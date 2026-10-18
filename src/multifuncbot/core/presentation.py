"""Small bilingual display helpers; storage keeps ISO dates and integer money."""

from datetime import date, datetime

RU_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
EN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def display_date(value: str | date, language: str) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    months = RU_MONTHS if language == "ru" else EN_MONTHS
    return f"{value.day} {months[value.month - 1]} {value.year}"


def zone_label(zone, when: datetime) -> str:
    local = when.astimezone(zone)
    return local.tzname() or local.strftime("UTC%z")


def money(kopecks: int) -> str:
    rubles, remainder = divmod(kopecks, 100)
    amount = f"{rubles:,}".replace(",", " ")
    return f"{amount}{',' + str(remainder).zfill(2) if remainder else ''} ₽"
