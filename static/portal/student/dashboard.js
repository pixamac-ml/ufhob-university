(function () {
  "use strict";

  const config = window.StudentDashboardConfig || {};
  const academicYearId = String(config.academicYearId || "").trim();

  function withAcademicYear(url, extraParams) {
    if (!url) return url;
    const parsed = new URL(url, window.location.origin);
    if (academicYearId) parsed.searchParams.set("academic_year_id", academicYearId);
    Object.entries(extraParams || {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") parsed.searchParams.set(key, String(value));
    });
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  }

  function csrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  window.parseDashboardData = function (id, fallback) {
    const node = document.getElementById(id);
    if (!node) return fallback;
    try { return JSON.parse(node.textContent); } catch (_error) { return fallback; }
  };

  async function updateContentProgress(contentId, payload) {
    const url = withAcademicYear((config.contentProgressUrlTemplate || "").replace("/0/", `/${contentId}/`));
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), "X-ESFE-Automated-Request": "1" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("progress-update-failed");
    return response.json();
  }

  function refreshCourseWorkspace() {
    const player = document.querySelector("[data-course-player-page]");
    if (player && window.htmx && player.dataset.refreshing !== "1") {
      player.dataset.refreshing = "1";
      const request = window.htmx.ajax("GET", window.location.href, { target: player, swap: "outerHTML" });
      if (request && typeof request.finally === "function") request.finally(() => { delete player.dataset.refreshing; });
      else window.setTimeout(() => { delete player.dataset.refreshing; }, 500);
    }
  }

  function sendProgressOnce(node, contentId, percent, lastPosition) {
    const previous = Number(node.dataset.lastSentProgress || 0);
    if (percent <= previous || node.dataset.progressPending === "1") return;
    node.dataset.lastSentProgress = String(percent);
    node.dataset.progressPending = "1";
    updateContentProgress(contentId, {
      progress_percent: percent,
      last_position: lastPosition || 0,
      // Completion is server-derived at the reading threshold, never a manual CTA.
      is_completed: percent >= 90,
    }).then((result) => {
      if (result.is_completed && node.dataset.completionRefreshed !== "1") {
        node.dataset.completionRefreshed = "1";
        refreshCourseWorkspace();
      }
    }).catch(() => {
      node.dataset.lastSentProgress = String(previous);
    }).finally(() => { delete node.dataset.progressPending; });
  }

  function initTextReadingTracking(root) {
    if (!root || !root.querySelectorAll || !("IntersectionObserver" in window)) return;
    root.querySelectorAll("[data-reading-progress-region]").forEach((region) => {
      if (region.dataset.boundReading === "1") return;
      region.dataset.boundReading = "1";
      const contentId = region.dataset.readingProgressRegion;
      const scrollRoot = region.closest("[data-reading-scroll-root]");
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const marker = entry.target;
          sendProgressOnce(region, contentId, Number(marker.dataset.readingProgressMarker || 0));
          observer.unobserve(marker);
        });
      }, { root: scrollRoot || null, rootMargin: "0px 0px -10%", threshold: 0.8 });
      region.querySelectorAll("[data-reading-progress-marker]").forEach((marker) => observer.observe(marker));
    });
  }

  function initEmbeddedViewTracking(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-track-content]").forEach((node) => {
      if (node.dataset.boundTrack === "1") return;
      node.dataset.boundTrack = "1";
      const record = () => sendProgressOnce(node, node.dataset.trackContent, Number(node.dataset.trackProgress || 10));
      node.addEventListener("load", record, { once: true });
    });
  }

  function initVideoTracking(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-media-progress-content]").forEach((node) => {
      if (node.dataset.boundTrack === "1") return;
      node.dataset.boundTrack = "1";
      const sendCurrentPosition = () => {
        if (!node.duration || !Number.isFinite(node.duration)) return;
        const percent = Math.min(100, Math.round((node.currentTime / node.duration) * 100));
        const last = Number(node.dataset.lastSentProgress || 0);
        if (percent < 90 && percent - last < 10) return;
        sendProgressOnce(node, node.dataset.mediaProgressContent, percent, Math.round(node.currentTime));
      };
      node.addEventListener("timeupdate", sendCurrentPosition);
      node.addEventListener("ended", () => sendProgressOnce(node, node.dataset.mediaProgressContent, 100, Math.round(node.duration || 0)));
    });
  }

  function initContentTracking(root) {
    initTextReadingTracking(root);
    initEmbeddedViewTracking(root);
    initVideoTracking(root);
  }

  window.studentDashboard = function () {
    return {
      init() {
        this.$nextTick(() => { initContentTracking(this.$root); if (window.lucide) window.lucide.createIcons(); });
      },
      goToSection(section) {
        const url = new URL(window.location.href);
        url.searchParams.set("section", section);
        if (academicYearId) url.searchParams.set("academic_year_id", academicYearId);
        window.location.assign(`${url.pathname}${url.search}`);
      },
      refreshSection(section) {
        const root = document.querySelector(`[data-student-section="${section}"]`);
        if (root && window.htmx) window.htmx.ajax("GET", withAcademicYear(root.dataset.sectionUrl), "#student-workspace");
      },
    };
  };

  function bindStudentDashboard() {
    document.body.addEventListener("htmx:afterSwap", (event) => {
      const target = event.detail && event.detail.target;
      initContentTracking(target);
      if (window.lucide) window.lucide.createIcons();
      if (target && target.id === "student-workspace") window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
    });
    initContentTracking(document);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindStudentDashboard);
  else bindStudentDashboard();
})();
