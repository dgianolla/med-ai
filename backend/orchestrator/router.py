"""
Router inteligente: detecta quando uma mensagem pertence a outro agente.
Usado para handoff automático entre agentes sem precisar passar pela triagem.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Padrões que indicam que a pergunta é sobre PREÇOS/VALORES
_PRICE_PATTERNS = [
    r"\b(valor|preço|preco|custo|quanto\s*custa|quanto\s*é|quanto\s*e|tabela\s*de\s*preço)",
    r"\b(orcamento|orçamento|tabela|planos|pacotes?\s*de?\s*preço)",
    r"\b(pagamento|parcela|parcelament|desconto|pix|boleto)",
    r"\b(convênio|convenio|plano\s*de\s*saúde|plano\s*de\s*saude)",
    r"\b(aceita\s*\w+\s*convênio|aceita\s*\w+\s*convenio|trabalha\s*com\s*convênio|trabalha\s*com\s*convenio|trabalha\s*com\s*particular|aceita\s*particular)",
    r"\b(aceita\s*(funserv|amhemed|incor|ossel|dental\s*med|medprev|particular))",
    r"\b(desconto|desconto\s*a\s*vista|a\s*vista|dinheiro)",
    r"\b(combo|pacote|promoção|promocao|oferta)",
    r"\b(ozempic|mounjaro|emagrecimento|protocolo)",
]

# Padrões que indicam que a pergunta é sobre EXAMES
_EXAM_PATTERNS = [
    r"\b(exame|resultado\s*de\s*exame|laudo|coleta)",
    r"\b(raio[-\s]*x|ultrassom|ressonância|tomografia|ecg|eletro)",
    r"\b(sangue|urina|fezes|hemograma|glicemia|colesterol)",
    r"\b(enviou\s*exame|mandei\s*exame|segue\s*exame|foto\s*do\s*exame)",
    r"\b(jejum|resultado\s*ficou|pronto\s*o\s*exame)",
]

# Padrões que indicam que a pergunta é sobre RETORNO
_RETURN_PATTERNS = [
    r"\b(retorno|voltar\s*ao\s*m[eé]dico|follow[\s-]*up|pós[\s-]*consulta)",
    r"\b(consulta\s*anterior|ultima\s*consulta|última\s*consulta)",
    r"\b(30\s*dias|gratuito|re\s*consulta|reconsulta)",
]

# Padrões que indicam que a pergunta é sobre CANCELAMENTO
_CANCEL_PATTERNS = [
    r"\b(cancel|desmarc|desist|anul)",
    r"\b(não\s*posso\s*(mais|ir|comparecer)|nao\s*posso\s*(mais|ir|comparecer))",
    r"\b(quero\s*(cancelar|desmarcar)|preciso\s*(cancelar|desmarcar)|gostaria\s*(de\s*)?(cancelar|desmarcar))",
    r"\b(remarcar|reagendar|mudar\s*data|trocar\s*data|trocar\s*horário|trocar\s*horario)",
    r"\b(vou\s*(ter|precisar)\s*desmarcar|vou\s*(ter|precisar)\s*cancelar)",
]

# Padrões que indicam que a pergunta é sobre AGENDAMENTO
_SCHEDULING_PATTERNS = [
    r"\b(marcar|agendar|agenda|horário?\s*dispon[ií]vel|tem\s*vaga)",
    r"\b(próxima\s*(consulta|disponibilidade)|proxima\s*data)",
    r"\b(consulta|profissional|m[eé]dico|doutor|dra?\.?\s*\w+)",
    r"\b(especialidade|cardio|gineco|dermato|orto|endocrino|psiquiatra)",
]


def classify_intent(text: str) -> str | None:
    """
    Classifica o intent da mensagem.
    Retorna o agent_id alvo ou None se não houver match claro.
    """
    text_lower = text.lower().strip()

    if not text_lower:
        return None

    # Verifica cada categoria por score de matches
    scores = {
        "commercial": 0,
        "exams": 0,
        "return": 0,
        "cancellation": 0,
        "scheduling": 0,
    }

    for pattern in _PRICE_PATTERNS:
        if re.search(pattern, text_lower):
            scores["commercial"] += 1

    for pattern in _EXAM_PATTERNS:
        if re.search(pattern, text_lower):
            scores["exams"] += 1

    for pattern in _RETURN_PATTERNS:
        if re.search(pattern, text_lower):
            scores["return"] += 1

    for pattern in _CANCEL_PATTERNS:
        if re.search(pattern, text_lower):
            scores["cancellation"] += 1

    for pattern in _SCHEDULING_PATTERNS:
        if re.search(pattern, text_lower):
            scores["scheduling"] += 1

    # Pega o maior score (mínimo 1 match)
    best_agent = max(scores, key=scores.get)
    best_score = scores[best_agent]

    if best_score == 0:
        return None

    logger.debug(
        "Router classification | text=%s | scores=%s | best=%s (score=%d)",
        text_lower[:50], scores, best_agent, best_score,
    )

    return best_agent


def should_handoff(current_agent: str, text: str) -> str | None:
    """
    Decide se deve fazer handoff para outro agente.
    Retorna o target agent ou None se deve permanecer no atual.
    """
    target = classify_intent(text)

    if target is None:
        return None

    # Se já está no agente certo, não faz handoff
    if target == current_agent:
        return None

    # Regras de prioridade: triage sempre pode rotear
    if current_agent == "triage":
        return target

    # Se o intent é claramente de outro domínio, sugere handoff
    logger.info(
        "Router: handoff recomendado | current=%s → target=%s | msg=%s",
        current_agent, target, text[:80],
    )

    return target
