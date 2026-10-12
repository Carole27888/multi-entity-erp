/* Chart helpers. A view renders data with {{ data|json_script:"chart-id-data" }} and the
   template adds <canvas data-chart="bar" data-source="chart-id-data"> (data-source = json_script id). Colours come from
   CSS variables in tokens.css so templates never hard-code hex values. */
(function () {
  "use strict";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function resolveColor(value) {
    if (typeof value === "string" && value.indexOf("--") === 0) return cssVar(value);
    if (Array.isArray(value)) return value.map(resolveColor);
    return value;
  }
  function compact(n) {
    var abs = Math.abs(n);
    if (abs >= 1e6) return (n / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (abs >= 1e3) return (n / 1e3).toFixed(abs >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "K";
    return String(n);
  }

  function baseOptions(type, spec) {
    var grid = cssVar("--c-border");
    var muted = cssVar("--c-text-muted");
    var opts = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: !!spec.legend, position: "bottom", labels: { color: muted, boxWidth: 10, boxHeight: 10, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var v = ctx.parsed && typeof ctx.parsed === "object" ? (ctx.parsed.y !== undefined ? ctx.parsed.y : ctx.parsed) : ctx.parsed;
              var prefix = spec.currency ? "KES " : "";
              return (ctx.dataset.label ? ctx.dataset.label + ": " : ctx.label + ": ") + prefix + Number(v).toLocaleString("en-KE");
            }
          }
        }
      }
    };
    if (type === "doughnut" || type === "pie") {
      opts.cutout = spec.cutout || "68%";
      return opts;
    }
    opts.scales = {
      x: { grid: { display: false }, ticks: { color: muted }, stacked: !!spec.stacked },
      y: {
        beginAtZero: true, stacked: !!spec.stacked, border: { display: false },
        grid: { color: grid }, ticks: { color: muted, callback: function (v) { return compact(v); } }
      }
    };
    if (spec.dualAxis) {
      opts.scales.y1 = { beginAtZero: true, position: "right", border: { display: false }, grid: { display: false }, ticks: { color: muted } };
    }
    if (spec.indexAxis === "y") {
      opts.indexAxis = "y";
      var x = opts.scales.x; opts.scales.x = opts.scales.y; opts.scales.y = x;
    }
    return opts;
  }

  function draw(canvas) {
    if (!window.Chart || canvas.dataset.drawn) return;
    var source = document.getElementById(canvas.dataset.source);
    if (!source) return;
    var spec = JSON.parse(source.textContent);
    var type = canvas.dataset.chart || spec.type || "bar";
    var datasets = (spec.datasets || []).map(function (ds) {
      var out = Object.assign({}, ds);
      out.backgroundColor = resolveColor(ds.color || ds.backgroundColor || "--c-primary");
      out.borderColor = resolveColor(ds.borderColor || ds.color || "--c-primary");
      delete out.color;
      var dsType = ds.type || type;
      if (dsType === "bar") { out.borderRadius = 4; out.maxBarThickness = out.maxBarThickness || 30; out.borderWidth = ds.borderColor ? 1 : 0; }
      if (dsType === "line") { out.tension = 0.35; out.pointRadius = 3; out.borderWidth = 2; out.fill = !!ds.fill; out.order = -1; }
      if (type === "doughnut") { out.borderWidth = 2; out.borderColor = cssVar("--c-card"); }
      return out;
    });
    canvas.dataset.drawn = "1";
    canvas._chart = new window.Chart(canvas, { type: type, data: { labels: spec.labels, datasets: datasets }, options: baseOptions(type, spec) });
  }

  function drawAll(root) {
    (root || document).querySelectorAll("canvas[data-chart]").forEach(draw);
  }

  document.addEventListener("DOMContentLoaded", function () { drawAll(document); });
  // Charts inside HTMX partials
  document.addEventListener("htmx:afterSettle", function (event) { drawAll(event.target); });
  window.App = window.App || {};
  window.App.drawCharts = drawAll;
})();
