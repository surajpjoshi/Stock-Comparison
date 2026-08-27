let appData = null, chart = null;

const sectorSelect = document.getElementById("sectorSelect");
const periodSelect = document.getElementById("periodSelect");
const stocksSelect = document.getElementById("stocksSelect");
const latestDate = document.getElementById("latestDate");
const chartTitle = document.getElementById("chartTitle");
const chartSubtitle = document.getElementById("chartSubtitle");
const legend = document.getElementById("legend");
const performanceTable = document.getElementById("performanceTable");

const lineColors = [
  "#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
  "#0891b2", "#db2777", "#65a30d", "#9333ea", "#475569"
];

async function loadData() {
  const response = await fetch("data.json", { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`Unable to load data.json (${response.status})`);
  }

  // Python/pandas may have written NaN/Infinity, which are not valid JSON.
  // Convert those values to null before parsing.
  const raw = await response.text();
  const cleaned = raw
    .replace(/\bNaN\b/g, "null")
    .replace(/\bInfinity\b/g, "null")
    .replace(/-Infinity\b/g, "null");

  try {
    appData = JSON.parse(cleaned);
  } catch (error) {
    console.error("Invalid data.json:", raw.substring(0, 1000));
    throw new Error("data.json contains invalid JSON. Run generate_web_data.py again after applying the generator fix.");
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
    .sort((a, b) => a.localeCompare(b))
    .forEach(sector => {
      const option = document.createElement("option");
      option.value = sector;
      option.textContent = prettyName(sector);
      sectorSelect.appendChild(option);
    });

  if (appData.sectors["nifty100"]) {
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
    chartTitle.textContent = `${prettyName(sector)} — ${period}`;
    chartSubtitle.textContent = "No stock data available";
    legend.innerHTML = "";
    performanceTable.innerHTML = "";
    return;
  }

  const dates = (periodData.dates || []).map(formatDate);

  chartTitle.textContent = `${prettyName(sector)} — ${period}`;
  chartSubtitle.textContent =
    `${symbols.length} stocks • normalized to 0% at period start`;

  drawChart(dates, symbols, periodData);
  drawLegend(symbols);
  drawTable(symbols, periodData);
}

function drawChart(labels, symbols, periodData) {
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
    const item = document.createElement("div");
    item.className = "legend-item";

    const line = document.createElement("span");
    line.className = "legend-line";
    line.style.backgroundColor = lineColors[index % lineColors.length];

    const text = document.createElement("span");
    text.textContent = symbol;

    item.appendChild(line);
    item.appendChild(text);
    legend.appendChild(item);
  });
}

function drawTable(symbols, periodData) {
  performanceTable.innerHTML = "";

  symbols.forEach((symbol, index) => {
    const info = periodData.stocks?.[symbol] || {};
    const raw = Number(info.performance);
    const value = Number.isFinite(raw) ? raw : null;

    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(symbol)}</strong></td>
      <td>${escapeHtml(info.company || "")}</td>
      <td class="${value === null ? "" : value >= 0 ? "return-positive" : "return-negative"}">
        ${value === null ? "N/A" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`}
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

function prettyName(value) {
  return String(value)
    .replace(/nifty/gi, "Nifty ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([a-z])([0-9])/gi, "$1 $2")
    .replace(/([0-9])([a-z])/gi, "$1 $2")
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

sectorSelect.addEventListener("change", render);
periodSelect.addEventListener("change", render);
stocksSelect.addEventListener("change", render);

loadData().catch(error => {
  console.error(error);
  latestDate.textContent = "";
  chartTitle.textContent = "Unable to load dashboard";
  chartSubtitle.textContent = error.message;
});
