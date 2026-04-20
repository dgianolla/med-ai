from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import get_settings

WEEKDAY_NAMES_PT_BR = (
    "segunda-feira",
    "terca-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sabado",
    "domingo",
)


def clinic_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def clinic_now() -> datetime:
    return datetime.now(clinic_tz())


def clinic_today() -> date:
    return clinic_now().date()


def parse_iso_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def weekday_name_pt_br(target: date | str) -> str:
    if isinstance(target, str):
        target = parse_iso_date(target)
    return WEEKDAY_NAMES_PT_BR[target.weekday()]


def format_date_br(target: date | str) -> str:
    if isinstance(target, str):
        target = parse_iso_date(target)
    return target.strftime("%d/%m/%Y")

