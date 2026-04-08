"""
Definições das tools Anthropic para o agente de Cancelamento.
"""

TOOLS = [
    {
        "name": "cancel_appointment",
        "description": (
            "Cancela um agendamento existente. "
            "Use SOMENTE após o paciente confirmar explicitamente que deseja cancelar. "
            "Sempre confirme o ID do agendamento, data e horário antes de chamar esta tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "integer",
                    "description": "ID numérico do agendamento a ser cancelado.",
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Motivo do cancelamento informado pelo paciente. "
                        "Ex: 'Não poderei comparecer', 'Quero reagendar', 'Motivo pessoal'."
                    ),
                },
            },
            "required": ["appointment_id"],
        },
    },
    {
        "name": "get_clinic_info",
        "description": (
            "Consulta informações sobre a clínica: política de cancelamento, "
            "reagendamento, prazos e condições."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A pergunta sobre política de cancelamento. "
                        "Ex: 'qual a política de cancelamento?', 'posso reagendar?'"
                    ),
                },
            },
            "required": ["query"],
        },
    },
]
