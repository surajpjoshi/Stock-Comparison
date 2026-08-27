let appData = null;
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
  const response = await fetch("data.json", { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`Unable to load data.json (${response.status})`);
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

function render() {
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
  const symbols = (ranking || []).filter(symbol =>
    periodData.series && Array.isArray(periodData.series[symbol])
  );

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
    addLegendItem(symbol, lineColors[index % lineColors.length], false);
  });

  addLegendItem("Nifty 50", benchmarkColors.nifty50, true);
  addLegendItem(getSectorName(sectorSelect.value), benchmarkColors.sector, true);
  addLegendItem("Nifty 500", benchmarkColors.nifty500, true);
}

function addLegendItem(label, color, dashed) {
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

  const text = document.createElement("span");
  text.textContent = label;

  item.appendChild(line);
  item.appendChild(text);
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
