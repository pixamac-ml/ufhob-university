(() => {
  if (window.esfeCourseInteractionRealtimeBound) return;
  window.esfeCourseInteractionRealtimeBound = true;

  const composerIsBusy = (root) => {
    const field = root && root.querySelector("textarea");
    return Boolean(field && (field === document.activeElement || field.value.trim()));
  };

  document.body.addEventListener("notifier.notification", (event) => {
    const payload = event.detail || {};
    if (payload.type !== "pedagogical.interaction" || !window.htmx) return;
    const teacherList = document.querySelector("[data-teacher-interactions-list]");
    if (teacherList && !composerIsBusy(document.querySelector("#teacher-course-interaction-detail"))) {
      window.htmx.ajax("GET", teacherList.dataset.listUrl, "#teacher-course-interactions-list");
    }

    const panel = document.querySelector("[data-course-interactions-panel]");
    if (!panel || String(panel.dataset.courseId) !== String(payload.ec_id)) return;
    const history = panel.querySelector("[data-question-id]");
    if (history && String(history.dataset.questionId) === String(payload.question_id)) {
      const threadUrl = (panel.dataset.threadUrl || "").replace("/0/thread/", `/${payload.question_id}/thread/`);
      if (threadUrl) window.htmx.ajax("GET", threadUrl, {target: "#course-question-thread-history", swap: "outerHTML"});
    } else if (!composerIsBusy(panel) && panel.dataset.listUrl) {
      window.htmx.ajax("GET", panel.dataset.listUrl, "#course-interactions-panel");
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail && event.detail.target;
    if (!target || target.id !== "teacher-course-interaction-detail" || !window.htmx) return;
    const teacherList = document.querySelector("[data-teacher-interactions-list]");
    if (teacherList && teacherList.dataset.listUrl) {
      window.htmx.ajax("GET", teacherList.dataset.listUrl, "#teacher-course-interactions-list");
    }
  });
})();
