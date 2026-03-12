#!/usr/bin/env python3
"""Generate a fake address benchmark dataset.

Output format: tab-separated with 5 columns:
address, city, street, postcode, country

- 200 rows are clean/plausible.
- 800 rows contain plausible errors.
- Erroneous rows remain internally consistent: the full address contains the
  same mutated city/street/postcode values that appear in the split columns.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass
from pathlib import Path


SEED = 123
OUT_PATH = Path("data/fake_addresses.tsv")


@dataclass(frozen=True)
class Locale:
    language: str
    country: str
    cities: list[str]
    streets: list[str]
    postcodes: list[str]


LOCALES: list[Locale] = [
    Locale(
        "english",
        "United States",
        ["New York", "Los Angeles", "Chicago", "Seattle", "Austin", "Miami", "Boston", "Denver", "Atlanta"],
        ["Main St", "Broadway", "Elm Street", "Oak Ave", "Sunset Blvd", "Market Street", "Lakeview Drive", "Maple Rd"],
        ["10001", "90001", "60601", "98101", "73301", "33101", "02108", "80202", "30301"],
    ),
    Locale(
        "chinese",
        "中国",
        ["北京市", "上海市", "广州市", "深圳市", "成都市", "杭州市", "苏州市"],
        ["长安街", "人民路", "中山路", "解放大道", "和平街", "光明路", "西大街"],
        ["100000", "200000", "510000", "518000", "610000", "310000", "215000"],
    ),
    Locale(
        "thai",
        "ประเทศไทย",
        ["กรุงเทพมหานคร", "เชียงใหม่", "ภูเก็ต", "ขอนแก่น", "หาดใหญ่"],
        ["ถนนพระรามเก้า", "ถนนจันทน์", "ถนนสุขุมวิท", "ถนนสีลม", "ถนนนิมมานเหมินท์", "ถนนราชดำเนิน"],
        ["10310", "50200", "83000", "40000", "90110", "10200"],
    ),
    Locale(
        "japanese",
        "日本",
        ["東京都", "大阪市", "京都市", "名古屋市", "福岡市"],
        ["中央通り", "桜通り", "銀座", "表参道", "本町", "中之島公園"],
        ["100-0001", "530-0001", "600-8001", "460-0002", "810-0001", "602-0895"],
    ),
    Locale(
        "french",
        "France",
        ["Paris", "Lyon", "Marseille", "Toulouse", "Lille", "Nantes"],
        ["Rue de la Paix", "Avenue des Champs-Elysees", "Rue du Faubourg Saint-Honore", "Rue de la Republique", "Boulevard Haussmann", "Rue de Strasbourg"],
        ["75001", "69002", "13001", "31000", "59000", "44000"],
    ),
    Locale(
        "german",
        "Deutschland",
        ["Berlin", "Munchen", "Hamburg", "Frankfurt", "Koln", "Stuttgart"],
        ["Hauptstrasse", "Lindenweg", "Bahnhofstrasse", "Schlossallee", "Marktplatz", "Kurfuerstendamm"],
        ["10115", "80331", "20095", "60311", "50667", "70173"],
    ),
    Locale(
        "spanish",
        "Espana",
        ["Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao", "Granada"],
        ["Calle Mayor", "Gran Via", "Rambla de Catalunya", "Calle Alcala", "Paseo de la Castellana", "Calle de Serrano"],
        ["28013", "08007", "46001", "41001", "48001", "18001"],
    ),
]


def mutate_text(text: str, rng: random.Random) -> str:
    if not text:
        return text
    op = rng.choice(["drop", "swap", "dup", "case", "accent", "space", "suffix"])
    if op == "drop" and len(text) > 3:
        i = rng.randrange(len(text))
        return text[:i] + text[i + 1 :]
    if op == "swap" and len(text) > 3:
        i = rng.randrange(len(text) - 1)
        return text[:i] + text[i + 1] + text[i] + text[i + 2 :]
    if op == "dup":
        i = rng.randrange(len(text))
        return text[:i] + text[i] + text[i:]
    if op == "case":
        return "".join(ch.upper() if rng.random() < 0.5 else ch.lower() for ch in text)
    if op == "accent":
        return unicodedata.normalize("NFKD", text)
    if op == "space":
        return " ".join(text.split())
    if op == "suffix":
        return text + rng.choice([" bis", " apt", " /B", " #", " c/o"])
    return text


def mutate_postcode(postcode: str, rng: random.Random) -> str:
    if not postcode:
        return postcode
    if rng.random() < 0.65:
        chars = list(postcode)
        digit_positions = [i for i, ch in enumerate(chars) if ch.isdigit()]
        if digit_positions:
            i = rng.choice(digit_positions)
            chars[i] = rng.choice("0123456789")
        return "".join(chars)
    return postcode + rng.choice(["A", "B", "X"])


def format_address(number: str, street: str, city: str, postcode: str, locale: Locale, rng: random.Random) -> str:
    templates = {
        "english": [
            "{number} {street}, {city} {postcode}",
            "{number} {street}, {city}, {postcode}",
        ],
        "chinese": [
            "{city}{street}{number}号 {postcode}",
            "{postcode} {city}{street}{number}号",
        ],
        "thai": [
            "{number} {street} {city} {postcode}",
            "{street} {number} {city} {postcode}",
        ],
        "japanese": [
            "{postcode} {city}{street}{number}",
            "{city}{street}{number} {postcode}",
        ],
        "french": [
            "{number} {street}, {postcode} {city}",
            "{number} {street} {postcode} {city}",
        ],
        "german": [
            "{street} {number}, {postcode} {city}",
            "{street} {number} {postcode} {city}",
        ],
        "spanish": [
            "{street} {number}, {postcode} {city}",
            "{number} {street}, {postcode} {city}",
        ],
    }
    template = rng.choice(templates[locale.language])
    return template.format(number=number, street=street, city=city, postcode=postcode)


def base_record(locale: Locale, rng: random.Random) -> tuple[str, str, str, str]:
    city = rng.choice(locale.cities)
    street = rng.choice(locale.streets)
    postcode = rng.choice(locale.postcodes)
    number = str(rng.randint(1, 999))
    return number, street, city, postcode


def clean_row(locale: Locale, rng: random.Random) -> str:
    number, street, city, postcode = base_record(locale, rng)
    address = format_address(number, street, city, postcode, locale, rng)
    return "\t".join([address, city, street, postcode, locale.country])


def error_row(locale: Locale, rng: random.Random) -> str:
    number, street, city, postcode = base_record(locale, rng)

    # Mutate components first, then build the address from those mutated values.
    street_bad = mutate_text(street, rng)
    city_bad = mutate_text(city, rng)
    postcode_bad = mutate_postcode(postcode, rng)
    if rng.random() < 0.25:
        number = str(max(1, int(number) + rng.choice([-1, 1, 10])))
    address_bad = format_address(number, street_bad, city_bad, postcode_bad, locale, rng)
    if rng.random() < 0.2:
        address_bad = mutate_text(address_bad, rng)
    return "\t".join([address_bad, city_bad, street_bad, postcode_bad, locale.country])


def main() -> None:
    rng = random.Random(SEED)
    rows: list[str] = []

    clean_counts = {locale.language: 200 // len(LOCALES) for locale in LOCALES}
    for locale in LOCALES[: 200 - sum(clean_counts.values())]:
        clean_counts[locale.language] += 1

    for locale in LOCALES:
        for _ in range(clean_counts[locale.language]):
            rows.append(clean_row(locale, rng))

    for _ in range(800):
        rows.append(error_row(rng.choice(LOCALES), rng))

    OUT_PATH.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
