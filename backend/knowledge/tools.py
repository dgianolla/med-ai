"""
Tool Anthropic: get_clinic_info
Permite que os agentes consultem a base de conhecimento da clínica.
"""

from knowledge.service import get_knowledge

TOOLS = [
    {
        "name": "get_clinic_info",
        "description": (
            "Consulta informações sobre a clínica: preços de combos, protocolos de emagrecimento, "
            "horários de funcionamento, endereço, formas de pagamento, convênios aceitos, "
            "política de retorno, documentos necessários, exames disponíveis, profissionais "
            "e canetas injetáveis (Ozempic, Mounjaro)."
            "\nUse quando o paciente perguntar sobre preços, horários, localização, convênios, "
            "formas de pagamento, protocolos de emagrecimento, canetas injetáveis, "
            "ou qualquer informação geral sobre a clínica."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A pergunta ou tópico de interesse em linguagem natural. "
                        "Ex: 'qual o preço do combo mulher?', 'qual o horário de funcionamento?', "
                        "'quais convênios aceitam?', 'qual o endereço da clínica?', "
                        "'quanto custa o protocolo ozempic?'"
                    ),
                },
            },
            "required": ["query"],
        },
    },
]


async def get_clinic_info(query: str) -> dict:
    """Executa a consulta e retorna resultado formatado."""
    knowledge = get_knowledge()
    result_text = knowledge.search(query)
    return {"result": result_text, "query": query}
