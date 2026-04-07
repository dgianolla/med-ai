"""
Definições das tools Anthropic para o agente de Agendamento.
O Claude decide quando e como chamar cada tool.
"""

TOOLS = [
    {
        "name": "get_agenda",
        "description": (
            "Retorna os agendamentos existentes em um período. "
            "Use para contar quantos pacientes de convênio já estão agendados em uma data "
            "para um determinado profissional, antes de exibir horários para pacientes de convênio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_start": {
                    "type": "string",
                    "description": "Data de início no formato YYYY-MM-DD.",
                },
                "date_end": {
                    "type": "string",
                    "description": "Data de fim no formato YYYY-MM-DD. Use a mesma data de início para um único dia.",
                },
                "professional_id": {
                    "type": "integer",
                    "description": "ID do profissional para filtrar os agendamentos.",
                },
            },
            "required": ["date_start", "date_end", "professional_id"],
        },
    },
    {
        "name": "get_available_dates",
        "description": (
            "Busca as datas disponíveis para agendamento de um profissional em um determinado mês e ano. "
            "Use para mostrar ao paciente quais datas têm horário disponível."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Especialidade desejada. Ex: cardiologia, ginecologia, ortopedia, dermatologia, endocrinologia, clinica_geral",
                },
                "month": {
                    "type": "integer",
                    "description": "Mês desejado (1-12)",
                },
                "year": {
                    "type": "integer",
                    "description": "Ano desejado. Ex: 2026",
                },
            },
            "required": ["specialty", "month", "year"],
        },
    },
    {
        "name": "get_available_times",
        "description": (
            "Busca os horários disponíveis para uma especialidade em uma data específica. "
            "Use após o paciente escolher uma data para mostrar os horários disponíveis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Especialidade desejada.",
                },
                "date": {
                    "type": "string",
                    "description": "Data no formato YYYY-MM-DD. Ex: 2026-04-08",
                },
            },
            "required": ["specialty", "date"],
        },
    },
    {
        "name": "schedule_appointment",
        "description": (
            "Realiza o agendamento da consulta após confirmar todos os dados com o paciente. "
            "Só use esta tool quando tiver: nome completo, telefone, "
            "especialidade, data e horário confirmados pelo paciente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Especialidade da consulta.",
                },
                "date": {
                    "type": "string",
                    "description": "Data da consulta no formato YYYY-MM-DD.",
                },
                "hora_inicio": {
                    "type": "string",
                    "description": "Horário de início no formato HH:MM:SS. Ex: 09:00:00",
                },
                "hora_fim": {
                    "type": "string",
                    "description": "Horário de fim no formato HH:MM:SS. Ex: 09:15:00",
                },
                "patient_name": {
                    "type": "string",
                    "description": "Nome completo do paciente.",
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Telefone do paciente (apenas números). Ex: 15988001234",
                },
                "convenio": {
                    "type": "string",
                    "description": "Convênio do paciente. Use 'particular' se não tiver convênio. Opções: particular, funserv, amhemed, incor, ossel, dental_med",
                    "default": "particular",
                },
            },
            "required": [
                "specialty", "date", "hora_inicio", "hora_fim",
                "patient_name", "patient_phone",
            ],
        },
    },
]
