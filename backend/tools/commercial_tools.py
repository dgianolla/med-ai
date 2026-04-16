"""
Definições das tools Anthropic para o agente Comercial.

Inclui a tool `confirm_combo`, que é o sinal estruturado para o orquestrador
mudar o fluxo para `flow_type=combo` e encaminhar para agendamento com a
especialidade da consulta já resolvida a partir dos metadados do combo.
"""

from knowledge.models import Combo
from knowledge.service import get_knowledge


TOOLS = [
    {
        "name": "confirm_combo",
        "description": (
            "Use esta tool quando o paciente confirmar claramente o interesse em um combo específico "
            "(ex: 'quero o combo mulher com exames', 'pode ser esse', 'vamos com o combo idoso'). "
            "Essa tool NÃO agenda nada — ela apenas registra a escolha do combo e prepara o "
            "handoff para agendamento com a especialidade correta da consulta. "
            "Só chame quando houver confirmação explícita do combo; não chame apenas porque o "
            "paciente perguntou sobre preço ou pediu detalhes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "combo_id": {
                    "type": "string",
                    "description": (
                        "Id formal do combo, exatamente como cadastrado no backend. "
                        "Valores válidos: combo_mulher_completo, combo_mulher_exames, "
                        "combo_homem, combo_idoso, combo_pediatria, combo_cardiologia."
                    ),
                },
            },
            "required": ["combo_id"],
        },
    },
]


def confirm_combo(combo_id: str) -> dict:
    """
    Valida o combo_id contra o catálogo estruturado e devolve os metadados
    operacionais que o orquestrador usa para montar o handoff.
    """
    knowledge = get_knowledge()
    combo: Combo | None = knowledge.get_combo(combo_id)
    if combo is None:
        return {
            "ok": False,
            "error": f"combo_id desconhecido: {combo_id}",
        }

    return {
        "ok": True,
        "combo_id": combo.id,
        "name": combo.name,
        "price": combo.price,
        "consultation_included": combo.consultation_included,
        "consultation_specialty": combo.consultation_specialty,
        "collection_included": combo.collection_included,
        "collection_schedule_required": combo.collection_schedule_required,
        "return_included": combo.return_included,
        "return_window_days": combo.return_window_days,
    }
