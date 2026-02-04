#!/usr/bin/env python3
"""Import GeoNames postal codes into DynamoDB.

Input file format: GeoNames postal code dump (tab-separated), e.g. allCountries.txt
Fields:
  country code, postal code, place name, admin name1, admin code1, admin name2, admin code2,
  admin name3, admin code3, latitude, longitude, accuracy

We store:
  PK = CC#POSTCODE
  latitude, longitude (as strings)
  place_name, admin1_name, admin1_code

Usage:
  python scripts/geonames_import_postcodes.py --file allCountries.txt --table <ddb-table> --region eu-central-1

NOTE: This is intended as a one-off tool run locally.
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
    ap.add_argument("--countries", default="", help="Comma-separated ISO-2 codes to include (e.g., CH,FR,DE). Empty = all")
    args = ap.parse_args()

    countries = {c.strip().upper() for c in args.countries.split(",") if c.strip()}

    ddb = boto3.resource("dynamodb", region_name=args.region)
    table = ddb.Table(args.table)

    n = 0
    t0 = time.time()

    with table.batch_writer(overwrite_by_pkeys=["PK"]) as batch:
        with open(args.file, "r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) < 12:
                    continue
                cc = (row[0] or "").strip().upper()
                pc = (row[1] or "").strip()
                if not cc or not pc:
                    continue
                if countries and cc not in countries:
                    continue

                place = (row[2] or "").strip()
                admin1_name = (row[3] or "").strip()
                admin1_code = (row[4] or "").strip()
                lat = (row[9] or "").strip()
                lon = (row[10] or "").strip()

                place_key = normalize_name(place)
                item = {
                    "PK": f"{cc}#{pc}",
                    "GSI2PK": f"{cc}#{place_key}",
                    "GSI2SK": pc,
                    "country_code": cc,
                    "postcode": pc,
                    "place_name": place,
                    "admin1_name": admin1_name,
                    "admin1_code": admin1_code,
                    "latitude": lat,
                    "longitude": lon,
                }
                batch.put_item(Item=item)

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
