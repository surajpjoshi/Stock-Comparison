import json
import math
import os
import sys
from datetime import datetime


DATA_FILE = os.path.join("docs", "data.json")
REQUIRED_SECTORS = {"nifty100", "nifty200", "nifty500"}
PERIODS = ("1M", "3M", "6M", "YTD")


def fail(message):
    print(f"VALIDATION FAILED: {message}")
    sys.exit(1)


def check_series(name, dates, values):
    if not isinstance(dates, list) or not isinstance(values, list):
        fail(f"{name} dates/series are not arrays")

    if len(dates) == 0 or len(dates) != len(values):
        fail(f"{name} has mismatched or empty dates/series")

    for value in values:
        if value is None:
            continue

        if not isinstance(value, (int, float)) or not math.isfinite(value):
            fail(f"{name} contains invalid numeric value: {value}")


def main():
    print("=" * 60)
    print("VALIDATING WEBSITE DATA")
    print("=" * 60)

    if not os.path.exists(DATA_FILE):
        fail(f"{DATA_FILE} does not exist")

    size_mb = os.path.getsize(DATA_FILE) / 1024 / 1024
    if size_mb > 20:
        fail(f"{DATA_FILE} is unexpectedly large: {size_mb:.2f} MB")

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        fail(f"invalid JSON: {exc}")

    if not data.get("latest_date"):
        fail("latest_date is missing")

    try:
        datetime.strptime(data["latest_date"], "%Y-%m-%d")
    except ValueError:
        fail(f"invalid latest_date: {data['latest_date']}")

    sectors = data.get("sectors")
    if not isinstance(sectors, dict) or len(sectors) < 50:
        fail("sector count is unexpectedly low")

    missing = REQUIRED_SECTORS - set(sectors)
    if missing:
        fail(f"required sectors missing: {sorted(missing)}")

    labels = data.get("sector_labels", {})
    if len(labels) < len(sectors):
        fail("sector display labels are incomplete")

    for sector, sector_data in sectors.items():
        for period in PERIODS:
            item = sector_data.get(period)
            if not item:
                fail(f"{sector} is missing {period}")

            check_series(
                f"{sector}/{period}",
                item.get("dates"),
                item.get("sector_benchmark", {}).get("series"),
            )

            for symbol, values in item.get("series", {}).items():
                check_series(
                    f"{sector}/{period}/{symbol}",
                    item.get("dates"),
                    values,
                )

    benchmarks = data.get("benchmarks", {})
    for benchmark in ("nifty50", "nifty500"):
        if benchmark not in benchmarks:
            fail(f"missing benchmark: {benchmark}")

        periods = benchmarks[benchmark].get("periods", {})
        for period in PERIODS:
            item = periods.get(period)
            if not item:
                fail(f"{benchmark} is missing {period}")

            check_series(
                f"{benchmark}/{period}",
                item.get("dates"),
                item.get("series"),
            )

            coverage = item.get("coverage", 0)
            if benchmark == "nifty50" and coverage < 40:
                fail(f"Nifty 50 benchmark coverage is only {coverage}")
            if benchmark == "nifty500" and coverage < 400:
                fail(f"Nifty 500 benchmark coverage is only {coverage}")

    rankings = data.get("sector_performance", {})
    for period in PERIODS:
        ranking = rankings.get(period)
        if not isinstance(ranking, list) or len(ranking) < 50:
            fail(f"sector ranking for {period} is incomplete")

        values = [row.get("performance") for row in ranking]
        if any(
            value is not None
            and (not isinstance(value, (int, float)) or not math.isfinite(value))
            for value in values
        ):
            fail(f"sector ranking for {period} contains invalid numbers")

    print(f"JSON size    : {size_mb:.2f} MB")
    print(f"Latest date  : {data['latest_date']}")
    print(f"Sectors      : {len(sectors)}")
    print("Benchmarks   : Nifty 50 + Nifty 500")
    print("Status       : PASS")
    print("=" * 60)


if __name__ == "__main__":
    main()
