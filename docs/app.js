let appData = null;
let rsiData = [];
let rsiBySymbol = new Map();
let stockMetadata = {};
let chart = null;

const sectorSelect = document.getElementById("sectorSelect");
const periodSelect = document.getElementById("periodSelect");
const stocksSelect = document.getElementById("stocksSelect");
const latestDate = document.getElementById("latestDate");
const chartTitle = document.getElementById("chartTitle");
const chartSubtitle = document.getElementById("chartSubtitle");
const legend = document.getElementById("legend");
const performanceTable = document.getElementById("performanceTable");
const benchmarkCards = document.getElementById("benchmarkCards");
const sectorRanking = document.getElementById("sectorRanking");

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
  const [response, rsiResponse, metadataResponse] = await Promise.all([
    fetch(`data.json?_=${Date.now()}`, { cache: "no-store" }),
    fetch(`rsi_data.json?_=${Date.now()}`, { cache: "no-store" }),
    fetch(`stock_metadata.json?_=${Date.now()}`, { cache: "no-store" })
  ]);

  if (!response.ok) {
    throw new Error(`Unable to load data.json (${response.status})`);
  }

  if (rsiResponse.ok) {
    try {
      const rawRsi = await rsiResponse.text();
      rsiData = JSON.parse(rawRsi);
      if (!Array.isArray(rsiData)) rsiData = [];
      rsiBySymbol = new Map(
        rsiData
          .filter(item => item && item.Symbol)
          .map(item => [normalizeSymbol(item.Symbol), item])
      );
    } catch (error) {
      console.warn("Unable to load rsi_data.json:", error);
      rsiData = [];
      rsiBySymbol = new Map();
    }
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

  const updatedAt = new Date();

  const updatedTime = updatedAt.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });

  latestDate.textContent =
    "Latest: " +
    formatDate(appData.latest_date || "") +
    " • " +
    updatedTime +
    " IST";

  populateSectors();
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

  if (appData.sectors.nifty100) {
    sectorSelect.value = "nifty100";
  }
}

function render(focusSymbol = null) {
  const sector = sectorSelect.value;
  const period = periodSelect.value;
  const count = Number(stocksSelect.value);
  const periodData = appData.sectors?.[sector]?.[period];

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

  // When an RSI alert is clicked, keep that stock in the chart and
  // fill the remaining slots with the sector's normal top peers.
  if (focusSymbol) {
    const focused = normalizeSymbol(focusSymbol);
    const matchingSymbol = Object.keys(periodData.series || {})
      .find(symbol => normalizeSymbol(symbol) === focused);

    if (matchingSymbol) {
      symbols = [
        matchingSymbol,
        ...symbols.filter(symbol => normalizeSymbol(symbol) !== focused)
      ].slice(0, count);
    }
  }

  if (!symbols.length) {
    destroyChart();
    chartTitle.textContent = `${getSectorName(sector)} — ${period}`;
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
  drawRsiAlerts();
}

const rsiAlertLabelPlugin = {
  id: "rsiAlertLabel",
  afterDatasetsDraw(chartInstance) {
    const ctx = chartInstance.ctx;
    ctx.save();
    ctx.font = "600 12px Arial";
    ctx.fillStyle = "#dc2626";
    ctx.textBaseline = "middle";

    chartInstance.data.datasets.forEach((dataset, datasetIndex) => {
      if (!dataset.rsiAlert) return;
      const meta = chartInstance.getDatasetMeta(datasetIndex);
      const point = meta.data.find(Boolean);
      if (!point) return;

      const position = point.getProps(["x", "y"], true);
      const label = `RSI < 35 (${Number(dataset.rsiValue).toFixed(1)})`;
      ctx.fillText(label, position.x + 12, position.y);
    });

    ctx.restore();
  }
};

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

  // Add a star marker at the latest available chart point when the
  // latest hourly RSI from rsi-dashboard is below 35.
  symbols.forEach((symbol, index) => {
    const rsiItem = rsiBySymbol.get(normalizeSymbol(symbol));
    const rsi = Number(rsiItem?.["Current Hourly RSI"]);
    if (!Number.isFinite(rsi) || rsi >= 35) return;

    const values = periodData.series[symbol].map(v => {
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    });
    let lastIndex = -1;
    for (let i = values.length - 1; i >= 0; i--) {
      if (values[i] !== null) {
        lastIndex = i;
        break;
      }
    }
    if (lastIndex < 0) return;

    const alertPoints = values.map((value, i) => i === lastIndex ? value : null);
    datasets.push({
      label: `${symbol} ⭐ RSI < 35`,
      data: alertPoints,
      borderWidth: 0,
      backgroundColor: "#dc2626",
      pointBackgroundColor: "#dc2626",
      pointBorderColor: "#ffffff",
      pointBorderWidth: 2,
      pointRadius: 9,
      pointHoverRadius: 11,
      pointStyle: "star",
      showLine: false,
      spanGaps: false,
      rsiAlert: true,
      rsiValue: rsi
    });
  });

  const benchmarkDefinitions = [
    ["Nifty 50", appData.benchmarks?.nifty50?.periods?.[period], benchmarkColors.nifty50],
    [getSectorName(sectorSelect.value), periodData.sector_benchmark, benchmarkColors.sector],
    ["Nifty 500", appData.benchmarks?.nifty500?.periods?.[period], benchmarkColors.nifty500]
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
      plugins: [rsiAlertLabelPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: context => {
                if (context.dataset.rsiAlert) {
                  return `${context.dataset.label}: ${Number(context.dataset.rsiValue).toFixed(2)}`;
                }
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

  const selected = appData.sectors?.[sector]?.[period]?.sector_benchmark;
  const nifty50 = appData.benchmarks?.nifty50?.periods?.[period];
  const nifty500 = appData.benchmarks?.nifty500?.periods?.[period];

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
  const ranking = (appData.sector_performance?.[period] || []).slice(0, 10);
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
      <div class="sector-name">${escapeHtml(item.name)}</div>
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

function findSectorForSymbol(symbol, period) {
  const target = normalizeSymbol(symbol);
  const metadata = stockMetadata[target] || {};
  const industry = metadata.industry || "";
  const metadataSectors = Array.isArray(metadata.sectors) ? metadata.sectors : [];

  const candidates = [];

  for (const sector of Object.keys(appData.sectors || {})) {
    const periodData = appData.sectors?.[sector]?.[period];
    if (!periodData) continue;

    const symbols = Object.keys(periodData.series || {});
    if (symbols.some(item => normalizeSymbol(item) === target)) {
      candidates.push(sector);
    }
  }

  if (!candidates.length) return null;

  // First prefer sectors explicitly listed in stock_master.xlsx.
  const masterCandidates = candidates.filter(sector =>
    metadataSectors.includes(sector)
  );

  const pool = masterCandidates.length ? masterCandidates : candidates;

  // Industry is used to choose the actual sector rather than Nifty 500.
  const ranked = pool
    .map(sector => ({
      sector,
      score: scoreSectorForIndustry(sector, industry)
    }))
    .sort((a, b) => b.score - a.score);

  return ranked[0]?.sector || pool[0];
}

function drawRsiAlerts() {
  const container = document.getElementById("rsiAlerts");
  const count = document.getElementById("rsiAlertCount");
  if (!container) return;

  const period = periodSelect.value;
  const alerts = rsiData
    .map(item => {
      const symbol = normalizeSymbol(item?.Symbol);
      const rsi = Number(item?.["Current Hourly RSI"]);
      return {
        symbol,
        rsi,
        sector: symbol ? findSectorForSymbol(symbol, period) : null
      };
    })
    .filter(item => item.symbol && Number.isFinite(item.rsi) && item.rsi < 35 && item.sector)
    .sort((a, b) => a.rsi - b.rsi);

  if (count) {
    count.textContent = `${alerts.length} stock${alerts.length === 1 ? "" : "s"}`;
  }

  container.innerHTML = "";

  if (!alerts.length) {
    container.innerHTML = '<div class="rsi-alert-empty">No stocks currently have 1H RSI below 35.</div>';
    return;
  }

  alerts.forEach(item => {
    const row = document.createElement("tr");
    const chartUrl = `https://chartink.com/stocks/${encodeURIComponent(item.symbol)}.html`;

    row.innerHTML = `
      <td>
        <a href="#" class="rsi-symbol-link" data-symbol="${escapeHtml(item.symbol)}"
           title="Open ${escapeHtml(getSectorName(item.sector))} chart">
          ${escapeHtml(item.symbol)}
        </a>
      </td>
      <td class="return-negative">${item.rsi.toFixed(1)}</td>
      <td class="return-negative">🔴 RSI &lt; 35</td>
      <td><a href="${chartUrl}" target="_blank" rel="noopener noreferrer">Open ChartInk ↗</a></td>
    `;

    const symbolLink = row.querySelector(".rsi-symbol-link");
    symbolLink.addEventListener("click", event => {
      event.preventDefault();
      sectorSelect.value = item.sector;
      render(item.symbol);
      document.querySelector(".chart-card")?.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    });

    container.appendChild(row);
  });
}

function drawTable(symbols, periodData) {
  performanceTable.innerHTML = "";

  const nifty50 = Number(
    appData.benchmarks?.nifty50?.periods?.[periodSelect.value]?.performance
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

sectorSelect.addEventListener("change", render);
periodSelect.addEventListener("change", render);
stocksSelect.addEventListener("change", render);

loadData().catch(error => {
  console.error(error);
  latestDate.textContent = "";
  chartTitle.textContent = "Unable to load dashboard";
  chartSubtitle.textContent = error.message;
});

// Automatically reload the dashboard every 5 minutes.
setInterval(() => {
  window.location.reload();
}, 5 * 60 * 1000);
