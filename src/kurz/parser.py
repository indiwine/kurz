"""Parse KRunner queries like ``500 EUR to UAH``.

Pure functions only, so they're easy to unit test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Common symbols -> ISO codes. Ambiguous "$" is treated as USD.
SYMBOLS = {
    "€": "eur",
    "$": "usd",
    "£": "gbp",
    "¥": "jpy",
    "₴": "uah",
    "zł": "pln",
    "kč": "czk",
    "₹": "inr",
    "₽": "rub",
    "₺": "try",
    "₩": "krw",
    "₪": "ils",
    "₿": "btc",
}

_SYM = "|".join(re.escape(s) for s in sorted(SYMBOLS, key=len, reverse=True))
_CUR = rf"(?:[a-z]{{2,6}}|{_SYM})"
_AMOUNT = r"\d[\d\s,']*(?:[.,]\d+)?(?:\s*[km](?![a-z]))?"
_SEP = r"(?:\s+to\s+|\s+in\s+|\s*=>?\s*|\s*->\s*|\s+)"

# "500 eur to uah", "500eur uah", "500 eur", "500 € in czk"
_AMOUNT_FIRST = re.compile(
    rf"^\s*(?P<amount>{_AMOUNT})\s*(?P<src>{_CUR})(?:{_SEP}(?P<dst>{_CUR}))?\s*$",
    re.IGNORECASE,
)
# "eur 500 to uah", "€500", "$10 to gbp"
_CUR_FIRST = re.compile(
    rf"^\s*(?P<src>{_CUR})\s*(?P<amount>{_AMOUNT})(?:{_SEP}(?P<dst>{_CUR}))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Query:
    amount: float
    source: str  # lower-case code, e.g. "eur"
    target: str | None  # None -> caller picks default targets


def _normalize_currency(token: str) -> str:
    token = token.strip().lower()
    return SYMBOLS.get(token, token)


def parse_amount(text: str) -> float | None:
    """Parse ``1 000``, ``1,000.50``, ``1.000,50``, ``12,5``, ``2k``, ``1.5m``."""
    text = text.strip().lower().replace(" ", "").replace("'", "").replace(" ", "")
    multiplier = 1.0
    if text.endswith("k"):
        multiplier, text = 1_000.0, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000.0, text[:-1]
    if not text:
        return None

    if "," in text and "." in text:
        # Whichever separator comes last is the decimal one.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        # "1,000" / "1,000,000" -> thousands; "12,5" -> decimal
        if len(tail) == 3 and text.count(",") >= 1 and head.replace(",", "").isdigit():
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def parse_query(text: str, known: set[str] | frozenset[str]) -> Query | None:
    """Return a Query if *text* looks like a currency conversion, else None.

    *known* is the set of lower-case currency codes the rate source supports;
    tokens that aren't in it are rejected so "500 km to mi" doesn't match.
    """
    for pattern in (_AMOUNT_FIRST, _CUR_FIRST):
        m = pattern.match(text)
        if not m:
            continue
        amount = parse_amount(m.group("amount"))
        src = _normalize_currency(m.group("src"))
        dst = _normalize_currency(m.group("dst")) if m.group("dst") else None
        if amount is None or src not in known:
            continue
        if dst is not None and (dst not in known or dst == src):
            continue
        return Query(amount, src, dst)
    return None
