(function () {
  "use strict";

  window.newsEditorialHero = function (count) {
    const slideCount = Math.max(0, Number(count) || 0);

    return {
      activeSlide: 0,
      progress: 0,
      userPaused: false,
      interactionPaused: false,
      reducedMotion: false,
      documentHidden: false,
      timer: null,
      progressTimer: null,
      motionQuery: null,
      motionHandler: null,
      visibilityHandler: null,
      duration: 7200,

      init() {
        if (slideCount < 2) return;

        this.motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
        this.reducedMotion = this.motionQuery.matches;
        this.motionHandler = (event) => {
          this.reducedMotion = event.matches;
          this.clearTimers();
          if (!this.reducedMotion) this.schedule();
        };
        if (this.motionQuery.addEventListener) {
          this.motionQuery.addEventListener("change", this.motionHandler);
        } else {
          this.motionQuery.addListener(this.motionHandler);
        }

        this.visibilityHandler = () => {
          this.documentHidden = document.hidden;
          if (this.documentHidden) this.clearTimers();
          else this.schedule();
        };
        document.addEventListener("visibilitychange", this.visibilityHandler);
        this.schedule();
      },

      destroy() {
        this.clearTimers();
        document.removeEventListener("visibilitychange", this.visibilityHandler);
        if (this.motionQuery && this.motionHandler) {
          if (this.motionQuery.removeEventListener) {
            this.motionQuery.removeEventListener("change", this.motionHandler);
          } else {
            this.motionQuery.removeListener(this.motionHandler);
          }
        }
      },

      canAdvance() {
        return slideCount > 1
          && !this.userPaused
          && !this.interactionPaused
          && !this.reducedMotion
          && !this.documentHidden;
      },

      clearTimers() {
        if (this.timer) window.clearTimeout(this.timer);
        if (this.progressTimer) window.clearInterval(this.progressTimer);
        this.timer = null;
        this.progressTimer = null;
      },

      schedule() {
        this.clearTimers();
        this.progress = 0;
        if (!this.canAdvance()) return;

        const startedAt = performance.now();
        this.progressTimer = window.setInterval(() => {
          this.progress = Math.min(100, ((performance.now() - startedAt) / this.duration) * 100);
        }, 80);
        this.timer = window.setTimeout(() => this.next(), this.duration);
      },

      hold() {
        this.interactionPaused = true;
        this.clearTimers();
      },

      release() {
        this.interactionPaused = false;
        this.schedule();
      },

      goTo(index) {
        if (slideCount < 1) return;
        this.activeSlide = (Number(index) + slideCount) % slideCount;
        this.schedule();
      },

      next() {
        this.goTo(this.activeSlide + 1);
      },

      previous() {
        this.goTo(this.activeSlide - 1);
      },

      togglePause() {
        this.userPaused = !this.userPaused;
        this.schedule();
      },
    };
  };
})();
