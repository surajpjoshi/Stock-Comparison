import os
import sys
import time
import gzip
import json
import requests
import pandas as pd

from datetime import date, timedelta, datetime, time as dt_time
from zoneinfo import ZoneInfo
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
# LIVE LTP / MARKET HOURS
# ============================================================

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

LTP_URL = "https://api.upstox.com/v3/market-quote/ltp"
LTP_BATCH_SIZE = 500


def get_live_ltp(instrument_map):
    """Fetch current LTP for NSE equities in batches."""
    items = [
        (symbol, data["instrument_key"])
        for symbol, data in instrument_map.items()
        if data.get("instrument_key")
    ]

    ltp_prices = {}
    failed_batches = 0

    print()
    print("Downloading live Upstox LTP...")

    for start in range(
        0,
        len(items),
        LTP_BATCH_SIZE
    ):
        batch = items[
            start:start + LTP_BATCH_SIZE
        ]

        params = {
            "instrument_key": ",".join(
                key
                for _, key in batch
            )
        }

        try:
            response = requests.get(
                LTP_URL,
                headers=HEADERS,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:
                print(
                    f"LTP batch HTTP "
                    f"{response.status_code}: "
                    f"{response.text[:200]}"
                )
                failed_batches += 1
                continue

            payload = response.json()

            if payload.get("status") != "success":
                print("LTP batch returned non-success status.")
                failed_batches += 1
                continue

            quote_data = (
                payload
                .get("data", {})
            )

            # Build reverse map from instrument key to symbol.
            key_to_symbol = {
                key: symbol
                for symbol, key in batch
            }

            for response_key, quote in quote_data.items():

                symbol = key_to_symbol.get(
                    response_key
                )

                if symbol is None:
                    # Some responses use exchange:symbol as key.
                    symbol = response_key.split(":")[-1].upper()

                last_price = quote.get(
                    "last_price"
                )

                try:
                    last_price = float(
                        last_price
                    )
                except (
                    TypeError,
                    ValueError
                ):
                    continue

                if last_price <= 0:
                    continue

                previous_close = quote.get("cp")

                try:
                    previous_close = (
                        float(previous_close)
                        if previous_close is not None
                        else None
                    )
                except (
                    TypeError,
                    ValueError
                ):
                    previous_close = None

                ltp_prices[symbol] = {
                    "last_price": last_price,
                    "previous_close": previous_close,
                }

        except requests.RequestException as e:
            print(
                f"LTP batch request error: {e}"
            )
            failed_batches += 1

        except Exception as e:
            print(
                f"LTP batch parsing error: {e}"
            )
            failed_batches += 1

    print(
        f"LTP quotes received: "
        f"{len(ltp_prices):,}"
    )

    if failed_batches:
        print(
            f"LTP batches failed: "
            f"{failed_batches}"
        )

    return ltp_prices


# ============================================================
# MAIN
# ============================================================

def get_ist_now():
    """Return current India time."""
    return pd.Timestamp.now(tz=IST)


def is_market_hours(now_ist=None):
    """Return True only during NSE cash-market hours on weekdays."""
    if now_ist is None:
        now_ist = get_ist_now()

    if now_ist.weekday() >= 5:
        return False

    current_time = now_ist.time().replace(tzinfo=None)
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def get_today_close_for_symbol(instrument_key, today):
    """Fetch today's official daily close for one symbol."""
    df = get_historical_closes(
        instrument_key,
        today.strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
    )

    if df is None or df.empty:
        return None

    rows = df[df["Date"] == today]

    if rows.empty:
        return None

    value = rows.iloc[-1]["Close"]

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if value <= 0:
        return None

    return value


def apply_live_ltp(
    price_df,
    symbols,
    instrument_map,
    source_label="LTP",
):
    """Create/update today's row from batched LTP quotes."""
    ltp_data = get_live_ltp(instrument_map)

    if not ltp_data:
        print("No usable LTP quotes received.")
        return price_df, 0

    price_df = price_df.copy()
    price_df["Date"] = pd.to_datetime(price_df["Date"])
    price_df = price_df.set_index("Date")

    today_ts = pd.Timestamp(date.today())

    if today_ts not in price_df.index:
        price_df.loc[today_ts] = pd.NA

    applied = 0

    for symbol in symbols:
        quote = ltp_data.get(symbol)
        if not quote:
            continue

        value = quote.get("last_price")

        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        if value <= 0:
            continue

        if symbol not in price_df.columns:
            price_df[symbol] = pd.NA

        price_df.loc[today_ts, symbol] = value
        applied += 1

    price_df = price_df.sort_index()
    price_df = price_df.reset_index()

    print(
        f"{source_label} values applied: {applied}"
    )

    return price_df, applied


def apply_official_close(
    price_df,
    symbols,
    instrument_map,
):
    """
    Attempt official daily close for today's row.

    Only replace today's values where the official close is available.
    This prevents a missing daily candle from destroying today's LTP.
    """
    price_df = price_df.copy()
    price_df["Date"] = pd.to_datetime(price_df["Date"])
    price_df = price_df.set_index("Date")

    today = date.today()
    today_ts = pd.Timestamp(today)

    if today_ts not in price_df.index:
        price_df.loc[today_ts] = pd.NA

    applied = 0

    print()
    print("=" * 70)
    print("Checking official daily close for today...")
    print("=" * 70)

    for index, symbol in enumerate(symbols, start=1):
        instrument = instrument_map.get(symbol)

        if instrument is None:
            continue

        close = get_today_close_for_symbol(
            instrument["instrument_key"],
            today,
        )

        if close is None:
            print(
                f"[{index:>3}/{len(symbols)}] "
                f"{symbol:<20} CLOSE NOT AVAILABLE"
            )
            continue

        if symbol not in price_df.columns:
            price_df[symbol] = pd.NA

        price_df.loc[today_ts, symbol] = close
        applied += 1

        print(
            f"[{index:>3}/{len(symbols)}] "
            f"{symbol:<20} CLOSE {close:.2f}"
        )

        time.sleep(REQUEST_DELAY)

    price_df = price_df.sort_index()
    price_df = price_df.reset_index()

    print(f"Official close values applied: {applied}")

    return price_df, applied


def main():

    start_time = time.time()

    print()
    print("=" * 70)
    print("       STOCK PRICE MASTER DOWNLOADER")
    print("=" * 70)
    print()

    now_ist = get_ist_now()
    live_mode = is_market_hours(now_ist)

    print("Source  : Upstox")
    print("Market  : NSE")
    print("Interval: Daily")
    print(
        f"Time    : {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )
    print(
        f"Mode    : {'LIVE LTP' if live_mode else 'DAILY CLOSE'}"
    )
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

        # On first run, keep historical downloader behavior.
        # During/after hours, refresh today's row with LTP if available.
        if not price_df.empty:
            price_df, _ = apply_live_ltp(
                price_df,
                symbols,
                instrument_map,
                source_label="INITIAL LTP",
            )

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

        old_dates = set(
            existing_prices["Date"]
            .dt.date
        )

        price_df = existing_prices.copy()

        # ----------------------------------------------------
        # MARKET HOURS: today's row is LIVE LTP only.
        #
        # Do NOT process the official daily close while the
        # NSE cash market is open. The current daily candle is
        # incomplete and may be stale/delayed.
        # ----------------------------------------------------

        if live_mode:

            print()
            print(
                "Market is open — using current Upstox LTP "
                "for today's row only."
            )

            price_df, applied = apply_live_ltp(
                price_df,
                symbols,
                instrument_map,
                source_label="LTP",
            )

            if applied == 0:
                print("WARNING: No LTP values were applied.")

        # ----------------------------------------------------
        # AFTER HOURS:
        #
        # Fetch completed daily data and official close.
        # If a stock's official close is unavailable, use LTP
        # only as a temporary fallback for that stock.
        # ----------------------------------------------------

        else:

            from_date = (
                last_date +
                timedelta(days=1)
            )

            if from_date <= today:

                print()
                print(
                    f"Updating completed data from "
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

                if new_prices:
                    price_df = merge_prices(
                        price_df,
                        new_prices,
                        symbols
                    )

            else:

                missing_symbols = []
                failed_symbols = []

            # Official close attempt.
            price_df, close_applied = apply_official_close(
                price_df,
                symbols,
                instrument_map,
            )

            # Fallback only for symbols whose today's value
            # is still missing. Never overwrite a valid close.
            today_ts = pd.Timestamp(today)

            if today_ts not in pd.to_datetime(
                price_df["Date"]
            ).values:

                price_df["Date"] = pd.to_datetime(
                    price_df["Date"]
                )
                price_df = price_df.set_index("Date")
                price_df.loc[today_ts] = pd.NA
                price_df = price_df.reset_index()

            today_row = (
                price_df["Date"] == today_ts
            )

            missing_today = [
                symbol
                for symbol in symbols
                if symbol in price_df.columns
                and pd.isna(
                    pd.to_numeric(
                        price_df.loc[today_row, symbol],
                        errors="coerce"
                    ).iloc[0]
                )
            ]

            if missing_today:
                print()
                print(
                    f"Official close missing for "
                    f"{len(missing_today)} stocks."
                )
                print(
                    "Using LTP as temporary fallback "
                    "for missing today's values."
                )

                ltp_data = get_live_ltp(
                    instrument_map
                )

                fallback_applied = 0

                for symbol in missing_today:

                    quote = ltp_data.get(symbol)

                    if not quote:
                        continue

                    value = quote.get("last_price")

                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue

                    if value <= 0:
                        continue

                    price_df.loc[
                        today_row,
                        symbol
                    ] = value

                    fallback_applied += 1

                print(
                    f"LTP fallback values applied: "
                    f"{fallback_applied}"
                )

            else:
                print(
                    "Official close available for all "
                    "stocks with data."
                )

        price_df = price_df.sort_values("Date")
        price_df = price_df.drop_duplicates(
            subset=["Date"],
            keep="last"
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
