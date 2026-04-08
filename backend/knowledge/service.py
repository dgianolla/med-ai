"""
Serviço centralizado de conhecimento da clínica.
Lê arquivos JSON e serve dados estruturados para os agentes.
"""

import json
import logging
from pathlib import Path
from typing import Any
from functools import lru_cache

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent


class KnowledgeService:
    """Carrega e serve conhecimento da clínica com cache em memória."""

    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._loaded = False

    def _load_all(self) -> None:
        """Carrega todos os arquivos JSON na inicialização."""
        if self._loaded:
            return

        for filename in KNOWLEDGE_DIR.glob("*.json"):
            key = filename.stem  # clinic_info, professionals, pricing
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    self._cache[key] = json.load(f)
                logger.info("Knowledge loaded: %s", filename.name)
            except Exception as e:
                logger.error("Erro ao carregar knowledge/%s: %s", filename.name, e)
                self._cache[key] = {}

        self._loaded = True

    # ----------------------------------------------------------------
    # API pública
    # ----------------------------------------------------------------

    def get(self, category: str, path: str | None = None) -> Any:
        """
        Retorna dado de conhecimento por categoria e caminho opcional.

        Exemplos:
            get("clinic_info")                    → tudo
            get("clinic_info", "address")         → só endereço
            get("pricing", "combos")              → lista de combos
            get("pricing", "combos.0.price")      → preço do primeiro combo
            get("professionals", "convenios")     → lista de convênios
        """
        self._load_all()

        if category not in self._cache:
            logger.warning("Categoria de conhecimento desconhecida: %s", category)
            return None

        data = self._cache[category]

        if not path:
            return data

        # Navega pelo caminho (dot notation)
        keys = path.split(".")
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            elif isinstance(data, list):
                try:
                    data = data[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return data

    def search(self, query: str) -> str:
        """
        Busca simplificada por palavras-chave.
        Retorna texto formatado com os resultados.
        Usado pela tool get_clinic_info quando o Claude faz pergunta em linguagem natural.
        """
        self._load_all()
        query_lower = query.lower()
        results = []

        # ---- Combos e preços ----
        if any(w in query_lower for w in ["combo", "pacote", "preço", "valor", "custo", "quanto"]):
            pricing = self._cache.get("pricing", {})
            combos = pricing.get("combos", [])
            if any(w in query_lower for w in ["mulher", "gineco", "papanicolau"]):
                for c in combos:
                    if "mulher" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["homem", "masculino"]):
                for c in combos:
                    if "homem" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["idoso", "third age", "melhor idade"]):
                for c in combos:
                    if "idoso" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["pediatra", "criança", "infantil"]):
                for c in combos:
                    if "pediatria" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            elif any(w in query_lower for w in ["cardio", "coração", "cardiologista"]):
                for c in combos:
                    if "cardio" in c["name"].lower():
                        results.append(
                            f"**{c['name']}** — R$ {c['price']:.2f}\n"
                            f"Inclui: {', '.join(c['includes'])}"
                        )
            else:
                # Mostra todos os combos
                for c in combos:
                    results.append(f"**{c['name']}** — R$ {c['price']:.2f}")

            protocols = pricing.get("weight_loss_protocols", [])
            if any(w in query_lower for w in ["emagrecimento", "ozempic", "mounjaro", "peso"]):
                for p in protocols:
                    if "price_90_days" in p:
                        results.append(
                            f"**{p['name']}** — R$ {p['price_90_days']:.2f} (90 dias) "
                            f"ou R$ {p['price_monthly']:.2f}/mês"
                        )
                    else:
                        results.append(
                            f"**{p['name']}** — R$ {p['price']:.2f} ({p['duration_days']} dias)"
                        )

        # ---- Informações da clínica ----
        if any(w in query_lower for w in ["horário", "funcionamento", "aberto", "hora"]):
            hours = self._cache.get("clinic_info", {}).get("hours", {})
            results.append(
                f"**Horários de funcionamento:**\n"
                f"Seg–Sex: {hours.get('weekdays')}\n"
                f"Sábado: {hours.get('saturday')}\n"
                f"Domingo e Feriados: {hours.get('sunday_holidays')}"
            )

        if any(w in query_lower for w in ["endereço", "localização", "onde", "local", "fica"]):
            addr = self._cache.get("clinic_info", {}).get("address", {})
            results.append(
                f"**Endereço:** {addr.get('street')}\n"
                f"**Referência:** {addr.get('landmark')}"
            )

        if any(w in query_lower for w in ["pagamento", "pix", "parcela", "débito", "crédito", "dinheiro"]):
            payment = self._cache.get("clinic_info", {}).get("payment", {})
            results.append(
                f"**Formas de pagamento:** {', '.join(payment.get('methods', []))}\n"
                f"**Chave PIX:** {payment.get('pix_key')}\n"
                f"**Parcelamento:** Consultas até 2x | Exames/Combos até 10x (sem juros)"
            )

        if any(w in query_lower for w in ["convênio", "convenio", "plano", "particular"]):
            convenios = self._cache.get("professionals", {}).get("convenios", [])
            convenio_names = [c["name"] for c in convenios]
            results.append(
                f"**Convênios aceitos:** {', '.join(convenio_names)}"
            )

        if any(w in query_lower for w in ["retorno", "gratuito", "30 dia"]):
            ret = self._cache.get("clinic_info", {}).get("return_policy", {})
            results.append(
                f"**Política de retorno:** Gratuito em até {ret.get('free_return_days')} dias "
                f"da consulta original (com o mesmo médico)."
            )

        if any(w in query_lower for w in ["documento", "rg", "cnh", "levar", "preciso levar"]):
            docs = self._cache.get("clinic_info", {}).get("documents_required", [])
            results.append(f"**Documentos necessários:**\n" + "\n".join(f"• {d}" for d in docs))

        if any(w in query_lower for w in ["exame", "jejum", "resultado", "laboratorial"]):
            exam = self._cache.get("clinic_info", {}).get("exam_policy", {})
            results.append(
                f"**Política de exames:**\n"
                f"• Jejum: {exam.get('lab_fasting_hours')}\n"
                f"• Resultado: {exam.get('result_turnaround')}\n"
                f"• Pedido médico: obrigatório"
            )

        if any(w in query_lower for w in ["profissional", "médico", "doutor", "especialidade"]):
            profs = self._cache.get("professionals", {}).get("professionals", [])
            for p in profs:
                specs = ", ".join(s["name"] for s in p["specialties"])
                results.append(f"**{p['name']}** — {specs}")

        if not results:
            return "Não encontrei informações específicas para essa consulta. Posso verificar com a equipe da clínica!"

        return "\n\n".join(results)


# Instância global
_knowledge_service: KnowledgeService | None = None


def get_knowledge() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
