import pandas as pd
import plotly.graph_objects as go

from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

MASTER_FILE = "stock_master.xlsx"
PRICE_FILE = "stock_prices.xlsx"

OUTPUT_DIR = Path("sector_charts")
OUTPUT_DIR.mkdir(exist_ok=True)

DEFAULT_SECTOR = "nifty500"
DEFAULT_PERIOD = "1M"
DEFAULT_STOCK_COUNT = 5


# ============================================================
# PERIOD SETTINGS
# ============================================================

PERIOD_DAYS = {
    "1M": 31,
    "3M": 92,
    "6M": 183,
    "YTD": None,
}


# ============================================================
# LOAD MASTER STOCK FILE
# ============================================================

def load_master():

    print("Loading master stock file...")

    if not Path(MASTER_FILE).exists():
        raise FileNotFoundError(
            f"{MASTER_FILE} not found."
        )

    df = pd.read_excel(
        MASTER_FILE
    )

    # Clean column names
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required_columns = [
        "Sector",
        "Symbol"
    ]

    for column in required_columns:

        if column not in df.columns:

            raise ValueError(
                f"Required column '{column}' "
                f"not found in {MASTER_FILE}."
            )

    # --------------------------------------------------------
    # Clean Sector
    # --------------------------------------------------------

    df["Sector"] = (
        df["Sector"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Clean Symbol
    # --------------------------------------------------------

    df["Symbol"] = (
        df["Symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # --------------------------------------------------------
    # Remove blank values
    # --------------------------------------------------------

    df = df[
        (df["Sector"] != "") &
        (df["Sector"].str.upper() != "NAN") &
        (df["Symbol"] != "") &
        (df["Symbol"].str.upper() != "NAN")
    ].copy()

    # --------------------------------------------------------
    # Remove duplicate Sector + Symbol
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "Sector",
            "Symbol"
        ]
    )

    return df


# ============================================================
# LOAD PRICE FILE
# ============================================================

def load_prices():

    print("Loading price file...")

    if not Path(PRICE_FILE).exists():

        raise FileNotFoundError(
            f"{PRICE_FILE} not found."
        )

    df = pd.read_excel(
        PRICE_FILE,
        sheet_name="Prices"
    )

    # Clean column names
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    # --------------------------------------------------------
    # Date column
    # --------------------------------------------------------

    if "Date" not in df.columns:

        raise ValueError(
            "Date column not found in "
            f"{PRICE_FILE}."
        )

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["Date"]
    )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        "Date"
    )

    # --------------------------------------------------------
    # Remove duplicate dates
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=["Date"],
        keep="last"
    )

    return df


# ============================================================
# GET AVAILABLE SECTORS
# ============================================================

def get_sectors(master):

    sectors = (
        master["Sector"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    sectors = sorted(
        sectors,
        key=lambda x: x.lower()
    )

    return sectors


# ============================================================
# FIND SECTOR
# ============================================================

def find_sector(
    sectors,
    user_input
):

    # --------------------------------------------------------
    # Empty input = default
    # --------------------------------------------------------

    if not user_input:

        for sector in sectors:

            if (
                sector.lower()
                == DEFAULT_SECTOR.lower()
            ):
                return sector

        return sectors[0]

    # --------------------------------------------------------
    # Number selection
    # --------------------------------------------------------

    if user_input.isdigit():

        index = int(
            user_input
        ) - 1

        if (
            index < 0
            or index >= len(sectors)
        ):

            raise ValueError(
                "Invalid sector number."
            )

        return sectors[index]

    # --------------------------------------------------------
    # Exact case-insensitive match
    # --------------------------------------------------------

    for sector in sectors:

        if (
            sector.lower()
            == user_input.lower()
        ):

            return sector

    raise ValueError(
        f"Sector '{user_input}' "
        f"not found."
    )


# ============================================================
# GET PERIOD START DATE
# ============================================================

def get_period_start_date(
    prices,
    period
):

    last_date = prices["Date"].max()

    # --------------------------------------------------------
    # YTD
    # --------------------------------------------------------

    if period == "YTD":

        return datetime(
            last_date.year,
            1,
            1
        )

    # --------------------------------------------------------
    # Other periods
    # --------------------------------------------------------

    days = PERIOD_DAYS[
        period
    ]

    return (
        last_date
        - pd.Timedelta(
            days=days
        )
    )


# ============================================================
# GET SECTOR STOCKS
# ============================================================

def get_sector_stocks(
    master,
    sector
):

    sector_df = master[
        master["Sector"].str.lower()
        == sector.lower()
    ].copy()

    if sector_df.empty:

        raise ValueError(
            f"No stocks found for sector: "
            f"{sector}"
        )

    symbols = (
        sector_df["Symbol"]
        .drop_duplicates()
        .tolist()
    )

    return symbols


# ============================================================
# PREPARE SECTOR DATA
# ============================================================

def prepare_sector_data(
    master,
    prices,
    sector,
    period,
    stock_count
):

    print()
    print("=" * 70)
    print("Preparing sector data...")
    print("=" * 70)

    # --------------------------------------------------------
    # Get stocks from Sector column
    # --------------------------------------------------------

    sector_symbols = get_sector_stocks(
        master,
        sector
    )

    print(
        f"Stocks in sector: "
        f"{len(sector_symbols)}"
    )

    # --------------------------------------------------------
    # Check which stocks exist in price file
    # --------------------------------------------------------

    price_columns = set(
        prices.columns
    )

    available_symbols = [
        symbol
        for symbol in sector_symbols
        if symbol in price_columns
    ]

    missing_symbols = [
        symbol
        for symbol in sector_symbols
        if symbol not in price_columns
    ]

    print(
        f"Stocks with price data: "
        f"{len(available_symbols)}"
    )

    if missing_symbols:

        print(
            f"Missing price data: "
            f"{len(missing_symbols)}"
        )

    if not available_symbols:

        raise ValueError(
            "None of the stocks in this sector "
            "exist in stock_prices.xlsx."
        )

    # --------------------------------------------------------
    # Period
    # --------------------------------------------------------

    start_date = get_period_start_date(
        prices,
        period
    )

    end_date = prices["Date"].max()

    print(
        f"Period start: "
        f"{start_date.strftime('%d-%b-%Y')}"
    )

    print(
        f"Period end: "
        f"{end_date.strftime('%d-%b-%Y')}"
    )

    # --------------------------------------------------------
    # Filter price data
    # --------------------------------------------------------

    period_df = prices[
        (prices["Date"] >= start_date) &
        (prices["Date"] <= end_date)
    ].copy()

    period_df = period_df.sort_values(
        "Date"
    )

    if period_df.empty:

        raise ValueError(
            "No price data available "
            "for selected period."
        )

    # --------------------------------------------------------
    # Calculate final return for ranking
    # --------------------------------------------------------

    ranking_data = []

    stock_series = {}

    for symbol in available_symbols:

        series = (
            period_df[
                [
                    "Date",
                    symbol
                ]
            ]
            .dropna(
                subset=[symbol]
            )
            .copy()
        )

        if series.empty:
            continue

        # First available trading-day close
        first_price = float(
            series.iloc[0][symbol]
        )

        # Last available close
        last_price = float(
            series.iloc[-1][symbol]
        )

        if first_price <= 0:
            continue

        # ----------------------------------------------------
        # Return %
        # ----------------------------------------------------

        final_return = (
            (
                last_price
                / first_price
            ) - 1
        ) * 100

        ranking_data.append(
            {
                "Symbol": symbol,
                "Return": final_return,
                "StartPrice": first_price,
                "EndPrice": last_price,
                "StartDate": series.iloc[0]["Date"],
                "EndDate": series.iloc[-1]["Date"],
            }
        )

        stock_series[symbol] = series

    # --------------------------------------------------------
    # Ranking dataframe
    # --------------------------------------------------------

    ranking_df = pd.DataFrame(
        ranking_data
    )

    if ranking_df.empty:

        raise ValueError(
            "Could not calculate returns "
            "for any stock."
        )

    ranking_df = ranking_df.sort_values(
        "Return",
        ascending=False
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Select stocks
    # --------------------------------------------------------

    if str(stock_count).lower() == "all":

        selected_df = ranking_df.copy()

    else:

        selected_df = ranking_df.head(
            int(stock_count)
        ).copy()

    selected_symbols = (
        selected_df["Symbol"]
        .tolist()
    )

    # --------------------------------------------------------
    # Create normalized chart dataframe
    # --------------------------------------------------------

    chart_df = pd.DataFrame()

    for symbol in selected_symbols:

        series = stock_series[
            symbol
        ].copy()

        first_price = float(
            series.iloc[0][symbol]
        )

        # ----------------------------------------------------
        # Normalize to ZERO
        # ----------------------------------------------------

        series["Return"] = (
            (
                series[symbol]
                / first_price
            ) - 1
        ) * 100

        temp = series[
            [
                "Date",
                "Return"
            ]
        ].copy()

        temp = temp.rename(
            columns={
                "Return": symbol
            }
        )

        if chart_df.empty:

            chart_df = temp

        else:

            chart_df = chart_df.merge(
                temp,
                on="Date",
                how="outer"
            )

    chart_df = chart_df.sort_values(
        "Date"
    )

    # --------------------------------------------------------
    # Force first displayed point to 0%
    # --------------------------------------------------------

    for symbol in selected_symbols:

        if symbol in chart_df.columns:

            first_valid_index = (
                chart_df[symbol]
                .first_valid_index()
            )

            if (
                first_valid_index
                is not None
            ):

                chart_df.loc[
                    first_valid_index,
                    symbol
                ] = 0.0

    return (
        chart_df,
        ranking_df,
        selected_df,
        start_date,
        end_date
    )


# ============================================================
# CREATE INTERACTIVE CHART
# ============================================================

def create_chart(
    chart_df,
    ranking_df,
    selected_df,
    sector,
    period,
    stock_count,
    start_date,
    end_date
):

    fig = go.Figure()

    selected_symbols = (
        selected_df["Symbol"]
        .tolist()
    )

    # --------------------------------------------------------
    # Add stock lines
    # --------------------------------------------------------

    for symbol in selected_symbols:

        if symbol not in chart_df.columns:
            continue

        fig.add_trace(
            go.Scatter(
                x=chart_df["Date"],
                y=chart_df[symbol],
                mode="lines+markers",
                name=symbol,

                line=dict(
                    width=2
                ),

                marker=dict(
                    size=5
                ),

                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Date: %{x|%d-%b-%Y}<br>"
                    "Return: %{y:.2f}%"
                    "<extra></extra>"
                )
            )
        )

    # --------------------------------------------------------
    # Zero baseline
    # --------------------------------------------------------

    fig.add_hline(
        y=0,
        line_width=1,
        line_dash="dot"
    )

    # --------------------------------------------------------
    # Stock count label
    # --------------------------------------------------------

    if str(stock_count).lower() == "all":

        count_label = "All"

    else:

        count_label = (
            f"Top {stock_count}"
        )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    fig.update_layout(

        title={
            "text": (
                f"{sector} — "
                f"{period} Relative Performance"
            ),
            "x": 0.5,
            "xanchor": "center"
        },

        # ----------------------------------------------------
        # X Axis
        # ----------------------------------------------------

        xaxis=dict(
            title="",
            showgrid=True,
            zeroline=False,
            rangeslider=dict(
                visible=False
            )
        ),

        # ----------------------------------------------------
        # Y Axis
        # ----------------------------------------------------

        yaxis=dict(
            title="Performance (%)",
            ticksuffix="%",
            showgrid=True,
            zeroline=True,
            zerolinewidth=1
        ),

        # ----------------------------------------------------
        # Legend
        # ----------------------------------------------------

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),

        # ----------------------------------------------------
        # Hover
        # ----------------------------------------------------

        hovermode="x unified",

        # ----------------------------------------------------
        # Theme
        # ----------------------------------------------------

        template="plotly_dark",

        # ----------------------------------------------------
        # Size
        # ----------------------------------------------------

        height=650,

        margin=dict(
            l=70,
            r=40,
            t=100,
            b=80
        )
    )

    # --------------------------------------------------------
    # Subtitle / annotation
    # --------------------------------------------------------

    fig.add_annotation(
        text=(
            f"Daily cumulative percentage performance "
            f"from {start_date.strftime('%d-%b-%Y')} "
            f"to {end_date.strftime('%d-%b-%Y')} "
            f"• {count_label}"
        ),
        xref="paper",
        yref="paper",
        x=0,
        y=1.08,
        showarrow=False,
        align="left"
    )

    # --------------------------------------------------------
    # Filename
    # --------------------------------------------------------

    safe_sector = (
        sector
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace("&", "and")
    )

    filename = (
        f"{safe_sector}_"
        f"{period}_"
        f"{count_label.replace(' ', '')}.html"
    )

    output_file = (
        OUTPUT_DIR /
        filename
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    fig.write_html(
        output_file,
        include_plotlyjs=True
    )

    return output_file


# ============================================================
# DISPLAY RANKING
# ============================================================

def show_ranking(
    ranking_df,
    selected_df
):

    selected_symbols = set(
        selected_df["Symbol"]
        .tolist()
    )

    print()
    print("=" * 70)
    print("STOCK PERFORMANCE RANKING")
    print("=" * 70)

    print()

    print(
        f"{'':1}"
        f"{'Rank':>5} "
        f"{'Symbol':<20} "
        f"{'Return':>10}"
    )

    print(
        "-" * 45
    )

    for index, row in ranking_df.iterrows():

        rank = index + 1

        symbol = row["Symbol"]

        performance = row["Return"]

        marker = (
            "*"
            if symbol in selected_symbols
            else " "
        )

        print(
            f"{marker}"
            f"{rank:>5} "
            f"{symbol:<20} "
            f"{performance:>9.2f}%"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("       SECTOR RELATIVE PERFORMANCE CHART")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # Load files
    # --------------------------------------------------------

    master = load_master()

    prices = load_prices()

    # --------------------------------------------------------
    # Available sectors
    # --------------------------------------------------------

    sectors = get_sectors(
        master
    )

    print()
    print("=" * 70)
    print("AVAILABLE SECTORS")
    print("=" * 70)

    for index, sector in enumerate(
        sectors,
        start=1
    ):

        count = len(
            master[
                master["Sector"]
                .str.lower()
                == sector.lower()
            ]["Symbol"]
            .unique()
        )

        print(
            f"{index:>3}. "
            f"{sector:<40} "
            f"({count} stocks)"
        )

    # --------------------------------------------------------
    # Sector selection
    # --------------------------------------------------------

    print()

    sector_input = input(
        f"Enter Sector "
        f"[default: {DEFAULT_SECTOR}]: "
    ).strip()

    sector = find_sector(
        sectors,
        sector_input
    )

    # --------------------------------------------------------
    # Period selection
    # --------------------------------------------------------

    print()
    print(
        "Periods available:"
    )

    print(
        "1M  = 1 Month"
    )

    print(
        "3M  = 3 Months"
    )

    print(
        "6M  = 6 Months"
    )

    print(
        "YTD = Year To Date"
    )

    print()

    period_input = input(
        f"Enter Period "
        f"[default: {DEFAULT_PERIOD}]: "
    ).strip().upper()

    period = (
        period_input
        if period_input
        else DEFAULT_PERIOD
    )

    if period not in PERIOD_DAYS:

        raise ValueError(
            "Invalid period. "
            "Use 1M, 3M, 6M or YTD."
        )

    # --------------------------------------------------------
    # Stock selection
    # --------------------------------------------------------

    print()
    print(
        "Stock selection:"
    )

    print(
        "5    = Top 5"
    )

    print(
        "10   = Top 10"
    )

    print(
        "20   = Top 20"
    )

    print(
        "All  = All stocks"
    )

    print()

    count_input = input(
        f"Enter selection "
        f"[default: {DEFAULT_STOCK_COUNT}]: "
    ).strip()

    if not count_input:

        stock_count = DEFAULT_STOCK_COUNT

    elif count_input.lower() == "all":

        stock_count = "All"

    else:

        try:

            stock_count = int(
                count_input
            )

        except ValueError:

            raise ValueError(
                "Invalid stock selection. "
                "Use 5, 10, 20 or All."
            )

        if stock_count <= 0:

            raise ValueError(
                "Stock count must be greater than zero."
            )

    # --------------------------------------------------------
    # Prepare data
    # --------------------------------------------------------

    (
        chart_df,
        ranking_df,
        selected_df,
        start_date,
        end_date
    ) = prepare_sector_data(
        master,
        prices,
        sector,
        period,
        stock_count
    )

    # --------------------------------------------------------
    # Show ranking
    # --------------------------------------------------------

    show_ranking(
        ranking_df,
        selected_df
    )

    # --------------------------------------------------------
    # Create chart
    # --------------------------------------------------------

    output_file = create_chart(
        chart_df,
        ranking_df,
        selected_df,
        sector,
        period,
        stock_count,
        start_date,
        end_date
    )

    # --------------------------------------------------------
    # Final message
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("CHART CREATED SUCCESSFULLY")
    print("=" * 70)

    print()

    print(
        f"Sector       : {sector}"
    )

    print(
        f"Period       : {period}"
    )

    print(
        f"Start date   : "
        f"{start_date.strftime('%d-%b-%Y')}"
    )

    print(
        f"End date     : "
        f"{end_date.strftime('%d-%b-%Y')}"
    )

    print(
        f"Stocks shown : "
        f"{len(selected_df)}"
    )

    print(
        f"Selected     : "
        f"{', '.join(selected_df['Symbol'].tolist())}"
    )

    print()

    print(
        f"HTML file    : "
        f"{output_file}"
    )

    print()

    print(
        "Open the HTML file in Chrome."
    )

    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Program cancelled."
        )

    except Exception as e:

        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)
        print()
        print(e)
        print()