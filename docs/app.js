let appData = null;
let stockMetadata = {};
let chart = null;
let periodEndDateOverride = null;

const sectorSelect = document.getElementById("sectorSelect");
const periodSelect = document.getElementById("periodSelect");
const periodPrev = document.getElementById("periodPrev");
const periodNext = document.getElementById("periodNext");
const periodRangeLabel = document.getElementById("periodRangeLabel");
const stocksSelect = document.getElementById("stocksSelect");
const latestDate = document.getElementById("latestDate");
const chartTitle = document.getElementById("chartTitle");
const chartSubtitle = document.getElementById("chartSubtitle");
const legend = document.getElementById("legend");
const performanceTable = document.getElementById("performanceTable");
const benchmarkCards = document.getElementById("benchmarkCards");
const sectorRanking = document.getElementById("sectorRanking");

// GitHub Actions workflow used to update the dashboard.
const GITHUB_WORKFLOW_RUNS_URL =
  "https://api.github.com/repos/surajpjoshi/Stock-Comparison/actions/workflows/daily_stock_update.yml/runs?per_page=1";

async function loadGitHubLastRunTime() {
  try {
    const response = await fetch(GITHUB_WORKFLOW_RUNS_URL, {
      cache: "no-store",
      headers: {
        Accept: "application/vnd.github+json"
      }
    });

    if (!response.ok) {
      throw new Error(`GitHub API returned ${response.status}`);
    }

    const data = await response.json();
    const run = data.workflow_runs?.[0];

    if (!run) {
      throw new Error("No GitHub Actions runs found.");
    }

    const runDate = new Date(run.run_started_at || run.created_at);

    if (Number.isNaN(runDate.getTime())) {
      throw new Error("Invalid GitHub Actions run time.");
    }

    const parts = new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false
    }).formatToParts(runDate);

    const getPart = type =>
      parts.find(part => part.type === type)?.value || "";

    const dateText =
      `${getPart("day")} ${getPart("month")} ${getPart("year")}`;

    const timeText =
      `${getPart("hour")}:${getPart("minute")}:${getPart("second")}`;

    latestDate.textContent =
      `Latest data: ${formatDate(appData?.latest_date || "")} • Last updated: ${timeText} IST`;

    latestDate.title =
      `GitHub Actions: ${dateText} ${timeText} IST`;

  } catch (error) {
    console.warn("Unable to get GitHub Actions last run time:", error);
  }
}

const lineColors = [
  "#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
  "#0891b2", "#db2777", "#65a30d", "#9333ea", "#475569"
];

const benchmarkColors = {
  nifty50: "#111827",
  sector: "#0f766e",
  nifty500: "#b45309"
};

async function loadData() {
  const [response, metadataResponse] = await Promise.all([
    fetch("data.json", { cache: "no-store" }),
    fetch("stock_metadata.json", { cache: "no-store" })
  ]);

  if (!response.ok) {
    throw new Error(`Unable to load data.json (${response.status})`);
  }

  if (metadataResponse.ok) {
    try {
      stockMetadata = await metadataResponse.json();
      if (!stockMetadata || typeof stockMetadata !== "object") {
        stockMetadata = {};
      }
    } catch (error) {
      console.warn("Unable to load stock_metadata.json:", error);
      stockMetadata = {};
    }
  }

  const raw = await response.text();
  const cleaned = raw
    .replace(/\bNaN\b/g, "null")
    .replace(/\bInfinity\b/g, "null")
    .replace(/-Infinity\b/g, "null");

  try {
    appData = JSON.parse(cleaned);
  } catch (error) {
    console.error("Invalid data.json:", raw.substring(0, 1000));
    throw new Error("data.json contains invalid JSON.");
  }

  if (!appData.sectors) {
    throw new Error("data.json does not contain sector data.");
  }

  latestDate.textContent =
    "Latest data: " + formatDate(appData.latest_date || "");

  // Show the actual time of the latest GitHub Actions update.
  loadGitHubLastRunTime();

  populateSectors();
  updateCustomDateControls();
  updatePeriodRangeLabel();
  updatePeriodNavigationButtons();
  render();
}

function populateSectors() {
  sectorSelect.innerHTML = "";

  Object.keys(appData.sectors)
    .sort((a, b) => getSectorName(a).localeCompare(getSectorName(b)))
    .forEach(sector => {
      const option = document.createElement("option");
      option.value = sector;
      option.textContent = getSectorName(sector);
      sectorSelect.appendChild(option);
    });

  if (appData.sectors.nifty500) {
    sectorSelect.value = "nifty500";
  } else if (appData.sectors.nifty100) {
    sectorSelect.value = "nifty100";
  }
}


const customDateControls = document.getElementById("customDateControls");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");

function getBaseYtdData(sector) {
  return appData.sectors?.[sector]?.YTD || null;
}

function getAvailableDates(periodData) {
  return (periodData?.dates || [])
    .map(v => String(v).slice(0, 10))
    .filter(Boolean);
}

function rebaseSeries(values, startIndex, endIndex) {
  const base = Number(values[startIndex]);
  if (!Number.isFinite(base)) return [];

  const result = [];
  for (let i = startIndex; i <= endIndex; i++) {
    const value = Number(values[i]);
    result.push(
      Number.isFinite(value)
        ? ((1 + value / 100) / (1 + base / 100) - 1) * 100
        : null
    );
  }
  return result;
}

function buildFilteredPeriodData(baseData, startDate, endDate) {
  const dates = getAvailableDates(baseData);
  let startIndex = dates.indexOf(startDate);
  let endIndex = dates.lastIndexOf(endDate);

  if (startIndex < 0) {
    startIndex = dates.findIndex(d => d >= startDate);
  }
  if (endIndex < 0) {
    for (let i = dates.length - 1; i >= 0; i--) {
      if (dates[i] <= endDate) {
        endIndex = i;
        break;
      }
    }
  }

  if (startIndex < 0 || endIndex < 0 || startIndex > endIndex) return null;

  const result = {
    ...baseData,
    dates: dates.slice(startIndex, endIndex + 1),
    series: {},
    stocks: {}
  };

  Object.entries(baseData.series || {}).forEach(([symbol, values]) => {
    result.series[symbol] = rebaseSeries(values, startIndex, endIndex);
  });

  Object.entries(baseData.stocks || {}).forEach(([symbol, info]) => {
    const series = result.series[symbol] || [];
    const valid = series.filter(v => Number.isFinite(Number(v)));
    const performance = valid.length ? Number(valid[valid.length - 1]) : null;
    result.stocks[symbol] = {...info, performance};
  });

  const ranked = Object.entries(result.stocks)
    .filter(([, info]) => Number.isFinite(Number(info.performance)))
    .sort((a, b) => Number(b[1].performance) - Number(a[1].performance))
    .map(([symbol]) => symbol);

  result.top5 = ranked.slice(0, 5);
  result.top10 = ranked.slice(0, 10);
  result.sector_benchmark = baseData.sector_benchmark
    ? {
        ...baseData.sector_benchmark,
        dates: dates.slice(startIndex, endIndex + 1),
        series: rebaseSeries(
          baseData.sector_benchmark.series || [],
          startIndex,
          endIndex
        )
      }
    : baseData.sector_benchmark;

  return result;
}

function getPeriodWindow(period, endDate) {
  if (!endDate) return null;

  if (period === "CUSTOM") {
    if (!startDateInput?.value || !endDateInput?.value) return null;
    return { start: startDateInput.value, end: endDateInput.value };
  }

  const end = new Date(endDate + "T00:00:00");
  let daysBack = 0;

  if (period === "1W") daysBack = 6;
  else if (period === "1M") daysBack = 30;
  else if (period === "3M") daysBack = 90;
  else if (period === "6M") daysBack = 180;
  else if (period === "YTD") {
    return { start: `${end.getFullYear()}-01-01`, end: endDate };
  }
  else return null;

  end.setDate(end.getDate() - daysBack);
  return {
    start: end.toISOString().slice(0, 10),
    end: endDate
  };
}

function getNavigationDates() {
  const base = appData?.sectors?.[sectorSelect.value]?.YTD;
  return getAvailableDates(base);
}

function getCurrentPeriodEndDate() {
  const dates = getNavigationDates();
  if (!dates.length) return null;

  if (periodSelect.value === "CUSTOM" && endDateInput?.value) return endDateInput.value;
  if (periodEndDateOverride && dates.includes(periodEndDateOverride)) return periodEndDateOverride;
  return dates[dates.length - 1];
}

function buildPeriodData(sector, period) {
  const base = getBaseYtdData(sector);
  if (!base?.dates?.length) return null;

  if (period === "CUSTOM") {
    if (!startDateInput?.value || !endDateInput?.value) return null;
    return buildFilteredPeriodData(base, startDateInput.value, endDateInput.value);
  }

  if (periodEndDateOverride || period === "1W") {
    const end = getCurrentPeriodEndDate();
    const window = getPeriodWindow(period, end);
    if (window) return buildFilteredPeriodData(base, window.start, window.end);
  }

  return appData.sectors?.[sector]?.[period] || null;
}

function updatePeriodRangeLabel() {
  if (!periodRangeLabel) return;
  const period = periodSelect.value;
  const dates = getNavigationDates();
  if (!dates.length) { periodRangeLabel.textContent = ""; return; }

  const end = getCurrentPeriodEndDate();
  const window = getPeriodWindow(period, end);
  if (!window) { periodRangeLabel.textContent = ""; return; }

  periodRangeLabel.textContent = `${formatDate(window.start)} → ${formatDate(window.end)}`;
}

function movePeriodByOneDay(direction) {
  const dates = getNavigationDates();
  if (!dates.length) return;

  const currentEnd = getCurrentPeriodEndDate();
  let index = dates.indexOf(currentEnd);
  if (index < 0) index = dates.length - 1;

  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= dates.length) return;

  const nextEnd = dates[nextIndex];

  if (periodSelect.value === "CUSTOM") {
    const start = new Date(startDateInput.value + "T00:00:00");
    const end = new Date(endDateInput.value + "T00:00:00");
    start.setDate(start.getDate() + direction);
    end.setDate(end.getDate() + direction);
    const nextStart = start.toISOString().slice(0, 10);
    const nextEndDate = end.toISOString().slice(0, 10);

    if (dates.some(d => d === nextStart) && dates.some(d => d === nextEndDate)) {
      startDateInput.value = nextStart;
      endDateInput.value = nextEndDate;
    }
  } else {
    periodEndDateOverride = nextEnd;
  }

  updatePeriodRangeLabel();
  render();
  updatePeriodNavigationButtons();
}

function updatePeriodNavigationButtons() {
  const dates = getNavigationDates();
  if (!dates.length) return;
  const index = dates.indexOf(getCurrentPeriodEndDate());
  if (periodPrev) periodPrev.disabled = index <= 0;
  if (periodNext) periodNext.disabled = index < 0 || index >= dates.length - 1;
}


function buildBenchmarkPeriodData(kind, period) {
  if (period === "1W" || period === "CUSTOM") {
    const base = appData.benchmarks?.[kind]?.periods?.YTD;
    if (!base) return null;
    const start = period === "CUSTOM" ? startDateInput.value : (() => {
      const dates = getAvailableDates(base);
      const end = dates[dates.length - 1];
      const d = new Date(end + "T00:00:00");
      d.setDate(d.getDate() - 6);
      return d.toISOString().slice(0, 10);
    })();
    return buildFilteredPeriodData(
      {dates: base.dates, series: {__benchmark__: base.series}},
      start,
      period === "CUSTOM" ? endDateInput.value : getAvailableDates(base).at(-1)
    ) && (() => {
      const filtered = buildFilteredPeriodData(
        {dates: base.dates, series: {__benchmark__: base.series}},
        start,
        period === "CUSTOM" ? endDateInput.value : getAvailableDates(base).at(-1)
      );
      if (!filtered) return null;
      return {
        ...base,
        dates: filtered.dates,
        series: filtered.series.__benchmark__,
        performance: filtered.series.__benchmark__.at(-1)
      };
    })();
  }
  return appData.benchmarks?.[kind]?.periods?.[period] || null;
}

function updateCustomDateControls() {
  const custom = periodSelect.value === "CUSTOM";
  if (customDateControls) customDateControls.hidden = !custom;

  if (custom && appData?.latest_date) {
    const latest = String(appData.latest_date).slice(0, 10);
    if (endDateInput && !endDateInput.value) endDateInput.value = latest;
    if (startDateInput && !startDateInput.value) {
      const d = new Date(latest + "T00:00:00");
      d.setDate(d.getDate() - 30);
      startDateInput.value = d.toISOString().slice(0, 10);
    }
  }
}

function render() {
  const sector = sectorSelect.value;
  const period = periodSelect.value;
  const count = Number(stocksSelect.value);
  const periodData = buildPeriodData(sector, period);

  if (!periodData) {
    destroyChart();
    chartTitle.textContent = "No data";
    chartSubtitle.textContent = "";
    legend.innerHTML = "";
    performanceTable.innerHTML = "";
    return;
  }

  const ranking = count === 5 ? periodData.top5 : periodData.top10;
  let symbols = (ranking || []).filter(symbol =>
    periodData.series && Array.isArray(periodData.series[symbol])
  );



  if (!symbols.length) {
    destroyChart();
    chartTitle.textContent = `${getSectorName(sector)} — ${period === "CUSTOM" ? `${startDateInput.value} to ${endDateInput.value}` : period}`;
    chartSubtitle.textContent = "No stock data available";
    legend.innerHTML = "";
    performanceTable.innerHTML = "";
    return;
  }

  const dates = (periodData.dates || []).map(formatDate);

  chartTitle.textContent = `${getSectorName(sector)} — ${period}`;
  chartSubtitle.textContent =
    `${symbols.length} stocks • normalized to 0% at period start`;

  drawChart(dates, symbols, periodData, period);
  drawLegend(symbols);
  drawTable(symbols, periodData);
  drawBenchmarkCards(sector, period);
  drawSectorRanking(period);
}

function drawChart(labels, symbols, periodData, period) {
  destroyChart();

  const datasets = symbols.map((symbol, index) => {
    const values = periodData.series[symbol].map(v => {
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    });

    return {
      label: symbol,
      data: values,
      borderColor: lineColors[index % lineColors.length],
      backgroundColor: lineColors[index % lineColors.length],
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.15,
      fill: false,
      spanGaps: true
    };
  });



  const benchmarkDefinitions = [
    ["Nifty 50", buildBenchmarkPeriodData("nifty50", period), benchmarkColors.nifty50],
    [getSectorName(sectorSelect.value), periodData.sector_benchmark, benchmarkColors.sector],
    ["Nifty 500", buildBenchmarkPeriodData("nifty500", period), benchmarkColors.nifty500]
  ];

  benchmarkDefinitions.forEach(([label, benchmark, color]) => {
    if (!benchmark?.series) return;

    datasets.push({
      label,
      data: benchmark.series.map(v => {
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      }),
      borderColor: color,
      backgroundColor: color,
      borderWidth: 2.5,
      borderDash: [7, 5],
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.15,
      fill: false,
      spanGaps: true
    });
  });

  chart = new Chart(
    document.getElementById("chart").getContext("2d"),
    {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: context => {
                const value = context.parsed.y;
                return value == null
                  ? `${context.dataset.label}: N/A`
                  : `${context.dataset.label}: ${Number(value).toFixed(2)}%`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { maxTicksLimit: 12, maxRotation: 0 },
            grid: { display: false }
          },
          y: {
            title: { display: true, text: "Relative Performance (%)" },
            ticks: { callback: value => `${value}%` },
            grid: { color: "#e8ebf0" }
          }
        }
      }
    }
  );
}

function drawLegend(symbols) {
  legend.innerHTML = "";

  symbols.forEach((symbol, index) => {
    // Stock symbols open their Chartink page in a new tab.
    addLegendItem(
      symbol,
      lineColors[index % lineColors.length],
      false,
      `https://chartink.com/stocks/${encodeURIComponent(symbol)}.html`
    );
  });

  addLegendItem("Nifty 50", benchmarkColors.nifty50, true);
  addLegendItem(getSectorName(sectorSelect.value), benchmarkColors.sector, true);
  addLegendItem("Nifty 500", benchmarkColors.nifty500, true);
}

function addLegendItem(label, color, dashed, href = null) {
  const item = document.createElement("div");
  item.className = "legend-item";

  const line = document.createElement("span");
  line.className = "legend-line";
  line.style.backgroundColor = color;

  if (dashed) {
    line.style.backgroundImage =
      `repeating-linear-gradient(to right, ${color} 0 6px, transparent 6px 10px)`;
    line.style.backgroundColor = "transparent";
  }

  if (href) {
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    link.title = `Open ${label} on Chartink`;
    link.style.cursor = "pointer";
    link.style.textDecoration = "none";
    link.style.color = "inherit";
    link.addEventListener("click", event => event.stopPropagation());

    item.appendChild(line);
    item.appendChild(link);
  } else {
    const text = document.createElement("span");
    text.textContent = label;

    item.appendChild(line);
    item.appendChild(text);
  }

  legend.appendChild(item);
}

function drawBenchmarkCards(sector, period) {
  benchmarkCards.innerHTML = "";

  const periodData = buildPeriodData(sector, period);
  const selected = periodData?.sector_benchmark;
  const nifty50 = buildBenchmarkPeriodData("nifty50", period);
  const nifty500 = buildBenchmarkPeriodData("nifty500", period);

  const cards = [
    {
      label: "Nifty 50",
      value: nifty50?.performance,
      note: "Equal-weighted proxy"
    },
    {
      label: getSectorName(sector),
      value: selected?.performance,
      note: `${selected?.constituents || 0} stocks`
    },
    {
      label: "Nifty 500",
      value: nifty500?.performance,
      note: "Equal-weighted proxy"
    }
  ];

  cards.forEach(card => {
    const value = Number(card.value);
    const valid = Number.isFinite(value);

    const div = document.createElement("div");
    div.className = "benchmark-card";

    const valueClass = !valid ? "" : value >= 0 ? "return-positive" : "return-negative";

    div.innerHTML = `
      <div class="benchmark-label">${escapeHtml(card.label)}</div>
      <div class="benchmark-value ${valueClass}">
        ${valid ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}%` : "N/A"}
      </div>
      <div class="benchmark-note">${escapeHtml(card.note)}</div>
    `;

    benchmarkCards.appendChild(div);
  });
}

function drawSectorRanking(period) {
  sectorRanking.innerHTML = "";

  // Keep this section compact: show only the 10 strongest sectors.
  let ranking;
  if (period === "1W" || period === "CUSTOM") {
    ranking = Object.keys(appData.sectors || {})
      .map(sector => {
        const pd = buildPeriodData(sector, period);
        const series = pd?.sector_benchmark?.series || [];
        const valid = series.filter(v => Number.isFinite(Number(v)));
        const performance = valid.length ? Number(valid[valid.length - 1]) : null;
        return {sector, performance};
      })
      .filter(item => Number.isFinite(item.performance))
      .sort((a, b) => b.performance - a.performance)
      .slice(0, 10);
  } else {
    ranking = (appData.sector_performance?.[period] || []).slice(0, 10);
  }
  const maxAbs = Math.max(
    1,
    ...ranking.map(item => Math.abs(Number(item.performance) || 0))
  );

  ranking.forEach((item, index) => {
    const value = Number(item.performance);
    if (!Number.isFinite(value)) return;

    const row = document.createElement("div");
    row.className = "sector-row";

    const width = Math.max(2, Math.min(100, Math.abs(value) / maxAbs * 100));
    const positive = value >= 0;

    row.innerHTML = `
      <div class="sector-rank">${index + 1}</div>
      <div class="sector-name">${escapeHtml(item.name || getSectorName(item.sector))}</div>
      <div class="sector-bar-wrap">
        <div class="sector-bar ${positive ? "positive" : "negative"}" style="width:${width}%"></div>
      </div>
      <div class="sector-return ${positive ? "return-positive" : "return-negative"}">
        ${value >= 0 ? "+" : ""}${value.toFixed(2)}%
      </div>
    `;

    row.addEventListener("click", () => {
      sectorSelect.value = item.sector;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    sectorRanking.appendChild(row);
  });
}

function normalizeSectorText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/^nifty/, "")
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "");
}

function scoreSectorForIndustry(sector, industry) {
  const s = normalizeSectorText(sector);
  const i = normalizeSectorText(industry);

  if (!s || !i) return 0;

  // Direct/near-direct industry → sector matches.
  const aliases = [
    ["oilgas", "oilandgas"],
    ["oilgasconsumablefuels", "oilandgas"],
    ["telecommunication", "telecommunications"],
    ["telecommunication", "midsmallitandtelecom"],
    ["informationtechnology", "it"],
    ["capitalgoods", "capitalgoods"],
    ["consumerdurables", "consumerdurables"],
    ["consumerservices", "consumerservices"],
    ["financialservices", "financialservices"],
    ["financialservices", "financialservicesexbank"],
    ["automobileandautocomponents", "auto"],
    ["fastmovingconsumergoods", "fmcg"],
    ["healthcare", "healthcare"],
    ["metals", "metal"],
    ["metalsmining", "metal"],
    ["oilgas", "energy"],
    ["power", "power"],
    ["realty", "realty"],
    ["mediaentertainmentpublication", "media"],
    ["chemicals", "chemicals"],
    ["constructionmaterials", "cement"],
    ["construction", "construction"],
  ];

  let score = 0;
  for (const [industryKey, sectorKey] of aliases) {
    if (i.includes(industryKey) && s.includes(sectorKey)) {
      score += 100;
    }
  }

  // Token overlap is a secondary signal.
  const industryTokens = i.match(/[a-z]{3,}/g) || [];
  for (const token of industryTokens) {
    if (s.includes(token)) score += 10;
  }

  // Avoid broad index buckets when a sector-specific candidate exists.
  if (s === "500" || s === "100" || s === "200" || s.includes("next50") ||
      s.includes("midcap") || s.includes("smallcap") || s.includes("microcap")) {
    score -= 50;
  }

  return score;
}

function drawTable(symbols, periodData) {
  performanceTable.innerHTML = "";

  const nifty50 = Number(
    buildBenchmarkPeriodData("nifty50", periodSelect.value)?.performance
  );

  symbols.forEach((symbol, index) => {
    const info = periodData.stocks?.[symbol] || {};
    const raw = Number(info.performance);
    const value = Number.isFinite(raw) ? raw : null;
    const relative = value !== null && Number.isFinite(nifty50)
      ? value - nifty50
      : null;

    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(symbol)}</strong></td>
      <td>${escapeHtml(info.company || "")}</td>
      <td class="${value === null ? "" : value >= 0 ? "return-positive" : "return-negative"}">
        ${value === null ? "N/A" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`}
      </td>
      <td class="${relative === null ? "" : relative >= 0 ? "return-positive" : "return-negative"}">
        ${relative === null ? "N/A" : `${relative >= 0 ? "+" : ""}${relative.toFixed(2)}%`}
      </td>
    `;

    performanceTable.appendChild(row);
  });
}

function destroyChart() {
  if (chart) {
    chart.destroy();
    chart = null;
  }
}

function normalizeSymbol(value) {
  return String(value || "")
    .replace(/^NSE:/i, "")
    .replace(/^BSE:/i, "")
    .trim()
    .toUpperCase();
}

function getSectorName(value) {
  return appData?.sector_labels?.[value] || prettyName(value);
}

function prettyName(value) {
  return String(value)
    .replace(/^nifty/i, "Nifty ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([a-z])([0-9])/gi, "$1 $2")
    .replace(/([0-9])([a-z])/gi, "$1 $2")
    .replace(/-/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase());
}

function formatDate(value) {
  if (!value) return "";
  const d = new Date(value + "T00:00:00");

  if (Number.isNaN(d.getTime())) return value;

  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "2-digit"
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelectorAll(".section-toggle").forEach(button => {
  button.addEventListener("click", () => {
    const target = document.getElementById(button.dataset.target);
    if (!target) return;

    const hidden = target.classList.toggle("is-hidden");
    button.textContent = hidden ? "Show" : "Hide";
    button.setAttribute("aria-expanded", String(!hidden));
  });
});

sectorSelect.addEventListener("change", () => {
  periodEndDateOverride = null;
  updateCustomDateControls();
  updatePeriodRangeLabel();
  updatePeriodNavigationButtons();
  render();
});
periodSelect.addEventListener("change", () => {
  periodEndDateOverride = null;
  updateCustomDateControls();
  updatePeriodRangeLabel();
  updatePeriodNavigationButtons();
  render();
});
startDateInput?.addEventListener("change", () => {
  if (periodSelect.value === "CUSTOM") {
    updatePeriodRangeLabel();
    updatePeriodNavigationButtons();
    render();
  }
});
endDateInput?.addEventListener("change", () => {
  if (periodSelect.value === "CUSTOM") {
    updatePeriodRangeLabel();
    updatePeriodNavigationButtons();
    render();
  }
});

periodPrev?.addEventListener("click", () => movePeriodByOneDay(-1));
periodNext?.addEventListener("click", () => movePeriodByOneDay(1));
stocksSelect.addEventListener("change", render);

loadData().catch(error => {
  console.error(error);
  latestDate.textContent = "";
  chartTitle.textContent = "Unable to load dashboard";
  chartSubtitle.textContent = error.message;
});
