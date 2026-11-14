(function () {
  "use strict";

  const api = window.ESFECertifiedDashboard;
  if (!api || api.key !== "manager") return;
  if (document.documentElement.dataset.managerDashboardBound === "true") return;
  document.documentElement.dataset.managerDashboardBound = "true";

  function dispatchSubview(id) {
    if (!id) return;
    window.dispatchEvent(new CustomEvent("manager-subview", { detail: { id } }));
    window.requestAnimationFrame(() => {
      const active = document.querySelector(`[data-manager-subview="${id}"]`);
      if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  function refreshWorkspace() {
    const activeItem = document.querySelector("[data-ui-nav-item][data-active='true'][hx-get]");
    const url = activeItem && activeItem.getAttribute("hx-get");
    if (!url || !window.htmx) return;
    window.htmx.ajax("GET", url, { target: api.workspaceSelector, swap: "innerHTML" });
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-manager-subview]");
    if (link) dispatchSubview(link.dataset.managerSubview);
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (!target || !target.id || !/^manager-.+-subcontent$/.test(target.id)) return;
    target.focus({ preventScroll: true });
    if (window.lucide) window.lucide.createIcons({ nodes: [target] });
    if (window.htmx) window.htmx.process(target);
  });

  // Keep the manager inside the certified shell after a successful
  // inscription: refresh only its active workspace instead of reloading the
  // entire page (and reinitialising every dashboard listener).
  document.body.addEventListener("inscriptionCreated", () => {
    if (window.managerCloseModal) window.managerCloseModal();
    refreshWorkspace();
  });
})();
