import re


def normalize_brazil_phone(raw: str | None) -> str:
    """
    Normaliza telefones brasileiros para dígitos puros no formato 55XXXXXXXXXXX.

    Exemplos:
    - "(15) 99695-0709"   -> "5515996950709"
    - "+55|15996950709"   -> "5515996950709"
    - "15996950709"       -> "5515996950709"
    """
    phone = (raw or "").strip()
    if not phone:
        return ""

    phone = phone.replace("+55|", "55")
    digits = re.sub(r"\D", "", phone)

    if not digits:
        return ""
    if not digits.startswith("55"):
        digits = "55" + digits

    return digits
