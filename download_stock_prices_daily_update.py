import os
import sys
import time
import gzip
import json
import requests
import pandas as pd

from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "stock_master.xlsx"
OUTPUT_FILE = "stock_prices.xlsx"

# Last 1 year
LOOKBACK_DAYS = 365

# Upstox NSE instrument master
INSTRUMENT_URL = (
    "https://assets.upstox.com/"
    "market-quote/instruments/exchange/NSE.json.gz"
)

# Current Upstox V3 Historical Candle API
HISTORICAL_URL = (
    "https://api.upstox.com/v3/historical-candle"
)

REQUEST_TIMEOUT = 30

# Small delay between requests
REQUEST_DELAY = 0.15


# ============================================================
# LOAD TOKEN
# ============================================================

load_dotenv()

ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    print()
    print("ERROR: UPSTOX_ACCESS_TOKEN not found.")
    print()
    print("Create a .env file containing:")
    print()
    print("UPSTOX_ACCESS_TOKEN=your_token_here")
    print()
    sys.exit(1)


# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}",
}


# ============================================================
# LOAD STOCK MASTER
# ============================================================

def load_stock_master():

    print()
    print("=" * 70)
    print("Loading stock master...")
    print("=" * 70)

    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found.")
        sys.exit(1)

    df = pd.read_excel(INPUT_FILE)

    # Clean column names
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    # Find Symbol column
    symbol_column = None

    for col in df.columns:
        if col.lower() == "symbol":
            symbol_column = col
            break

    if symbol_column is None:
        print()
        print("ERROR: Could not find 'Symbol' column.")
        print("Available columns:")
        print(list(df.columns))
        sys.exit(1)

    # Keep non-empty symbols
    df[symbol_column] = (
        df[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df = df[
        (df[symbol_column] != "") &
        (df[symbol_column] != "NAN")
    ].copy()

    # Remove duplicates
    df = df.drop_duplicates(
        subset=[symbol_column]
    )

    symbols = df[symbol_column].tolist()

    print(f"Stocks found: {len(symbols)}")

    return df, symbols, symbol_column


# ============================================================
# DOWNLOAD UPSTOX INSTRUMENT MASTER
# ============================================================

def load_upstox_instruments():

    print()
    print("=" * 70)
    print("Downloading Upstox NSE instrument master...")
    print("=" * 70)

    try:

        response = requests.get(
            INSTRUMENT_URL,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        raw_data = gzip.decompress(
            response.content
        )

        instruments = json.loads(
            raw_data.decode("utf-8")
        )

    except Exception as e:

        print()
        print("ERROR downloading Upstox instruments:")
        print(e)
        sys.exit(1)

    print(
        f"Total instruments received: "
        f"{len(instruments):,}"
    )

    # We only need NSE equity instruments
    instrument_map = {}

    for item in instruments:

        if item.get("segment") != "NSE_EQ":
            continue

        if item.get("instrument_type") != "EQ":
            continue

        symbol = str(
            item.get("trading_symbol", "")
        ).strip().upper()

        instrument_key = item.get(
            "instrument_key"
        )

        if not symbol or not instrument_key:
            continue

        instrument_map[symbol] = {
            "instrument_key": instrument_key,
            "name": item.get("name", ""),
            "isin": item.get("isin", ""),
        }

    print(
        f"NSE equity instruments mapped: "
        f"{len(instrument_map):,}"
    )

    return instrument_map


# ============================================================
# GET HISTORICAL DATA
# ============================================================

def get_historical_closes(
    instrument_key,
    from_date,
    to_date
):

    url = (
        f"{HISTORICAL_URL}/"
        f"{instrument_key}/"
        f"days/1/"
        f"{to_date}/"
        f"{from_date}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code != 200:

            print(
                f"HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

            return None

        payload = response.json()

        if payload.get("status") != "success":
            return None

        candles = (
            payload
            .get("data", {})
            .get("candles", [])
        )

        if not candles:
            return None

        rows = []

        for candle in candles:

            # Upstox candle format:
            #
            # [
            #   timestamp,
            #   open,
            #   high,
            #   low,
            #   close,
            #   volume,
            #   open_interest
            # ]

            if len(candle) < 5:
                continue

            timestamp = candle[0]
            close = candle[4]

            if close is None:
                continue

            # Convert timestamp to date
            dt = pd.to_datetime(
                timestamp
            )

            trading_date = dt.date()

            rows.append(
                {
                    "Date": trading_date,
                    "Close": float(close),
                }
            )

        if not rows:
            return None

        df = pd.DataFrame(rows)

        df = df.drop_duplicates(
            subset=["Date"]
        )

        df = df.sort_values(
            "Date"
        )

        return df

    except requests.RequestException as e:

        print(
            f"Request error: {e}"
        )

        return None

    except Exception as e:

        print(
            f"Parsing error: {e}"
        )

        return None



# ============================================================
# LOAD EXISTING PRICE FILE
# ============================================================

def load_existing_prices():

    if not os.path.exists(OUTPUT_FILE):
        return None

    print()
    print("=" * 70)
    print("Loading existing price file...")
    print("=" * 70)

    try:
        df = pd.read_excel(
            OUTPUT_FILE,
            sheet_name="Prices"
        )
    except Exception as e:
        print(f"ERROR reading {OUTPUT_FILE}: {e}")
        sys.exit(1)

    if "Date" not in df.columns:
        print("ERROR: Date column not found in existing price file.")
        sys.exit(1)

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce"
    )

    df = df.dropna(subset=["Date"])
    df = df.drop_duplicates(
        subset=["Date"],
        keep="last"
    )
    df = df.sort_values("Date")

    return df


# ============================================================
# DOWNLOAD STOCK DATA
# ============================================================

def download_prices(
    symbols,
    instrument_map,
    from_date,
    to_date
):

    prices = {}
    missing_symbols = []
    failed_symbols = []

    total = len(symbols)

    from_date_str = from_date.strftime("%Y-%m-%d")
    to_date_str = to_date.strftime("%Y-%m-%d")

    print()
    print("=" * 70)
    print("Downloading daily prices...")
    print("=" * 70)

    print(
        f"Date range: {from_date_str} → {to_date_str}"
    )

    for index, symbol in enumerate(
        symbols,
        start=1
    ):

        print(
            f"[{index:>3}/{total}] "
            f"{symbol:<20}",
            end=" "
        )

        instrument = instrument_map.get(
            symbol
        )

        if instrument is None:

            print("NOT FOUND")

            missing_symbols.append(
                symbol
            )

            continue

        instrument_key = (
            instrument["instrument_key"]
        )

        df = get_historical_closes(
            instrument_key,
            from_date_str,
            to_date_str
        )

        if df is None or df.empty:

            print("NO NEW DATA")

            continue

        # Convert to Series
        series = df.set_index(
            "Date"
        )["Close"]

        series.index = pd.to_datetime(
            series.index
        )

        # IMPORTANT:
        # Only accept dates requested by this update.
        series = series[
            (series.index.date >= from_date) &
            (series.index.date <= to_date)
        ]

        if series.empty:

            print("NO NEW DATA")

            continue

        prices[symbol] = series

        dates_received = [
            pd.Timestamp(d).strftime("%d-%b-%Y")
            for d in series.index
        ]

        print(
            f"NEW DATA: "
            f"{', '.join(dates_received)}"
        )

        time.sleep(
            REQUEST_DELAY
        )

    return (
        prices,
        missing_symbols,
        failed_symbols
    )


# ============================================================
# MERGE PRICES
# ============================================================

def merge_prices(
    existing_df,
    new_prices,
    symbols
):

    # --------------------------------------------------------
    # FIRST RUN
    # --------------------------------------------------------

    if existing_df is None:

        if not new_prices:
            return pd.DataFrame()

        price_df = pd.DataFrame(
            new_prices
        )

        price_df.index.name = "Date"

        price_df = price_df.sort_index()

        price_df = price_df.reset_index()

    # --------------------------------------------------------
    # INCREMENTAL UPDATE
    # --------------------------------------------------------

    else:

        price_df = existing_df.copy()

        price_df["Date"] = pd.to_datetime(
            price_df["Date"]
        )

        price_df = price_df.set_index(
            "Date"
        )

        # Ensure all current master symbols exist.
        for symbol in symbols:

            if symbol not in price_df.columns:
                price_df[symbol] = pd.NA

        # Add/update only newly downloaded dates.
        for symbol, series in new_prices.items():

            for dt, close in series.items():

                dt = pd.Timestamp(dt)

                if dt not in price_df.index:
                    price_df.loc[dt] = pd.NA

                price_df.loc[
                    dt,
                    symbol
                ] = close

        price_df = price_df.sort_index()

        # Never allow duplicate dates.
        price_df = price_df[
            ~price_df.index.duplicated(
                keep="last"
            )
        ]

        price_df = price_df.reset_index()

    # Date first
    other_columns = [
        c
        for c in price_df.columns
        if c != "Date"
    ]

    price_df = price_df[
        ["Date"] + other_columns
    ]

    # Round price values
    numeric_columns = [
        c
        for c in price_df.columns
        if c != "Date"
    ]

    if numeric_columns:

        price_df[numeric_columns] = (
            price_df[numeric_columns]
            .apply(
                pd.to_numeric,
                errors="coerce"
            )
            .round(2)
        )

    return price_df


# ============================================================
# SAVE EXCEL
# ============================================================

def save_price_file(
    price_df,
    symbols,
    instrument_map,
    missing_symbols,
    failed_symbols
):

    print()
    print("=" * 70)
    print("Saving master price table...")
    print("=" * 70)

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
        mode="w"
    ) as writer:

        price_df.to_excel(
            writer,
            sheet_name="Prices",
            index=False
        )

        status_rows = []

        for symbol in symbols:

            instrument = instrument_map.get(
                symbol
            )

            if symbol in missing_symbols:
                status = "Instrument Not Found"

            elif symbol in failed_symbols:
                status = "Download Failed"

            else:
                status = "Downloaded"

            status_rows.append(
                {
                    "Symbol": symbol,
                    "Status": status,
                    "Instrument Key": (
                        instrument["instrument_key"]
                        if instrument
                        else ""
                    ),
                }
            )

        status_df = pd.DataFrame(
            status_rows
        )

        status_df.to_excel(
            writer,
            sheet_name="Status",
            index=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    print()
    print("=" * 70)
    print("       STOCK PRICE MASTER DOWNLOADER")
    print("=" * 70)
    print()

    print("Source  : Upstox")
    print("Market  : NSE")
    print("Interval: Daily")
    print()

    # --------------------------------------------------------
    # Load stock master
    # --------------------------------------------------------

    stock_master, symbols, symbol_column = (
        load_stock_master()
    )

    # --------------------------------------------------------
    # Load current Upstox instrument master
    # --------------------------------------------------------

    instrument_map = (
        load_upstox_instruments()
    )

    # --------------------------------------------------------
    # Existing price file?
    # --------------------------------------------------------

    existing_prices = (
        load_existing_prices()
    )

    today = date.today()

    # ========================================================
    # FIRST RUN
    # ========================================================

    if existing_prices is None:

        print()
        print("=" * 70)
        print("FIRST RUN - DOWNLOADING 1 YEAR HISTORY")
        print("=" * 70)

        from_date = (
            today -
            timedelta(days=LOOKBACK_DAYS)
        )

        (
            new_prices,
            missing_symbols,
            failed_symbols
        ) = download_prices(
            symbols,
            instrument_map,
            from_date,
            today
        )

        price_df = merge_prices(
            None,
            new_prices,
            symbols
        )

        old_dates = set()

    # ========================================================
    # DAILY INCREMENTAL UPDATE
    # ========================================================

    else:

        last_date = (
            existing_prices["Date"]
            .max()
            .date()
        )

        print()
        print("=" * 70)
        print("EXISTING PRICE FILE FOUND")
        print("=" * 70)

        print(
            f"Latest stored date: {last_date}"
        )

        print(
            f"Today:              {today}"
        )

        # Remember dates before update so we can report
        # exactly what was added.
        old_dates = set(
            existing_prices["Date"]
            .dt.date
        )

        # ----------------------------------------------------
        # Only request dates AFTER the latest stored date.
        # ----------------------------------------------------

        from_date = (
            last_date +
            timedelta(days=1)
        )

        if from_date > today:

            print()
            print(
                "No new date available for update."
            )

            return

        print()
        print(
            f"Updating from "
            f"{from_date} → {today}"
        )

        (
            new_prices,
            missing_symbols,
            failed_symbols
        ) = download_prices(
            symbols,
            instrument_map,
            from_date,
            today
        )

        price_df = merge_prices(
            existing_prices,
            new_prices,
            symbols
        )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if price_df.empty:

        print()
        print(
            "ERROR: No price data available."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_price_file(
        price_df,
        symbols,
        instrument_map,
        missing_symbols,
        failed_symbols
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    elapsed = (
        time.time() -
        start_time
    )

    latest_date = (
        price_df["Date"]
        .max()
        .strftime("%d-%b-%Y")
    )

    stocks_with_data = sum(
        1
        for symbol in symbols
        if symbol in price_df.columns
        and price_df[symbol].notna().any()
    )

    new_dates = sorted(
        set(
            pd.to_datetime(
                price_df["Date"]
            ).dt.date
        ) - old_dates
    )

    print()
    print("=" * 70)
    print("DOWNLOAD / UPDATE COMPLETE")
    print("=" * 70)

    print(
        f"Stocks requested : {len(symbols)}"
    )

    print(
        f"Stocks with data  : {stocks_with_data}"
    )

    print(
        f"Not found         : "
        f"{len(missing_symbols)}"
    )

    print(
        f"Failed            : "
        f"{len(failed_symbols)}"
    )

    print(
        f"Trading days      : "
        f"{len(price_df)}"
    )

    print(
        f"Latest date       : "
        f"{latest_date}"
    )

    print(
        f"Excel file        : "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Time taken        : "
        f"{elapsed:.1f} seconds"
    )

    if new_dates:

        print()
        print("NEW DATES ADDED:")

        for dt in new_dates:

            print(
                f"  - {dt.strftime('%d-%b-%Y')}"
            )

    else:

        print()
        print("NO NEW TRADING DAY ADDED.")

        print(
            "The latest completed Upstox daily "
            "candle is not newer than the Excel data."
        )

    if missing_symbols:

        print()
        print("NOT FOUND SYMBOLS:")

        for symbol in missing_symbols:

            print(
                f"  - {symbol}"
            )

    if failed_symbols:

        print()
        print("FAILED SYMBOLS:")

        for symbol in failed_symbols:

            print(
                f"  - {symbol}"
            )

    print()
    print("Done.")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
