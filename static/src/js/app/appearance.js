/* Authenticated shell only. The server-rendered attributes win on first paint. */
(function () {
  "use strict";

  const shell = document.querySelector("[data-certified-dashboard-shell][data-app-shell]");
  if (!shell) return;
  const key = `ufhob.appearance.${shell.dataset.appearanceUser || "guest"}`;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const themes = new Set(["light", "dark", "system"]);
  const scales = new Set(["sm", "md", "lg", "xl"]);
  let mode = themes.has(shell.dataset.theme) ? shell.dataset.theme : "system";
  let scale = scales.has(shell.dataset.fontScale) ? shell.dataset.fontScale : "md";

  function resolvedTheme() {
    return mode === "system" ? (media.matches ? "dark" : "light") : mode;
  }

  function themedColor(token) {
    const probe = document.createElement("span");
    probe.style.color = `var(${token})`;
    shell.appendChild(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
  }

  function refreshCharts() {
    if (!window.Chart || !window.Chart.instances) return;
    const label = themedColor("--text-secondary");
    const grid = themedColor("--border-subtle");
    const surface = themedColor("--surface-elevated");
    const text = themedColor("--text-primary");
    if (window.Chart.defaults) {
      window.Chart.defaults.color = label;
      window.Chart.defaults.borderColor = grid;
    }
    Object.values(window.Chart.instances).forEach((chart) => {
      if (!shell.contains(chart.canvas)) return;
      const options = chart.options || {};
      if (options.plugins && options.plugins.legend && options.plugins.legend.labels) {
        options.plugins.legend.labels.color = label;
      }
      if (options.plugins && options.plugins.tooltip) {
        options.plugins.tooltip.backgroundColor = surface;
        options.plugins.tooltip.titleColor = text;
        options.plugins.tooltip.bodyColor = text;
      }
      Object.values(options.scales || {}).forEach((axis) => {
        if (axis.ticks) axis.ticks.color = label;
        if (axis.grid) axis.grid.color = grid;
        if (axis.title) axis.title.color = label;
      });
      chart.update("none");
    });
  }

  function apply(theme, fontScale, persist) {
    mode = themes.has(String(theme).toLowerCase()) ? String(theme).toLowerCase() : "system";
    scale = scales.has(String(fontScale).toLowerCase()) ? String(fontScale).toLowerCase() : "md";
    document.querySelectorAll("[data-app-shell]").forEach((root) => {
      root.dataset.theme = mode;
      root.dataset.fontScale = scale;
      root.dataset.resolvedTheme = resolvedTheme();
    });
    document.documentElement.dataset.appBootTheme = resolvedTheme();
    document.documentElement.style.colorScheme = resolvedTheme();
    const contentRoot = shell.querySelector(".ui-app-shell") || shell;
    document.documentElement.style.backgroundColor = getComputedStyle(contentRoot).backgroundColor;
    if (persist) {
      try { localStorage.setItem(key, JSON.stringify({ theme: mode, font_scale: scale })); } catch (_) {}
    }
    refreshCharts();
    window.dispatchEvent(new CustomEvent("app:theme-changed", {
      detail: { theme: mode, resolved: resolvedTheme(), font_scale: scale },
    }));
  }

  // Server values are authoritative; this also repairs an older local cache.
  apply(mode, scale, true);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", refreshCharts);
  else refreshCharts();
  document.addEventListener("account:preferences-updated", (event) => {
    const detail = event.detail || {};
    apply(detail.theme || mode, detail.font_scale || scale, true);
  });
  const onSystemChange = () => {
    if (mode === "system") apply(mode, scale, false);
  };
  if (media.addEventListener) media.addEventListener("change", onSystemChange);
  else media.addListener(onSystemChange);
  window.addEventListener("storage", (event) => {
    if (event.key !== key || !event.newValue) return;
    try {
      const value = JSON.parse(event.newValue);
      apply(value.theme, value.font_scale, false);
    } catch (_) {}
  });
  document.body.addEventListener("htmx:afterSwap", () => {
    // New charts and fragments inherit the already selected root attributes.
    window.requestAnimationFrame(refreshCharts);
  });
})();
