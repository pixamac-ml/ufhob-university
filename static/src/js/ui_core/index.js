(function () {
  "use strict";

  if (typeof window.sidebarCollapsed === "undefined") {
    window.sidebarCollapsed = false;
  }

  const UI = window.ESFEUI = window.ESFEUI || {};
  if (UI.coreInitialized) return;
  UI.coreInitialized = true;
  UI.instances = UI.instances || { charts: new Map() };
  UI.toastRecent = UI.toastRecent || new Map();

  // The component is registered inline before Alpine boots, but focus
  // restoration is shared here so every UI Core overlay has one contract.
  UI.overlay = UI.overlay || {
    locks: new Set(),
    pruneLocks() {
      this.locks.forEach((owner) => {
        if (!owner || !owner.isConnected) this.locks.delete(owner);
      });
    },
    lockPage(owner) {
      this.pruneLocks();
      if (owner) this.locks.add(owner);
      document.documentElement.classList.add("overflow-hidden");
    },
    unlockPage(owner) {
      if (owner) this.locks.delete(owner);
      this.pruneLocks();
      // Closing a drawer or a confirmation dialog must not restore scrolling
      // while another shared overlay still owns the page lock.
      if (!this.locks.size) document.documentElement.classList.remove("overflow-hidden");
    },
    restoreFocus() {
      if (this.opener) this.opener.focus();
    }
  };

  UI.toast = function (detail, fallbackTone = "info") {
    const raw = typeof detail === "string" ? { message: detail } : (detail || {});
    const region = document.getElementById("ui-toast-region");
    const message = String(raw.message || raw.text || "").trim();
    if (!region || !message) return;
    const toneAliases = { error: "danger", neutral: "info" };
    const requestedTone = raw.tone || raw.type || fallbackTone;
    const tone = toneAliases[requestedTone] || requestedTone;
    const normalizedTone = ["info", "success", "warning", "danger"].includes(tone) ? tone : "info";
    const key = `${normalizedTone}:${message}`;
    const now = Date.now();
    const previous = UI.toastRecent.get(key) || 0;
    if (now - previous < 2500) return;
    UI.toastRecent.set(key, now);
    if (UI.toastRecent.size > 80) {
      UI.toastRecent.forEach((seenAt, seenKey) => {
        if (now - seenAt > 10000) UI.toastRecent.delete(seenKey);
      });
    }
    const colors = {
      info: ["border-ui-info/30", "bg-ui-info"],
      success: ["border-ui-success/30", "bg-ui-success"],
      warning: ["border-ui-warning/30", "bg-ui-warning"],
      danger: ["border-ui-danger/30", "bg-ui-danger"]
    };
    const durations = { success: 4200, info: 5000, warning: 6500, danger: 7500 };
    const requestedDuration = Number(raw.duration);
    const duration = Number.isFinite(requestedDuration) && requestedDuration > 0
      ? requestedDuration
      : durations[normalizedTone];
    const toast = document.createElement("div");
    toast.dataset.uiToast = "true";
    toast.className = `pointer-events-auto flex items-start gap-3 rounded-ui-card border ${colors[normalizedTone][0]} bg-ui-surface p-4 shadow-ui-dropdown`;
    toast.setAttribute("role", normalizedTone === "danger" ? "alert" : "status");
    toast.innerHTML = `<span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-ui-badge ${colors[normalizedTone][1]}"></span><p class="min-w-0 flex-1 break-words text-sm text-ui-text"></p><button type="button" class="grid h-8 w-8 place-items-center rounded-ui-button hover:bg-ui-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ui-focus" aria-label="Fermer"><span aria-hidden="true">&times;</span></button>`;
    toast.querySelector("p").textContent = message;
    const visibleToasts = region.querySelectorAll("[data-ui-toast]");
    if (visibleToasts.length >= 3) visibleToasts[visibleToasts.length - 1].remove();
    let removed = false;
    let timer = null;
    let hardTimer = null;
    const remove = () => {
      if (removed) return;
      removed = true;
      window.clearTimeout(timer);
      window.clearTimeout(hardTimer);
      toast.remove();
    };
    const scheduleRemoval = (delay) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(remove, delay);
    };
    toast.querySelector("button").addEventListener("click", remove);
    if (!raw.persistent) {
      scheduleRemoval(duration);
      // Hover may pause the readable countdown, never the lifecycle itself.
      // This prevents a forgotten pointer from leaving a toast forever.
      hardTimer = window.setTimeout(remove, duration + 5000);
      toast.addEventListener("mouseenter", () => window.clearTimeout(timer));
      toast.addEventListener("mouseleave", () => scheduleRemoval(Math.min(1800, duration)));
    }
    region.prepend(toast);
  };

  // Compatibility only: legacy endpoints and templates may still send
  // ``showToast`` / ``esfe:toast``. They now use the one UI Core renderer.
  window.esfeToast = function (messageOrDetail, type = "info", options = {}) {
    const detail = typeof messageOrDetail === "object" && messageOrDetail !== null
      ? messageOrDetail
      : { message: messageOrDetail, type, ...options };
    UI.toast(detail, type);
  };
  window.showToast = window.esfeToast;

  UI.charts = UI.charts || {};
  UI.charts.render = function (root) {
    if (!window.Chart) return;
    (root || document).querySelectorAll("[data-ui-chart]").forEach((canvas) => {
      // Chart.getChart retrouve l'instance par élément : fiable même sans id,
      // contrairement à la map indexée par canvas.id où les canvas sans id
      // partagent la même clé et se détruisent mutuellement.
      const existing = (window.Chart.getChart && window.Chart.getChart(canvas))
        || (canvas.id ? UI.instances.charts.get(canvas.id) : null);
      if (existing) existing.destroy();
      try {
        const config = JSON.parse(canvas.dataset.uiChart || "{}");
        const styles = getComputedStyle(document.documentElement);
        const chartColors = {
          "ui-primary": styles.getPropertyValue("--ui-chart-primary").trim() || styles.color,
          "ui-primary-soft": styles.getPropertyValue("--ui-chart-primary-soft").trim() || "transparent"
        };
        (config.data.datasets || []).forEach((dataset) => {
          dataset.borderColor = chartColors[dataset.borderColor] || dataset.borderColor;
          dataset.backgroundColor = chartColors[dataset.backgroundColor] || dataset.backgroundColor;
        });
        config.options = Object.assign({ responsive: true, maintainAspectRatio: false }, config.options || {});
        UI.instances.charts.set(canvas.id, new window.Chart(canvas, config));
      } catch (error) {
        canvas.replaceWith(Object.assign(document.createElement("p"), {
          className: "text-sm text-ui-danger",
          textContent: "Configuration du graphique invalide."
        }));
      }
    });
  };

  UI.init = function (root) {
    const scope = root || document;
    if (window.lucide) window.lucide.createIcons();
    UI.charts.render(scope);
    scope.querySelectorAll("[data-ui-clear-input]:not([data-ui-bound])").forEach((button) => {
      button.dataset.uiBound = "true";
      button.addEventListener("click", () => {
        const input = button.closest("label").querySelector("input");
        if (!input) return;
        input.value = "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
      });
    });
    scope.querySelectorAll("[data-ui-copy]:not([data-ui-bound])").forEach((button) => {
      button.dataset.uiBound = "true";
      button.addEventListener("click", async () => {
        await navigator.clipboard.writeText(button.dataset.uiCopy || "");
        UI.toast({ message: "Copié dans le presse-papiers.", tone: "success" });
      });
    });
    UI.bootstrapToasts(scope);
  };

  UI.emitDataChanged = function (requestPath = "") {
    document.body.dispatchEvent(new CustomEvent("esfe:data-changed", { bubbles: true }));
    const topics = {
      paiement: "payments", payment: "payments",
      candidature: "candidatures", candidat: "candidatures",
      caisse: "session", cash: "session", session: "session",
      depense: "expenses", expense: "expenses",
      boutique: "shop", shop: "shop",
      salaire: "salaries", salary: "salaries",
      inscription: "inscriptions", secretaire: "secretary", secretary: "secretary",
      enseignant: "teachers", teacher: "teachers"
    };
    Object.entries(topics).forEach(([term, topic]) => {
      if (requestPath.includes(term)) {
        document.body.dispatchEvent(new CustomEvent(`esfe:${topic}-changed`, { bubbles: true }));
      }
    });
  };

  UI.bootstrapToasts = function (root = document) {
    const bootstraps = [];
    if (root.matches && root.matches("[data-ui-toast-bootstrap]")) bootstraps.push(root);
    if (root.querySelectorAll) bootstraps.push(...root.querySelectorAll("[data-ui-toast-bootstrap]"));
    bootstraps.forEach((bootstrap) => {
      if (bootstrap.dataset.loaded === "true") return;
      bootstrap.dataset.loaded = "true";
      try {
        JSON.parse(bootstrap.textContent || "[]").forEach((detail) => UI.toast(detail));
      } catch (_) {}
    });
  };

  // HTMX keeps the request mechanics; UI Core owns the consistent interaction
  // state around them. This deliberately stays local to the source/target: a
  // small filter must not freeze an entire dashboard.
  UI.requests = UI.requests || {
    pending: new Map(),
    elements: new WeakMap(),
    enter(element, busy = false) {
      if (!element) return;
      let state = this.elements.get(element);
      if (!state) {
        state = {
          count: 0,
          requestState: element.getAttribute("data-ui-request-state"),
          requestVisible: element.getAttribute("data-ui-request-visible"),
          ariaBusy: element.getAttribute("aria-busy"),
        };
        this.elements.set(element, state);
      }
      state.count += 1;
      element.dataset.uiRequestState = "pending";
      if (busy) element.setAttribute("aria-busy", "true");
    },
    leave(element, busy = false) {
      const state = element && this.elements.get(element);
      if (!state) return;
      state.count -= 1;
      if (state.count > 0) return;
      if (state.requestState === null) delete element.dataset.uiRequestState;
      else element.setAttribute("data-ui-request-state", state.requestState);
      if (state.requestVisible === null) delete element.dataset.uiRequestVisible;
      else element.setAttribute("data-ui-request-visible", state.requestVisible);
      if (busy) {
        if (state.ariaBusy === null) element.removeAttribute("aria-busy");
        else element.setAttribute("aria-busy", state.ariaBusy);
      }
      this.elements.delete(element);
    },
    requestKey(event) {
      const detail = event.detail || {};
      return detail.xhr || null;
    },
    begin(event) {
      const key = this.requestKey(event);
      if (!key || this.pending.has(key)) return;
      const detail = event.detail || {};
      const source = detail.elt;
      const target = detail.target;
      const controls = [];
      const form = source && source.closest && source.closest("form");
      const candidates = form
        ? form.querySelectorAll("button[type='submit']:not([data-ui-keep-enabled])")
        : source && source.matches && source.matches("button") ? [source] : [];
      candidates.forEach((control) => {
        controls.push({ control, disabled: control.disabled });
        if (!control.disabled) {
          control.disabled = true;
          control.dataset.uiRequestDisabled = "true";
        }
      });
      this.enter(source);
      this.enter(target, true);
      const request = { source, target, controls, visibilityTimer: null };
      this.pending.set(key, request);
      // Fast exchanges should not flash a spinner. The cursor and disabled
      // submit still provide immediate, local feedback.
      request.visibilityTimer = window.setTimeout(() => {
        if (!this.pending.has(key)) return;
        if (source) source.dataset.uiRequestVisible = "true";
        if (target) target.dataset.uiRequestVisible = "true";
      }, 180);
    },
    finish(event) {
      const key = this.requestKey(event);
      const request = key && this.pending.get(key);
      if (!request) return;
      this.pending.delete(key);
      window.clearTimeout(request.visibilityTimer);
      this.leave(request.source);
      this.leave(request.target, true);
      request.controls.forEach(({ control, disabled }) => {
        if (!control || !control.isConnected) return;
        control.disabled = disabled;
        delete control.dataset.uiRequestDisabled;
      });
    },
  };

  // A mutation may affect a fragment outside its HTMX target. Fragments opt in
  // with data-ui-refresh-on="topic-a topic-b" and a canonical GET URL; this
  // keeps Django as the source of truth and avoids dashboard-specific reloads.
  UI.invalidation = UI.invalidation || {
    timers: new Map(),
    inFlight: new Set(),
    topics(detail) {
      const raw = detail && (detail.topics || detail.topic || detail);
      const values = Array.isArray(raw) ? raw : typeof raw === "string" ? raw.split(/[\s,]+/) : [];
      return new Set(values.map((value) => String(value).trim()).filter(Boolean));
    },
    matches(node, topics) {
      const declared = (node.dataset.uiRefreshOn || "").split(/[\s,]+/).filter(Boolean);
      return declared.some((topic) => topics.has(topic));
    },
    isBusy(node) {
      return node.matches("[data-ui-request-state='pending']") || Boolean(
        node.querySelector("[data-ui-request-state='pending'], form[data-ui-dirty='true']")
      );
    },
    queue(node) {
      if (this.timers.has(node) || this.inFlight.has(node)) return;
      this.timers.set(node, window.setTimeout(() => {
        this.timers.delete(node);
        this.refresh(node);
      }, 80));
    },
    refresh(node) {
      if (!node.isConnected || this.isBusy(node) || !window.htmx) return;
      const url = node.dataset.uiRefreshUrl;
      const target = node.dataset.uiRefreshTarget
        ? document.querySelector(node.dataset.uiRefreshTarget)
        : node;
      if (!url || !target) return;
      this.inFlight.add(target);
      target.dataset.uiRefreshState = "refreshing";
      window.htmx.ajax("GET", url, {
        target,
        swap: node.dataset.uiRefreshSwap || "outerHTML",
      });
    },
    settle(event) {
      const target = event.detail && event.detail.target;
      if (!target || !this.inFlight.has(target)) return;
      this.inFlight.delete(target);
      delete target.dataset.uiRefreshState;
    },
    invalidate(detail) {
      const topics = this.topics(detail);
      if (!topics.size) return;
      document.querySelectorAll("[data-ui-refresh-on][data-ui-refresh-url]").forEach((node) => {
        if (this.matches(node, topics)) this.queue(node);
      });
    },
  };

  UI.subnavigation = UI.subnavigation || {
    viewFromUrl(url) {
      if (!url) return "";
      try {
        return new URL(url, window.location.origin).searchParams.get("view") || "";
      } catch (_) {
        return "";
      }
    },
    viewFromEvent(event) {
      const xhr = event.detail && event.detail.xhr;
      const pushedUrl = xhr && xhr.getResponseHeader && xhr.getResponseHeader("HX-Push-Url");
      return this.viewFromUrl(pushedUrl) || this.viewFromUrl(xhr && xhr.responseURL) || this.viewFromUrl(window.location.href);
    },
    sync(view) {
      if (!view) return;
      document.querySelectorAll("[data-ui-subnavigation]").forEach((navigation) => {
        const eventName = navigation.dataset.uiSubviewEvent;
        const attribute = navigation.dataset.uiSubviewAttr;
        if (!eventName || !attribute) return;
        const selector = `[data-${attribute}]`;
        const items = navigation.querySelectorAll(selector);
        if (!Array.from(items).some((item) => item.getAttribute(`data-${attribute}`) === view)) return;
        window.dispatchEvent(new CustomEvent(eventName, { detail: { id: view } }));
        items.forEach((item) => {
          const active = item.getAttribute(`data-${attribute}`) === view;
          item.setAttribute("aria-selected", active ? "true" : "false");
          if (active) item.setAttribute("aria-current", "page");
          else item.removeAttribute("aria-current");
        });
      });
    },
    syncFromEvent(event) {
      this.sync(this.viewFromEvent(event));
    },
  };

  // The certified top bar is shared by every dashboard. Keep its clock alive
  // in the browser instead of making a server request for a visual-only value.
  UI.refreshLiveClocks = function (root) {
    (root || document).querySelectorAll("[data-ui-live-clock]").forEach((clock) => {
      const now = new Date();
      clock.dateTime = now.toISOString();
      clock.textContent = new Intl.DateTimeFormat("fr-FR", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(now).replace(",", " ·");
    });
  };

  UI.setContextLabel = function (label) {
    if (!label) return;
    document.querySelectorAll("[data-ui-context-label]").forEach((node) => {
      node.textContent = label;
    });
  };

  const initialize = () => {
    UI.init(document);
    UI.refreshLiveClocks(document);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();

  document.addEventListener("ui:toast", (event) => UI.toast(event.detail));
  document.addEventListener("ui:invalidate", (event) => UI.invalidation.invalidate(event.detail));
  document.addEventListener("esfe:toast", (event) => UI.toast(event.detail));
  document.addEventListener("toast", (event) => UI.toast(event.detail));
  document.addEventListener("showToast", (event) => UI.toast(event.detail, "success"));
  document.addEventListener("account:profile-updated", (event) => {
    const avatarUrl = event.detail && event.detail.avatar_url;
    if (!avatarUrl) return;
    const cacheBusted = avatarUrl + (avatarUrl.includes("?") ? "&" : "?") + "v=" + Date.now();
    document.querySelectorAll("[data-user-avatar]").forEach((avatar) => {
      if (avatar.tagName === "IMG") {
        avatar.src = cacheBusted;
        return;
      }
      const image = document.createElement("img");
      image.src = cacheBusted;
      image.alt = avatar.dataset.avatarAlt || "Photo de profil";
      image.className = avatar.dataset.avatarImageClass || "h-8 w-8 rounded-full object-cover";
      image.loading = "lazy";
      image.dataset.userAvatar = "";
      avatar.replaceWith(image);
    });
  });
  document.body.addEventListener("htmx:configRequest", (event) => {
    const token = document.cookie.split("; ").find((item) => item.startsWith("csrftoken="));
    if (token) event.detail.headers["X-CSRFToken"] = decodeURIComponent(token.split("=").slice(1).join("="));
  });
  document.body.addEventListener("htmx:beforeRequest", (event) => UI.requests.begin(event));
  document.body.addEventListener("htmx:afterSwap", (event) => {
    UI.init(event.detail.target);
    UI.subnavigation.syncFromEvent(event);
  });
  document.body.addEventListener("htmx:afterSettle", (event) => {
    UI.requests.finish(event);
    UI.invalidation.settle(event);
  });
  document.addEventListener("esfe:dashboard-context-changed", (event) => {
    UI.setContextLabel(event.detail && event.detail.label);
  });
  if (!UI.liveClockTimer) {
    UI.liveClockTimer = window.setInterval(() => UI.refreshLiveClocks(document), 30000);
  }
  window.addEventListener("popstate", () => {
    window.requestAnimationFrame(() => UI.subnavigation.sync(UI.subnavigation.viewFromUrl(window.location.href)));
  });
  document.body.addEventListener("htmx:historyRestore", () => {
    UI.subnavigation.sync(UI.subnavigation.viewFromUrl(window.location.href));
  });
  function hasToastTrigger(xhr) {
    const trigger = xhr && xhr.getResponseHeader("HX-Trigger");
    if (!trigger) return false;
    try {
      const events = JSON.parse(trigger);
      return Boolean(events["ui:toast"] || events.toast || events.showToast);
    } catch (_) {
      return false;
    }
  }

  document.body.addEventListener("htmx:afterRequest", (event) => {
    // afterSettle is the normal path; afterRequest is the final safety net
    // for cancelled swaps, errors and responses with no swap.
    UI.requests.finish(event);
    UI.invalidation.settle(event);
    const xhr = event.detail.xhr;
    const trigger = xhr && xhr.getResponseHeader("HX-Trigger");
    const requestPath = (event.detail.pathInfo && event.detail.pathInfo.requestPath) || "";
    if (event.detail.successful) UI.emitDataChanged(requestPath);
    if (!trigger) return;
    try {
      const events = JSON.parse(trigger);
      if (events["ui:toast"]) UI.toast(events["ui:toast"]);
      if (events.toast) UI.toast(events.toast);
      if (events.showToast) UI.toast(events.showToast, "success");
    } catch (_) {}
  });
  document.body.addEventListener("htmx:responseError", (event) => {
    UI.requests.finish(event);
    UI.invalidation.settle(event);
    UI.subnavigation.sync(UI.subnavigation.viewFromUrl(window.location.href));
    if (hasToastTrigger(event.detail && event.detail.xhr)) return;
    UI.toast({ message: "La requête n'a pas pu aboutir.", tone: "danger" });
  });
  document.body.addEventListener("htmx:sendError", (event) => {
    UI.requests.finish(event);
    UI.invalidation.settle(event);
    UI.subnavigation.sync(UI.subnavigation.viewFromUrl(window.location.href));
    UI.toast({ message: "La connexion au serveur a échoué.", tone: "danger" });
  });
  document.body.addEventListener("htmx:timeout", (event) => {
    UI.requests.finish(event);
    UI.invalidation.settle(event);
    UI.subnavigation.sync(UI.subnavigation.viewFromUrl(window.location.href));
    if (hasToastTrigger(event.detail && event.detail.xhr)) return;
    UI.toast({ message: "La requête a expiré. Réessayez dans quelques instants.", tone: "danger" });
  });
  document.body.addEventListener("htmx:abort", (event) => {
    UI.requests.finish(event);
    UI.invalidation.settle(event);
    UI.subnavigation.sync(UI.subnavigation.viewFromUrl(window.location.href));
  });
})();
