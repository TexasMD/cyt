"""Date parsing module for SecondHandSongs HTML table cells."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

PAREN_RE = re.compile(r"\s*\([^)]*\)$")
MDY_RE = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")
DMY_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")
MY_RE = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")
YEAR_RE = re.compile(r"^(\d{4})$")
ISO_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
ISO_MON_RE = re.compile(r"^(\d{4})-(\d{2})$")
CIRCA_RE = re.compile(r"^(?:circa|ca\.|c\.)\s*", re.I)


@dataclass(frozen=True)
class SHSDate:
    status: str
    value: str
    precision: str


def parse_shs_date(text: Optional[str]) -> Optional[SHSDate]:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    if raw.casefold() in {"unreleased", "unissued", "withdrawn"}:
        return SHSDate(status="undated", value="", precision="none")

    # Remove trailing parentheticals e.g. "(performance date)", "(recording date)"
    clean = PAREN_RE.sub("", raw).strip()
    # Remove circa prefix if present
    clean = CIRCA_RE.sub("", clean).strip()

    # ISO Day: YYYY-MM-DD
    m = ISO_DAY_RE.match(clean)
    if m:
        year, month, day = m.groups()
        return SHSDate(status="dated", value=f"{int(year):04d}-{int(month):02d}-{int(day):02d}", precision="day")

    # ISO Month: YYYY-MM
    m = ISO_MON_RE.match(clean)
    if m:
        year, month = m.groups()
        return SHSDate(status="dated", value=f"{int(year):04d}-{int(month):02d}-00", precision="month")

    # Month Day, Year: March 11, 1975
    m = MDY_RE.match(clean)
    if m:
        mon_str, day, year = m.groups()
        mon = MONTH_MAP.get(mon_str.lower())
        if mon:
            return SHSDate(status="dated", value=f"{int(year):04d}-{mon:02d}-{int(day):02d}", precision="day")

    # Day Month Year: 11 March 1975
    m = DMY_RE.match(clean)
    if m:
        day, mon_str, year = m.groups()
        mon = MONTH_MAP.get(mon_str.lower())
        if mon:
            return SHSDate(status="dated", value=f"{int(year):04d}-{mon:02d}-{int(day):02d}", precision="day")

    # Month Year: September 1983
    m = MY_RE.match(clean)
    if m:
        mon_str, year = m.groups()
        mon = MONTH_MAP.get(mon_str.lower())
        if mon:
            return SHSDate(status="dated", value=f"{int(year):04d}-{mon:02d}-00", precision="month")

    # Year: 1975
    m = YEAR_RE.match(clean)
    if m:
        year = m.group(1)
        return SHSDate(status="dated", value=f"{int(year):04d}-00-00", precision="year")

    return None
