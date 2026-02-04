#!/usr/bin/env python3
"""Import GeoNames cities into DynamoDB for population ranking.

Input: GeoNames cities dump (tab-separated), e.g. cities5000.txt
We store:
  PK = CC#CITYLOWER
  SK = POP#<zero-padded-pop>#ID#<geonameid>
  country_code, name, ascii_name, population, latitude, longitude, admin1_code

Usage:
  python scripts/geonames_import_cities.py --file cities5000.txt --table <ddb-table> --region eu-central-1 --countries CH,FR,DE,US
"""

import argparse
import csv
import re
import time
import unicodedata

import boto3


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip().casefold()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--region", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--countries", default="")
    args = ap.parse_args()

    countries = {c.strip().upper() for c in args.countries.split(",") if c.strip()}

    ddb = boto3.resource("dynamodb", region_name=args.region)
    table = ddb.Table(args.table)

    n = 0
    t0 = time.time()

    with table.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
        with open(args.file, "r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) < 15:
                    continue

                geonameid = (row[0] or "").strip()
                name = (row[1] or "").strip()
                asciiname = (row[2] or "").strip()
                cc = (row[8] or "").strip().upper()
                admin1 = (row[10] or "").strip()
                lat = (row[4] or "").strip()
                lon = (row[5] or "").strip()
                pop = (row[14] or "0").strip()

                if not cc or not name:
                    continue
                if countries and cc not in countries:
                    continue

                try:
                    pop_i = int(pop)
                except Exception:
                    pop_i = 0

                city_key = normalize_name(asciiname or name)
                if not city_key:
                    continue
                pk = f"{cc}#{city_key}"
                sk = f"POP#{pop_i:012d}#ID#{geonameid}"

                batch.put_item(
                    Item={
                        "PK": pk,
                        "SK": sk,
                        "country_code": cc,
                        "name": name,
                        "ascii_name": asciiname,
                        "population": pop_i,
                        "latitude": lat,
                        "longitude": lon,
                        "admin1_code": admin1,
                        "geonameid": geonameid,
                    }
                )

                n += 1
                if args.limit and n >= args.limit:
                    break
                if n % 5000 == 0:
                    dt = time.time() - t0
                    print(f"Imported {n} rows ({n/dt:.1f}/s)")

    dt = time.time() - t0
    print(f"Done. Imported {n} rows in {dt:.1f}s")


if __name__ == "__main__":
    main()
