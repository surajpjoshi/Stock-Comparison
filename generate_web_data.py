import json
import math
import os
from datetime import datetime

import pandas as pd


PRICE_FILE = "stock_prices.xlsx"
MASTER_FILE = "stock_master.xlsx"
OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data.json")
PERIOD_NAMES = ("1M", "3M", "6M", "YTD")

SECTOR_DISPLAY_NAMES = {
    "nifty100": "Nifty 100",
    "nifty200": "Nifty 200",
    "nifty500": "Nifty 500",
    "nifty500healthcare": "Nifty 500 Healthcare",
    "niftyauto": "Nifty Auto",
    "niftybank": "Nifty Bank",
    "niftycapitalgoods": "Nifty Capital Goods",
    "niftycapitalmarketsindex": "Nifty Capital Markets",
    "niftycement": "Nifty Cement",
    "niftychemicals": "Nifty Chemicals",
    "niftychemicalsindex": "Nifty Chemicals Index",
    "niftycommercialtransportservices": "Nifty Commercial Transport Services",
    "niftycommodities": "Nifty Commodities",
    "niftyconstruction": "Nifty Construction",
    "niftyconsumerdurables": "Nifty Consumer Durables",
    "niftyconsumerservices": "Nifty Consumer Services",
    "niftyenergy": "Nifty Energy",
    "niftyfinancialservices": "Nifty Financial Services",
    "niftyfinancialservices2550": "Nifty Financial Services 25/50",
    "niftyfinancialservicesexbank": "Nifty Financial Services ex-Bank",
    "niftyfmcg": "Nifty FMCG",
    "niftyhealthcare": "Nifty Healthcare",
    "niftyhospitals": "Nifty Hospitals",
    "niftyhousing": "Nifty Housing",
    "niftyhousingfinance": "Nifty Housing Finance",
    "niftyindiaconsumption": "Nifty India Consumption",
    "niftyindiadefence": "Nifty India Defence",
    "niftyindiadigital": "Nifty India Digital",
    "niftyindiafpi150": "Nifty India FPI 150",
    "niftyindiainternetindex": "Nifty India Internet",
    "niftyindiamanufacturing": "Nifty India Manufacturing",
    "niftyindiatourism": "Nifty India Tourism",
    "niftyinfrastructure": "Nifty Infrastructure",
    "niftyinsurance": "Nifty Insurance",
    "niftyit": "Nifty IT",
    "niftymedia": "Nifty Media",
    "niftymetal": "Nifty Metal",
    "niftymicrocap250": "Nifty Microcap 250",
    "niftymidcap150": "Nifty Midcap 150",
    "niftymidcapselect": "Nifty Midcap Select",
    "niftymidsmallfinancialservices": "Nifty MidSmall Financial Services",
    "niftymidsmallhealthcare": "Nifty MidSmall Healthcare",
    "niftymidsmallitandtelecom": "Nifty MidSmall IT & Telecom",
    "niftynbfc": "Nifty NBFC",
    "niftynext50": "Nifty Next 50",
    "niftyoilandgas": "Nifty Oil & Gas",
    "niftypharma": "Nifty Pharma",
    "niftypower": "Nifty Power",
    "niftyprivatebank": "Nifty Private Bank",
    "niftypsubank": "Nifty PSU Bank",
    "niftyrealty": "Nifty Realty",
    "niftyreitsandrealty": "Nifty REITs & Realty",
    "niftyretail": "Nifty Retail",
    "niftyservicessector": "Nifty Services Sector",
    "niftysmallcap250": "Nifty Smallcap 250",
    "niftytelecommunications": "Nifty Telecommunications",
}

# Current Nifty 50 constituent symbols used by the dashboard.
# The basket is used as an equal-weighted price-return proxy because
# stock_prices.xlsx does not contain official Nifty free-float weights.
NIFTY50_SYMBOLS = {
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC",
    "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M",
    "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATASTEEL", "TCS", "TECHM",
    "TITAN", "TRENT", "ULTRACEMCO", "WIPRO", "TMPV",
}


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

    sector_col = find_column(df, ["Sector", "sector"])
    symbol_col = find_column(df, ["Symbol", "symbol", "Trading Symbol"])
    company_col = find_column(
        df,
        ["Company Name", "Company", "company_name", "Name"],
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
            df[company_col].fillna("").astype(str).str.strip()
        )
    else:
        result["company"] = result["symbol"]

    result = result[
        (result["symbol"] != "") & (result["sector"] != "")
    ]

    # A stock can belong to multiple sectors/indexes.
    result = result.drop_duplicates(
        subset=["symbol", "sector"],
        keep="first",
    )

    print(f"Stock-sector records: {len(result)}")
    print(f"Unique sectors: {result['sector'].nunique()}")

    if result["sector"].nunique() < 50:
        raise ValueError(
            f"Stock master contains only {result['sector'].nunique()} sectors. "
            "Refusing to generate website data."
        )

    return result


def load_prices():
    print("Loading stock prices...")

    df = pd.read_excel(PRICE_FILE)

    if df.empty:
        raise ValueError("stock_prices.xlsx is empty")

    date_col = df.columns[0]

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    if df.empty:
        raise ValueError("stock_prices.xlsx has no valid trading dates")

    if df[date_col].duplicated().any():
        duplicates = int(df[date_col].duplicated().sum())
        raise ValueError(f"stock_prices.xlsx contains {duplicates} duplicate dates")

    df = df.set_index(date_col)

    df.columns = [clean_symbol(c) for c in df.columns]

    if any(not c for c in df.columns):
        raise ValueError("stock_prices.xlsx contains an empty price column name")

    if len(set(df.columns)) != len(df.columns):
        raise ValueError("stock_prices.xlsx contains duplicate stock symbols")

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if len(df) < 100:
        raise ValueError(
            f"Only {len(df)} trading days found. Refusing to publish incomplete price history."
        )

    if len(df.columns) < 700:
        raise ValueError(
            f"Only {len(df.columns)} price columns found. Refusing to publish incomplete stock data."
        )

    positive_values = df.where(df > 0)
    latest_valid = int(positive_values.iloc[-1].notna().sum())
    minimum_latest = math.floor(len(df.columns) * 0.90)

    if latest_valid < minimum_latest:
        raise ValueError(
            f"Latest trading day has only {latest_valid}/{len(df.columns)} valid prices; "
            f"minimum required is {minimum_latest}."
        )

    if not df.index.is_monotonic_increasing:
        raise ValueError("Trading dates are not sorted correctly")

    print(f"Trading days: {len(df)}")
    print(f"Price columns: {len(df.columns)}")
    print(f"Latest valid prices: {latest_valid}/{len(df.columns)}")

    return df


def get_period_dates(prices):
    latest = prices.index.max()

    return {
        "1M": latest - pd.DateOffset(months=1),
        "3M": latest - pd.DateOffset(months=3),
        "6M": latest - pd.DateOffset(months=6),
        "YTD": pd.Timestamp(year=latest.year, month=1, day=1),
    }


def nearest_date(index, target):
    candidates = index[index >= target]
    return candidates[0] if len(candidates) else index[0]


def calculate_performance(prices, start_date):
    start = nearest_date(prices.index, start_date)
    end = prices.index[-1]
    selected = prices.loc[start:end]

    if selected.empty:
        return pd.DataFrame()

    first = selected.iloc[0]
    first = first.where(first > 0)

    performance = selected.divide(first, axis="columns").subtract(1.0) * 100
    performance = performance.replace([float("inf"), float("-inf")], pd.NA)

    return performance


def build_equal_weighted_benchmark(performance, symbols):
    available = [s for s in symbols if s in performance.columns]

    if not available:
        return None

    basket = performance[available]
    values = basket.mean(axis=1, skipna=True)
    coverage = basket.notna().sum(axis=1)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in values.index],
        "series": [None if pd.isna(v) else round(float(v), 4) for v in values],
        "performance": (
            None if pd.isna(values.iloc[-1]) else round(float(values.iloc[-1]), 2)
        ),
        "coverage": int(coverage.iloc[-1]),
        "constituents": len(available),
        "method": "Equal-weighted price-return proxy",
    }


def build_data(master, prices):
    periods = get_period_dates(prices)
    available_symbols = set(prices.columns)

    master = master[master["symbol"].isin(available_symbols)].copy()

    unique_symbols = master["symbol"].nunique()
    print(f"Matched stocks: {len(master)}")
    print(f"Matched unique symbols: {unique_symbols}")

    if unique_symbols < 700:
        raise ValueError(
            f"Only {unique_symbols} unique master symbols matched prices. "
            "Refusing to publish incomplete website data."
        )

    performance_by_period = {
        period_name: calculate_performance(prices, start_date)
        for period_name, start_date in periods.items()
    }

    output = {
        "generated_at": datetime.now().isoformat(),
        "latest_date": prices.index[-1].strftime("%Y-%m-%d"),
        "sector_labels": {
            key: SECTOR_DISPLAY_NAMES.get(key, key)
            for key in master["sector"].unique()
        },
        "sectors": {},
        "sector_performance": {},
        "benchmarks": {
            "nifty50": {
                "label": "Nifty 50",
                "method": "Equal-weighted price-return proxy",
                "periods": {},
            },
            "nifty500": {
                "label": "Nifty 500",
                "method": "Equal-weighted price-return proxy",
                "periods": {},
            },
        },
    }

    # Build Nifty 50 and Nifty 500 benchmark series.
    for period_name, performance in performance_by_period.items():
        output["benchmarks"]["nifty50"]["periods"][period_name] = (
            build_equal_weighted_benchmark(performance, NIFTY50_SYMBOLS)
        )

        nifty500_symbols = (
            master.loc[master["sector"] == "nifty500", "symbol"]
            .drop_duplicates()
            .tolist()
        )

        output["benchmarks"]["nifty500"]["periods"][period_name] = (
            build_equal_weighted_benchmark(performance, nifty500_symbols)
        )

    # Build sector-level performance ranking and stock-level data.
    for sector in sorted(master["sector"].unique()):
        sector_stocks = master[master["sector"] == sector]
        sector_label = SECTOR_DISPLAY_NAMES.get(sector, sector)
        sector_output = {}

        for period_name, performance in performance_by_period.items():
            symbols = [
                s
                for s in sector_stocks["symbol"].drop_duplicates()
                if s in performance.columns
            ]

            if not symbols:
                continue

            period_perf = performance[symbols].copy()

            final_values = (
                period_perf.iloc[-1]
                .dropna()
                .sort_values(ascending=False)
            )

            top5 = list(final_values.head(5).index)
            top10 = list(final_values.head(10).index)

            stocks_info = {}

            for _, row in sector_stocks.iterrows():
                symbol = row["symbol"]

                if symbol not in symbols:
                    continue

                value = final_values.get(symbol)
                stocks_info[symbol] = {
                    "company": row["company"],
                    "performance": (
                        None if pd.isna(value) else round(float(value), 2)
                    ),
                }

            dates = [d.strftime("%Y-%m-%d") for d in period_perf.index]

            series = {}
            for symbol in symbols:
                values = period_perf[symbol].tolist()
                series[symbol] = [
                    None if pd.isna(v) else round(float(v), 4)
                    for v in values
                ]

            sector_benchmark = build_equal_weighted_benchmark(
                performance,
                symbols,
            )

            sector_output[period_name] = {
                "dates": dates,
                "top5": top5,
                "top10": top10,
                "stocks": stocks_info,
                "series": series,
                "sector_benchmark": sector_benchmark,
            }

        output["sectors"][sector] = sector_output

        print(f"  {sector}: OK")

    # Strongest -> weakest sector ranking for every period.
    for period_name, performance in performance_by_period.items():
        ranking = []

        for sector in sorted(master["sector"].unique()):
            symbols = [
                s
                for s in master.loc[
                    master["sector"] == sector, "symbol"
                ].drop_duplicates()
                if s in performance.columns
            ]

            if not symbols:
                continue

            value = performance[symbols].iloc[-1].mean(skipna=True)

            if pd.isna(value):
                continue

            ranking.append(
                {
                    "sector": sector,
                    "name": SECTOR_DISPLAY_NAMES.get(sector, sector),
                    "performance": round(float(value), 2),
                    "stocks": len(symbols),
                }
            )

        ranking.sort(key=lambda item: item["performance"], reverse=True)
        output["sector_performance"][period_name] = ranking

    return output


def sanitize_for_json(value):
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}

    if isinstance(value, list):
        return [sanitize_for_json(v) for v in value]

    if isinstance(value, tuple):
        return [sanitize_for_json(v) for v in value]

    if isinstance(value, float):
        if not math.isfinite(value):
            return None

    return value


def validate_data_structure(data):
    if not data.get("latest_date"):
        raise ValueError("Generated data has no latest_date")

    sectors = data.get("sectors", {})
    if len(sectors) < 50:
        raise ValueError(f"Generated data contains only {len(sectors)} sectors")

    for required in ("nifty100", "nifty200", "nifty500"):
        if required not in sectors:
            raise ValueError(f"Required sector missing: {required}")

    benchmarks = data.get("benchmarks", {})
    for benchmark in ("nifty50", "nifty500"):
        if benchmark not in benchmarks:
            raise ValueError(f"Required benchmark missing: {benchmark}")

        for period in PERIOD_NAMES:
            item = benchmarks[benchmark]["periods"].get(period)
            if not item or not item.get("dates") or not item.get("series"):
                raise ValueError(
                    f"Benchmark {benchmark} has no valid {period} series"
                )

    sector_ranking = data.get("sector_performance", {})
    for period in PERIOD_NAMES:
        if len(sector_ranking.get(period, [])) < 50:
            raise ValueError(
                f"Sector ranking for {period} contains fewer than 50 sectors"
            )


def main():
    print("=" * 60)
    print("GENERATING WEB DATA")
    print("=" * 60)

    if not os.path.exists(PRICE_FILE):
        raise FileNotFoundError(PRICE_FILE)

    if not os.path.exists(MASTER_FILE):
        raise FileNotFoundError(MASTER_FILE)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    master = load_master()
    prices = load_prices()

    data = build_data(master, prices)
    data = sanitize_for_json(data)
    validate_data_structure(data)

    # Write atomically: a failed generation never destroys the previous
    # known-good docs/data.json.
    temp_file = OUTPUT_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )

    # Re-read the exact file that will be published.
    with open(temp_file, "r", encoding="utf-8") as f:
        json.load(f)

    os.replace(temp_file, OUTPUT_FILE)

    size_mb = os.path.getsize(OUTPUT_FILE) / 1024 / 1024

    print()
    print("=" * 60)
    print("WEB DATA GENERATED")
    print("=" * 60)
    print(f"Latest date : {data['latest_date']}")
    print(f"Sectors     : {len(data['sectors'])}")
    print(f"File        : {OUTPUT_FILE}")
    print(f"Size        : {size_mb:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
