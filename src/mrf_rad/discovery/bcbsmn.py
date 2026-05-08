from __future__ import annotations

from datetime import date


def current_index_url(today: date | None = None) -> str:
    today = today or date.today()
    return index_url(today.year, today.month)


def index_url(year: int, month: int) -> str:
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")
    stamp = f"{year}-{month:02d}-01"
    return (
        f"https://mktg.bluecrossmn.com/mrf/{year}/"
        f"{stamp}_Blue_Cross_and_Blue_Shield_of_Minnesota_index.json"
    )

