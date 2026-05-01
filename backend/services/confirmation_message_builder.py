from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final


@dataclass(frozen=True)
class ConfirmationMessage:
    text: str
    template_key: str
    template_version: str


_CLINIC_NAME: Final[str] = "Atend Já"
_CLINIC_WHATSAPP: Final[str] = "(15) 99695-0709"
_TEMPLATE_VERSION: Final[str] = "2026-05-01"

_TEMPLATES: Final[list[dict[str, str]]] = [
    {
        "key": "v1_a",
        "body": (
            "Olá, {patient_name}! Tudo bem?\n"
            "Aqui é da {clinic_name}.\n\n"
            "Estamos confirmando sua consulta com {professional_name} no dia {appointment_date} às {appointment_time}.\n\n"
            "Por favor, responda:\n"
            "👉 SIM - para confirmar presença\n"
            "👉 NÃO - caso não possa comparecer\n"
            "👉 REMARCAR - para ajustar o horário pelo WhatsApp: {clinic_whatsapp}\n\n"
            "⚠️ Este canal é exclusivo para confirmação de consultas.\n"
            "Para dúvidas ou outros assuntos, fale com a clínica pelo canal oficial."
        ),
    },
    {
        "key": "v1_b",
        "body": (
            "Oi, {patient_name}! Aqui é da {clinic_name}.\n\n"
            "Passando para confirmar sua consulta com {professional_name}, marcada para {appointment_date} às {appointment_time}.\n\n"
            "Você pode responder assim:\n"
            "👉 SIM - confirma presença\n"
            "👉 NÃO - informa que não poderá vir\n"
            "👉 REMARCAR - fala com a clínica sobre outro horário: {clinic_whatsapp}\n\n"
            "⚠️ Este número é usado apenas para confirmação de consultas.\n"
            "Se precisar de ajuda com outro assunto, chame a clínica no canal oficial."
        ),
    },
    {
        "key": "v1_c",
        "body": (
            "Olá, {patient_name}.\n\n"
            "Sua consulta com {professional_name} está agendada para {appointment_date} às {appointment_time}, e estamos fazendo a confirmação.\n\n"
            "Responda por favor:\n"
            "👉 SIM - para confirmar presença\n"
            "👉 NÃO - se não puder comparecer\n"
            "👉 REMARCAR - para ajustar data ou horário com a clínica: {clinic_whatsapp}\n\n"
            "⚠️ Canal exclusivo para confirmação de consultas.\n"
            "Para dúvidas ou demais solicitações, entre em contato pelo atendimento oficial."
        ),
    },
    {
        "key": "v1_d",
        "body": (
            "Olá, {patient_name}! Tudo certo?\n"
            "Aqui é da {clinic_name}.\n\n"
            "Estamos validando a presença da sua consulta com {professional_name} em {appointment_date}, às {appointment_time}.\n\n"
            "É só responder:\n"
            "👉 SIM - se vai comparecer\n"
            "👉 NÃO - se não vai conseguir vir\n"
            "👉 REMARCAR - para combinar outro horário pelo WhatsApp: {clinic_whatsapp}\n\n"
            "⚠️ Este canal atende somente confirmações de consulta.\n"
            "Outros assuntos devem ser tratados com a clínica pelo canal principal."
        ),
    },
    {
        "key": "v1_e",
        "body": (
            "Oi, {patient_name}!\n\n"
            "A {clinic_name} está confirmando sua consulta com {professional_name} no dia {appointment_date} às {appointment_time}.\n\n"
            "Nos responda com uma destas opções:\n"
            "👉 SIM - para confirmar presença\n"
            "👉 NÃO - caso não possa comparecer\n"
            "👉 REMARCAR - para falar com a clínica e ajustar o horário: {clinic_whatsapp}\n\n"
            "⚠️ Este canal é exclusivo para confirmação de consultas.\n"
            "Para dúvidas ou outros atendimentos, procure o nosso WhatsApp oficial."
        ),
    },
    {
        "key": "v1_f",
        "body": (
            "Olá, {patient_name}! Aqui é da {clinic_name}.\n\n"
            "Queremos confirmar sua consulta com {professional_name}, agendada para {appointment_date} às {appointment_time}.\n\n"
            "Por favor, responda:\n"
            "👉 SIM - para manter a confirmação\n"
            "👉 NÃO - se não puder comparecer\n"
            "👉 REMARCAR - para ajustar com a clínica pelo WhatsApp {clinic_whatsapp}\n\n"
            "⚠️ Este canal responde apenas confirmações de consulta.\n"
            "Se precisar de outro suporte, fale conosco pelo canal oficial."
        ),
    },
    {
        "key": "v1_g",
        "body": (
            "Olá, {patient_name}.\n"
            "Mensagem da {clinic_name}.\n\n"
            "Estamos entrando em contato para confirmar sua consulta com {professional_name}, marcada para {appointment_date} às {appointment_time}.\n\n"
            "Responda conforme abaixo:\n"
            "👉 SIM - confirma presença\n"
            "👉 NÃO - informa ausência\n"
            "👉 REMARCAR - solicita ajuste de horário com a clínica: {clinic_whatsapp}\n\n"
            "⚠️ Canal exclusivo para confirmação de consultas.\n"
            "Mensagens fora desse escopo devem ser tratadas pelo atendimento oficial."
        ),
    },
    {
        "key": "v1_h",
        "body": (
            "Oi, {patient_name}! Tudo bem?\n\n"
            "Estamos confirmando sua consulta com {professional_name} para {appointment_date}, às {appointment_time}.\n"
            "Aqui é da {clinic_name}.\n\n"
            "Responda com uma opção:\n"
            "👉 SIM - para confirmar presença\n"
            "👉 NÃO - se não puder vir\n"
            "👉 REMARCAR - para ajustar o horário falando com a clínica: {clinic_whatsapp}\n\n"
            "⚠️ Este canal é exclusivo para confirmação de consultas.\n"
            "Para outros assuntos, use o canal oficial da clínica."
        ),
    },
]


def _format_appointment_date(date_str: str | None) -> str:
    from datetime import datetime

    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str


def _format_appointment_time(time_str: str | None) -> str:
    time_str = (time_str or "").strip()
    return time_str[:5] if time_str else ""


def _stable_template_index(schedule: dict) -> int:
    seed = str(schedule.get("id") or schedule.get("telefonePrincipal") or schedule.get("nome") or "")
    digest = sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % len(_TEMPLATES)


def build_confirmation_message(schedule: dict) -> ConfirmationMessage:
    patient_name = schedule.get("nome", "Paciente")
    professional_name = ((schedule.get("profissionalSaude") or {}).get("nome") or "seu médico").strip()
    appointment_date = _format_appointment_date(schedule.get("data"))
    appointment_time = _format_appointment_time(schedule.get("horaInicio"))

    template = _TEMPLATES[_stable_template_index(schedule)]
    text = template["body"].format(
        patient_name=patient_name,
        professional_name=professional_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        clinic_name=_CLINIC_NAME,
        clinic_whatsapp=_CLINIC_WHATSAPP,
    )
    return ConfirmationMessage(
        text=text,
        template_key=template["key"],
        template_version=_TEMPLATE_VERSION,
    )
