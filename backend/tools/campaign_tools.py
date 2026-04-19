"""
Tools de campanha disponíveis para todos os agentes.

Permitem que qualquer agente consulte dinamicamente o catálogo de campanhas
ativas e os detalhes de uma campanha específica, sem precisar carregar todo
o conteúdo no system prompt.

Uso típico: o agente recebe via L5 metadata que o lead veio de uma campanha,
ou vê no bloco REF que certa campanha existe, e quer detalhes completos
(fluxo, promessas, oferta) para responder com precisão.

Estas tools são **read-only**. Para executar o fluxo de uma campanha, o
agente deve encaminhar via handoff para o agente `campaign`.
"""

from __future__ import annotations

from typing import Any

from campaigns.service import get_campaign_service

TOOLS = [
    {
        "name": "list_active_campaigns",
        "description": (
            "Lista as campanhas comerciais ativas no momento. Use quando o "
            "paciente mencionar uma oferta, promoção ou campanha e você "
            "precisar confirmar se ela existe e quais são os dados básicos. "
            "Retorna campaign_id, campaign_name, especialidade, offer_anchor "
            "e um resumo curto de cada campanha ativa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_campaign_details",
        "description": (
            "Retorna os detalhes completos de uma campanha ativa: metadados, "
            "promessas permitidas/proibidas e o conteúdo operacional (fluxo, "
            "oferta, FAQ, escalonamento). Use quando precisar responder com "
            "precisão sobre uma campanha específica — ex.: paciente pergunta "
            "o que inclui um pacote ou quer saber se determinada condição é "
            "coberta. Se o agente não for o agente `campaign`, **não** execute "
            "o fluxo dessa campanha; use handoff para o agente `campaign`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": (
                        "Identificador da campanha (campo `campaign_id` do catálogo "
                        "de campanhas)."
                    ),
                },
            },
            "required": ["campaign_id"],
        },
    },
]


def list_active_campaigns() -> dict[str, Any]:
    """Retorna lista curta de campanhas ativas."""
    service = get_campaign_service()
    campaigns = service.list_all()
    return {
        "count": len(campaigns),
        "campaigns": [
            {
                "campaign_id": c.schema.campaign_id,
                "campaign_name": c.schema.campaign_name,
                "especialidade": c.schema.especialidade,
                "offer_anchor": c.schema.offer_anchor,
                "handoff_target": c.schema.handoff_target,
                "summary": c.summary(),
            }
            for c in campaigns
        ],
    }


def get_campaign_details(campaign_id: str) -> dict[str, Any]:
    """Retorna detalhes completos de uma campanha ativa pelo campaign_id."""
    service = get_campaign_service()
    campaign_id = (campaign_id or "").strip()
    if not campaign_id:
        return {"error": "campaign_id vazio"}

    # get() busca por campaign_name. Aqui queremos por campaign_id — percorremos.
    for c in service.list_all():
        if c.schema.campaign_id == campaign_id:
            schema = c.schema
            return {
                "campaign_id": schema.campaign_id,
                "campaign_name": schema.campaign_name,
                "status": schema.status,
                "especialidade": schema.especialidade,
                "offer_anchor": schema.offer_anchor,
                "handoff_target": schema.handoff_target,
                "valid_from": schema.valid_from.isoformat() if schema.valid_from else None,
                "valid_until": schema.valid_until.isoformat() if schema.valid_until else None,
                "allowed_promises": list(schema.allowed_promises),
                "forbidden_promises": list(schema.forbidden_promises),
                "body": schema.body.strip(),
            }

    return {
        "error": f"Campanha não encontrada ou inativa: {campaign_id}",
        "available_ids": [c.schema.campaign_id for c in service.list_all()],
    }


def execute_campaign_tool(name: str, tool_input: dict) -> dict[str, Any]:
    """Dispatcher único: chama a tool certa com base no nome.

    Retorna {"error": "..."} se o nome não bate com nenhuma tool de campanha.
    Agentes podem usar esse dispatcher para evitar duplicar o switch em cada
    agent file.
    """
    if name == "list_active_campaigns":
        return list_active_campaigns()
    if name == "get_campaign_details":
        return get_campaign_details(tool_input.get("campaign_id", ""))
    return {"error": f"Tool de campanha desconhecida: {name}"}


CAMPAIGN_TOOL_NAMES = frozenset({"list_active_campaigns", "get_campaign_details"})
