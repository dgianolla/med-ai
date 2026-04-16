import httpx
import logging
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


def get_professionals_for_specialty(specialty: str) -> list[dict]:
    """Retorna profissionais disponíveis para uma especialidade."""
    key = specialty.lower().replace(" ", "_").replace("ç", "c").replace("ã", "a")
    # Normalização simples de palavras comuns
    aliases = {
        "cardiologista": "cardiologia",
        "cardiologico": "cardiologia",
        "cardiologo": "cardiologia",
        "ginecologo": "ginecologia",
        "ginecologista": "ginecologia",
        "gineco": "ginecologia",
        "dermato": "dermatologia",
        "dermatologo": "dermatologia",
        "dermatologa": "dermatologia",
        "pele": "dermatologia",
        "endocrino": "endocrinologia",
        "endocrinologista": "endocrinologia",
        "metabolismo": "endocrinologia",
        "hormonio": "endocrinologia",
        "hormonal": "endocrinologia",
        "psiquiatra": "psiquiatria",
        "psiquiatria": "psiquiatria",
        "mental": "psiquiatria",
        "ansiedade": "psiquiatria",
        "depressao": "psiquiatria",
        "depressão": "psiquiatria",
        "clinico": "clinica_geral",
        "clínico": "clinica_geral",
        "geral": "clinica_geral",
        "clinica": "clinica_geral",
        "otorrino": "otorrinolaringologia",
        "otorrinolaringologista": "otorrinolaringologia",
        "garganta": "otorrinolaringologia",
        "nariz": "otorrinolaringologia",
        "ouvido": "otorrinolaringologia",
    }
    key = aliases.get(key, key)
    return PROFESSIONALS.get(key, [])
