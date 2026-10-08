"""Panama-time dates and timestamps: the only place that converts to America/Panama and names months."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

PANAMA = ZoneInfo("America/Panama")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def panama(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(PANAMA)


def day_label(day: date | datetime) -> str:
    return f"{day.day} {MONTHS[day.month - 1]}"


def day_year_label(moment: datetime) -> str:
    return f"{day_label(moment)} {moment.year}"


def stamp(value: str) -> str:
    moment = panama(value)
    return f"{day_year_label(moment)}, {moment:%H:%M}"


def short_stamp(value: str) -> str:
    moment = panama(value)
    return f"{day_label(moment)}, {moment:%H:%M}"


def short_date(value: str | None) -> str:
    return day_label(panama(value)) if value else ""


def panama_time(value: str | None) -> str:
    return "Fecha desconocida" if value is None else panama(value).strftime("%d/%m/%Y %H:%M")
