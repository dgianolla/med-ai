"""
Serviço de campanhas ativas da clínica.

Lê arquivos .md em backend/campaigns/, parseia frontmatter YAML simples e serve
o conteúdo para o CampaignAgent e para a triagem.

Regra operacional: arquivo presente no diretório = campanha ativa.
Para pausar uma campanha, remova o .md correspondente.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CAMPAIGNS_DIR = Path(__file__).parent

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class Campaign:
    """Uma campanha carregada de um arquivo .md."""

    def __init__(self, slug: str, frontmatter: dict[str, str], body: str, raw: str):
        self.slug = slug
        self.nome = frontmatter.get("nome", "").strip()
        self.especialidade = (frontmatter.get("especialidade") or "").strip() or None
        self.valor = (frontmatter.get("valor") or "").strip() or None
        self.body = body
        self.raw = raw  # frontmatter + corpo — pronto pra injetar no system prompt

    def summary(self) -> str:
        """Primeira linha útil do corpo para usar como resumo curto no índice."""
        for line in self.body.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            return s[:140]
        return ""

    def index_entry(self) -> str:
        """Linha única descrevendo a campanha para o índice da triage."""
        parts = [f'"{self.nome}"']
        meta = []
        if self.especialidade:
            meta.append(f"especialidade: {self.especialidade}")
        if self.valor:
            meta.append(self.valor)
        if meta:
            parts.append(" / ".join(meta))
        summary = self.summary()
        if summary:
            parts.append(summary)
        return " — ".join(parts)


class CampaignService:
    """Carrega e serve campanhas ativas com cache em memória."""

    def __init__(self):
        self._cache: dict[str, Campaign] = {}
        self._loaded = False

    def _load_all(self) -> None:
        if self._loaded:
            return

        self._cache.clear()
        for md_file in sorted(CAMPAIGNS_DIR.glob("*.md")):
            if md_file.name.startswith("_"):
                continue
            try:
                raw = md_file.read_text(encoding="utf-8")
                fm, body = self._parse_frontmatter(raw)

                if not fm.get("nome"):
                    logger.error(
                        "Campanha ignorada: frontmatter sem 'nome' | file=%s",
                        md_file.name,
                    )
                    continue

                campaign = Campaign(slug=md_file.stem, frontmatter=fm, body=body, raw=raw)

                if campaign.nome in self._cache:
                    logger.error(
                        "Campanha duplicada ignorada: nome já existe | file=%s | nome=%s",
                        md_file.name, campaign.nome,
                    )
                    continue

                self._cache[campaign.nome] = campaign
                logger.info(
                    "Campanha carregada: %s | file=%s | especialidade=%s | valor=%s",
                    campaign.nome, md_file.name, campaign.especialidade, campaign.valor,
                )
            except Exception as e:
                logger.error("Erro ao carregar campanha %s: %s", md_file.name, e)

        self._loaded = True

    @staticmethod
    def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
        """Parser mínimo: só aceita `key: value` em uma linha. Sem listas/dicts."""
        match = _FRONTMATTER_RE.match(raw)
        if not match:
            return {}, raw

        fm_block, body = match.group(1), match.group(2)
        fm: dict[str, str] = {}
        for line in fm_block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
        return fm, body

    # ----------------------------------------------------------------
    # API pública
    # ----------------------------------------------------------------

    def list_all(self) -> list[Campaign]:
        """Lista todas as campanhas ativas (arquivo presente no diretório)."""
        self._load_all()
        return list(self._cache.values())

    def get(self, nome: str) -> Campaign | None:
        """Busca campanha por nome exato (case-insensitive)."""
        self._load_all()
        target = nome.strip().lower()
        for c in self._cache.values():
            if c.nome.lower() == target:
                return c
        return None

    def index_text(self) -> str:
        """
        Texto pronto para injetar no system prompt da triagem.
        Contém só nome, meta e resumo curto de cada campanha.
        """
        campaigns = self.list_all()
        if not campaigns:
            return ""

        lines = [
            "## CAMPANHAS ATIVAS",
            "",
            "As campanhas abaixo estão no ar. Se a mensagem do paciente bater",
            "com o tema de uma delas, roteie para o agente `campaign` passando",
            "o nome exato da campanha. Se não bater com nenhuma, siga o fluxo",
            "normal (commercial, weight_loss, exams, etc.).",
            "",
        ]
        for c in campaigns:
            lines.append(f"- {c.index_entry()}")
        return "\n".join(lines)

    def reload(self) -> None:
        """Força reload do diretório. Útil em dev."""
        self._loaded = False
        self._cache.clear()
        self._load_all()


_service: CampaignService | None = None


def get_campaign_service() -> CampaignService:
    global _service
    if _service is None:
        _service = CampaignService()
    return _service
