"""
Definições das tools Anthropic para o agente de Retorno.
Reutiliza a mesma lógica de disponibilidade do agendamento.
"""

TOOLS = [
    {
        "name": "get_available_dates",
        "description": (
            "Busca datas disponíveis para retorno de um profissional em um determinado mês e ano."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Especialidade do médico que fez a consulta original.",
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
            "Busca horários disponíveis para retorno em uma data específica."
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
                    "description": "Data no formato YYYY-MM-DD.",
                },
            },
            "required": ["specialty", "date"],
        },
    },
    {
        "name": "schedule_return",
        "description": (
            "Agenda o retorno do paciente após confirmar data, horário e nome. "
            "Use somente após o paciente confirmar todos os dados."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Especialidade da consulta original.",
                },
                "date": {
                    "type": "string",
                    "description": "Data do retorno no formato YYYY-MM-DD.",
                },
                "hora_inicio": {
                    "type": "string",
                    "description": "Horário de início no formato HH:MM:SS.",
                },
                "hora_fim": {
                    "type": "string",
                    "description": "Horário de fim no formato HH:MM:SS.",
                },
                "patient_name": {
                    "type": "string",
                    "description": "Nome completo do paciente.",
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Telefone do paciente (apenas números).",
                },
            },
            "required": [
                "specialty", "date", "hora_inicio", "hora_fim",
                "patient_name", "patient_phone",
            ],
        },
    },
]
