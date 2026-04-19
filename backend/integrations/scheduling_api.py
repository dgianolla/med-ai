import httpx
import logging
import re
import unicodedata
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://back.apphealth.com.br:9090/api-vizi"
AUTH_TOKEN = "laVZIRHpJt1K9ygtRcDQfH7L1QmjHPN9qZ7l87Qp9PKLR"

# Mapeamento especialidade → profissional(is)
# IDs de especialidade vindos da API: /especialidades
PROFESSIONALS = {
    "clinica_geral":        [{"id": 29116, "nome": "Dr. Ricardo Dilda",      "esp_id": 168}],
    "cardiologia":          [{"id": 29116, "nome": "Dr. Ricardo Dilda",      "esp_id": 6}],
    "psiquiatria":          [{"id": 35270, "nome": "Dra. Rebeca Espelho Storch", "esp_id": 49}],
    "endocrinologia":       [{"id": 30319, "nome": "Dr. Arthur Wagner",      "esp_id": 19}],
    "ginecologia":          [
        {"id": 30320, "nome": "Dra. Silmara Capeleto", "esp_id": 24},
        {"id": 32874, "nome": "Dra. Paolla Cappelari", "esp_id": 58},
    ],
    "dermatologia":         [{"id": 31644, "nome": "Dra. Ellen Santini",     "esp_id": 18}],
    # STANDBY: Otorrinolaringologia (esp_id: 44) — Dra. Camila Maria (ID 34374) disponível na API
}

# Convênios

# Convênios
CONVENIOS = {
    "particular": 48339,
    "amhemed":    59000,
    "amhemed_plus": 59000,
    "funserv":    59001,
    "incor":      59002,
    "dental_med": 58999,
    "medprev":    59756,
}


def _headers() -> dict:
    return {"Authorization": AUTH_TOKEN}


async def get_available_dates(professional_id: int, month: int, year: int) -> list[str]:
    """Retorna datas disponíveis para um profissional em determinado mês/ano."""
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        resp = await client.get(
            f"{BASE_URL}/agenda/profissionais/{professional_id}/datas",
            headers=_headers(),
            params={"mes": month, "ano": year},
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["data"] for item in data]


async def get_available_times(professional_id: int, date: str) -> list[dict]:
    """Retorna horários disponíveis para um profissional em determinada data.

    Returns list of {"horaInicio": "07:00:00", "horaFim": "07:15:00"}
    """
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        resp = await client.get(
            f"{BASE_URL}/agenda/profissionais/{professional_id}/horarios",
            headers=_headers(),
            params={"data": date},
        )
        resp.raise_for_status()
        return resp.json()


async def get_agenda(date_start: str, date_end: str) -> list[dict]:
    """Retorna agendamentos existentes em um período para contagem de convênios."""
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        resp = await client.get(
            f"{BASE_URL}/agendamentos",
            headers=_headers(),
            params={"dataInicio": date_start, "dataFim": date_end},
        )
        resp.raise_for_status()
        return resp.json()


async def create_appointment(
    professional_id: int,
    esp_id: int,
    date: str,
    hora_inicio: str,
    hora_fim: str,
    patient_name: str,
    patient_phone: str,
    convenio_id: int = 48339,
) -> dict:
    """Cria um agendamento via endpoint /ia. Retorna o agendamento criado."""
    phone_clean = patient_phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    payload = {
        "data": date,
        "horaInicio": hora_inicio,
        "horaFim": hora_fim,
        "situacao": "AGENDADO",
        "telefone": phone_clean,
        "convenio": {"id": convenio_id},
        "profissionalSaude": {"id": professional_id},
        "especialidade": {"id": esp_id},
        "unidade": {"id": 1},
        "paciente": {"nome": patient_name},
    }
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        resp = await client.post(
            f"{BASE_URL}/agendamentos/ia",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def cancel_appointment(appointment_id: str | int, reason: str = "Solicitado pelo paciente via WhatsApp") -> dict:
    """Cancela um agendamento existente. Retorna confirmação do cancelamento."""
    payload = {
        "situacao": "CANCELADO",
        "observacao": reason,
    }
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        resp = await client.put(
            f"{BASE_URL}/agendamentos/{appointment_id}/cancelar",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def confirm_appointment(appointment_id: str | int) -> dict:
    """Confirma um agendamento existente. Retorna confirmação da operação."""
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        resp = await client.put(
            f"{BASE_URL}/agendamentos/{appointment_id}/confirmar",
            headers={**_headers(), "Content-Type": "application/json"},
            json={},
        )
        resp.raise_for_status()
        return resp.json()


# Sinônimos → especialidade canônica. Aceita palavras ou expressões multi-token
# (ex.: "saude metabolica"). Todas as chaves ficam normalizadas (minúsculo, sem
# acento, sem pontuação — alinhado com _normalize_specialty abaixo).
_SPECIALTY_SYNONYMS: dict[str, str] = {
    # cardiologia
    "cardiologista": "cardiologia",
    "cardiologico": "cardiologia",
    "cardiologo": "cardiologia",
    "coracao": "cardiologia",
    "cardio": "cardiologia",
    # ginecologia
    "ginecologo": "ginecologia",
    "ginecologista": "ginecologia",
    "gineco": "ginecologia",
    "saude da mulher": "ginecologia",
    "saude feminina": "ginecologia",
    # dermatologia
    "dermato": "dermatologia",
    "dermatologo": "dermatologia",
    "dermatologa": "dermatologia",
    "pele": "dermatologia",
    # endocrinologia
    "endocrino": "endocrinologia",
    "endocrinologista": "endocrinologia",
    "metabolismo": "endocrinologia",
    "saude metabolica": "endocrinologia",
    "metabolica": "endocrinologia",
    "hormonio": "endocrinologia",
    "hormonal": "endocrinologia",
    # psiquiatria
    "psiquiatra": "psiquiatria",
    "saude mental": "psiquiatria",
    "mental": "psiquiatria",
    "ansiedade": "psiquiatria",
    "depressao": "psiquiatria",
    "tdah": "psiquiatria",
    # clinica geral
    "clinico": "clinica_geral",
    "geral": "clinica_geral",
    "clinica": "clinica_geral",
    "clinica geral": "clinica_geral",
    "clinico geral": "clinica_geral",
    # otorrino
    "otorrino": "otorrinolaringologia",
    "otorrinolaringologista": "otorrinolaringologia",
    "garganta": "otorrinolaringologia",
    "nariz": "otorrinolaringologia",
    "ouvido": "otorrinolaringologia",
}


def _normalize_specialty(specialty: str) -> str:
    """Minúsculo, sem acentos, sem pontuação, espaços colapsados."""
    if not specialty:
        return ""
    decomposed = unicodedata.normalize("NFKD", specialty)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = without_accents.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    return re.sub(r"\s+", " ", cleaned)


def _canonical_from_tokens(normalized: str) -> str | None:
    """Token/substring match contra chaves canônicas + sinônimos.

    Ex.: "endocrinologia saude metabolica" contém "endocrinologia" (chave canônica)
    → retorna "endocrinologia". Ex.: "saude metabolica e controle hormonal" contém
    "saude metabolica" (sinônimo) → retorna "endocrinologia".
    """
    canonical_keys = {k.replace("_", " "): k for k in PROFESSIONALS.keys()}

    # sinônimos multi-palavra primeiro (mais específicos)
    for synonym, canonical in sorted(
        _SPECIALTY_SYNONYMS.items(), key=lambda kv: -len(kv[0])
    ):
        if re.search(rf"\b{re.escape(synonym)}\b", normalized):
            return canonical

    # chaves canônicas como substring (ex.: "ginecologia" em "ginecologia e obstetricia")
    for canonical_space, canonical_key in canonical_keys.items():
        if re.search(rf"\b{re.escape(canonical_space)}\b", normalized):
            return canonical_key

    return None


def get_professionals_for_specialty(specialty: str) -> list[dict]:
    """Retorna profissionais da especialidade.

    Estratégia:
      1. Normaliza (lowercase, sem acento, sem pontuação).
      2. Match exato contra chaves canônicas ou sinônimos.
      3. Fallback: procura chave canônica ou sinônimo como substring/token.
      4. Loga o caminho de resolução p/ diagnóstico.
    """
    if not specialty:
        return []

    normalized = _normalize_specialty(specialty)
    normalized_key = normalized.replace(" ", "_")

    # 1. match exato em PROFESSIONALS (chave com underscore)
    if normalized_key in PROFESSIONALS:
        logger.info(
            "[SPECIALTY] resolve | input=%r | resolved=%s | via=exact",
            specialty, normalized_key,
        )
        return PROFESSIONALS[normalized_key]

    # 2. match exato em sinônimos (string normalizada com espaços)
    if normalized in _SPECIALTY_SYNONYMS:
        canonical = _SPECIALTY_SYNONYMS[normalized]
        logger.info(
            "[SPECIALTY] resolve | input=%r | resolved=%s | via=synonym_exact",
            specialty, canonical,
        )
        return PROFESSIONALS.get(canonical, [])

    # 3. fallback: token/substring
    canonical = _canonical_from_tokens(normalized)
    if canonical:
        logger.info(
            "[SPECIALTY] resolve | input=%r | resolved=%s | via=substring",
            specialty, canonical,
        )
        return PROFESSIONALS.get(canonical, [])

    logger.warning(
        "[SPECIALTY] resolve_fail | input=%r | normalized=%r",
        specialty, normalized,
    )
    return []
