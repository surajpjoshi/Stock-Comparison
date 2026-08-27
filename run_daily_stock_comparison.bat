@echo off
setlocal

REM ============================================================
REM Stock Comparison - Daily Update
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo STOCK COMPARISON DAILY UPDATE
echo ============================================================
echo.

REM Run the Upstox incremental updater
python download_stock_prices_daily_update.py

if errorlevel 1 (
    echo.
    echo ERROR: Stock price update failed.
    exit /b 1
)

echo.
echo ============================================================
echo PRICE UPDATE COMPLETED
echo ============================================================
echo.

REM Run the existing comparison generator.
REM NOTE: This generator is interactive, so this step is only
REM intended for manual testing until the website data pipeline
REM is automated separately.
python generate_comparison_chart.py

if errorlevel 1 (
    echo.
    echo ERROR: Comparison chart generation failed.
    exit /b 1
)

echo.
echo ============================================================
echo GIT UPDATE
echo ============================================================
echo.

git add stock_prices.xlsx sector_charts

git diff --cached --quiet
if not errorlevel 1 (
    echo No chart/price changes detected.
    goto :done
)

git commit -m "Daily stock comparison update"

if errorlevel 1 (
    echo.
    echo ERROR: Git commit failed.
    exit /b 1
)

git push origin master

if errorlevel 1 (
    echo.
    echo ERROR: Git push failed.
    exit /b 1
)

:done
echo.
echo ============================================================
echo DAILY UPDATE FINISHED
echo ============================================================
echo.

endlocal
