import json
import os
from datetime import datetime

import pandas as pd


PRICE_FILE = "stock_prices.xlsx"
MASTER_FILE = "stock_master.xlsx"
OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data.json")


def clean_symbol(value):
    if pd.isna(value):
        return ""

    value = str(value).strip()

    if ":" in value:
        value = value.split(":")[-1]

    return value.upper()


def find_column(df, candidates):
    lookup = {str(c).strip().lower(): c for c in df.columns}

    for candidate in candidates:
        key = candidate.lower()

        if key in lookup:
            return lookup[key]

    return None


def load_master():
    print("Loading stock master...")

    df = pd.read_excel(MASTER_FILE)

    print("Master columns:")
    print(list(df.columns))

    sector_col = find_column(
        df,
        [
            "Sector",
            "sector",
        ],
    )

    symbol_col = find_column(
        df,
        [
            "Symbol",
            "symbol",
            "Trading Symbol",
        ],
    )

    company_col = find_column(
        df,
        [
            "Company Name",
            "Company",
            "company_name",
            "Name",
        ],
    )

    if sector_col is None:
        raise ValueError("Sector column not found in stock_master.xlsx")

    if symbol_col is None:
        raise ValueError("Symbol column not found in stock_master.xlsx")

    result = pd.DataFrame()

    result["symbol"] = df[symbol_col].apply(clean_symbol)
    result["sector"] = df[sector_col].fillna("").astype(str).str.strip()

    if company_col:
        result["company"] = (
            df[company_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        result["company"] = result["symbol"]

    result = result[
        (result["symbol"] != "")
        & (result["sector"] != "")
    ]

    # A stock can belong to multiple sectors/indexes.
    # Keep each unique stock + sector combination.
    result = result.drop_duplicates(
        subset=["symbol", "sector"],
        keep="first",
    )

    print(f"Stock-sector records: {len(result)}")
    print(f"Unique sectors: {result['sector'].nunique()}")

    return result


def load_prices():
    print("Loading stock prices...")

    df = pd.read_excel(PRICE_FILE)

    if df.empty:
        raise ValueError("stock_prices.xlsx is empty")

    # First column is expected to be Date
    date_col = df.columns[0]

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    df = df.dropna(subset=[date_col])

    df = df.sort_values(date_col)

    df = df.set_index(date_col)

    # Clean column names
    df.columns = [
        clean_symbol(c)
        for c in df.columns
    ]

    # Convert prices to numeric
    for col in df.columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    print(
        f"Trading days: {len(df)}"
    )

    print(
        f"Price columns: {len(df.columns)}"
    )

    return df


def get_period_dates(prices):
    latest = prices.index.max()

    one_month = latest - pd.DateOffset(months=1)
    three_months = latest - pd.DateOffset(months=3)
    six_months = latest - pd.DateOffset(months=6)

    year_start = pd.Timestamp(
        year=latest.year,
        month=1,
        day=1,
    )

    return {
        "1M": one_month,
        "3M": three_months,
        "6M": six_months,
        "YTD": year_start,
    }


def nearest_date(index, target):
    candidates = index[index >= target]

    if len(candidates):
        return candidates[0]

    return index[0]


def calculate_performance(prices, start_date):
    start = nearest_date(
        prices.index,
        start_date,
    )

    end = prices.index[-1]

    selected = prices.loc[start:end]

    if selected.empty:
        return pd.DataFrame()

    first = selected.iloc[0]

    performance = selected.divide(
        first,
        axis="columns",
    ).subtract(1.0)

    performance = performance * 100

    return performance


def sanitize_for_json(value):
    """Convert pandas/numpy missing or non-finite values to JSON-safe values."""
    if isinstance(value, dict):
        return {
            str(k): sanitize_for_json(v)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [
            sanitize_for_json(v)
            for v in value
        ]

    if isinstance(value, tuple):
        return [
            sanitize_for_json(v)
            for v in value
        ]

    if isinstance(value, float):
        if pd.isna(value) or value in (float("inf"), float("-inf")):
            return None

    return value


def build_data(master, prices):
    periods = get_period_dates(prices)

    output = {
        "generated_at": datetime.now().isoformat(),
        "latest_date": prices.index[-1].strftime("%Y-%m-%d"),
        "sectors": {},
    }

    # Match master stocks with price columns
    available_symbols = set(prices.columns)

    master = master[
        master["symbol"].isin(
            available_symbols
        )
    ].copy()

    print(
        f"Matched stocks: {len(master)}"
    )

    for sector in sorted(
        master["sector"].unique()
    ):
        sector_stocks = master[
            master["sector"] == sector
        ]

        sector_output = {}

        for period_name, start_date in periods.items():

            performance = calculate_performance(
                prices,
                start_date,
            )

            if performance.empty:
                continue

            symbols = [
                s
                for s in sector_stocks["symbol"]
                if s in performance.columns
            ]

            if not symbols:
                continue

            period_perf = performance[
                symbols
            ].copy()

            # Rank by final performance
            final_values = (
                period_perf.iloc[-1]
                .dropna()
                .sort_values(
                    ascending=False
                )
            )

            top5 = list(
                final_values.head(5).index
            )

            top10 = list(
                final_values.head(10).index
            )

            stocks_info = {}

            for _, row in sector_stocks.iterrows():

                symbol = row["symbol"]

                if symbol not in symbols:
                    continue

                stocks_info[symbol] = {
                    "company": row["company"],
                    "performance": round(
                        float(
                            final_values.get(
                                symbol,
                                0
                            )
                        ),
                        2,
                    ),
                }

            # Store ALL data.
            # Browser decides Top 5 / Top 10.
            dates = [
                d.strftime("%Y-%m-%d")
                for d in period_perf.index
            ]

            series = {}

            for symbol in symbols:

                values = (
                    period_perf[symbol]
                    .round(4)
                    .tolist()
                )

                series[symbol] = values

            sector_output[period_name] = {
                "dates": dates,
                "top5": top5,
                "top10": top10,
                "stocks": stocks_info,
                "series": series,
            }

        output["sectors"][sector] = sector_output

        print(
            f"  {sector}: OK"
        )

    return output


def main():

    print("=" * 60)
    print("GENERATING WEB DATA")
    print("=" * 60)

    if not os.path.exists(PRICE_FILE):
        raise FileNotFoundError(
            PRICE_FILE
        )

    if not os.path.exists(MASTER_FILE):
        raise FileNotFoundError(
            MASTER_FILE
        )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    master = load_master()

    prices = load_prices()

    data = build_data(
        master,
        prices,
    )

    # Final JSON safety pass.
    data = sanitize_for_json(data)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        # allow_nan=False guarantees standards-compliant JSON.
        # Any missing numeric values are converted to null before writing.
        json.dump(
            data,
            f,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

    size_mb = (
        os.path.getsize(OUTPUT_FILE)
        / 1024
        / 1024
    )

    print()
    print("=" * 60)
    print("WEB DATA GENERATED")
    print("=" * 60)

    print(
        f"Latest date : "
        f"{data['latest_date']}"
    )

    print(
        f"Sectors     : "
        f"{len(data['sectors'])}"
    )

    print(
        f"File        : "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Size        : "
        f"{size_mb:.2f} MB"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()