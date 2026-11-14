(function () {
  "use strict";

  window.publicNavbarVisibility = function () {
    return {
      navVisible: false,
      frameId: null,
      updateHandler: null,

      init() {
        const hero = document.getElementById("hero-section");
        if (!hero) {
          this.navVisible = true;
          return;
        }

        const update = () => {
          this.frameId = null;
          this.navVisible = hero.getBoundingClientRect().bottom <= 0;
        };
        this.updateHandler = () => {
          if (this.frameId === null) this.frameId = requestAnimationFrame(update);
        };

        update();
        window.addEventListener("scroll", this.updateHandler, { passive: true });
        window.addEventListener("resize", this.updateHandler);
      },

      destroy() {
        window.removeEventListener("scroll", this.updateHandler);
        window.removeEventListener("resize", this.updateHandler);
        if (this.frameId !== null) cancelAnimationFrame(this.frameId);
      },
    };
  };

  window.cinematicHero = function (options) {
    const slideCount = Math.max(1, Number(options && options.slideCount) || 1);
    const duration = Math.max(6000, Number(options && options.duration) || 7000);

    return {
      current: 0,
      progress: 0,
      phase: "entering",
      transitioning: false,
      userPaused: false,
      reducedMotion: false,
      inViewport: true,
      cycleStartedAt: 0,
      pausedAt: 0,
      transitionStartedAt: 0,
      transitionTarget: 0,
      sceneSwapped: false,
      frameId: null,
      visibilityHandler: null,
      motionQuery: null,
      motionHandler: null,
      observer: null,

      init() {
        this.motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
        this.reducedMotion = this.motionQuery.matches;
        this.motionHandler = (event) => {
          this.reducedMotion = event.matches;
          if (this.reducedMotion) {
            this.cancelFrame();
            this.progress = 0;
            this.phase = "reading";
          } else if (!this.userPaused && this.inViewport && !document.hidden) {
            this.restartCycle();
          }
          this.syncVideos();
        };
        this.motionQuery.addEventListener("change", this.motionHandler);

        this.visibilityHandler = () => {
          if (document.hidden) {
            this.pauseClock();
          } else if (!this.userPaused && this.inViewport && !this.reducedMotion) {
            this.resumeClock();
          }
          this.syncVideos();
        };
        document.addEventListener("visibilitychange", this.visibilityHandler);

        this.observer = new IntersectionObserver(
          ([entry]) => {
            this.inViewport = Boolean(entry && entry.isIntersecting);
            if (this.inViewport && !this.userPaused && !this.reducedMotion && !document.hidden) {
              this.resumeClock();
            } else {
              this.pauseClock();
            }
            this.syncVideos();
          },
          { threshold: 0.15 }
        );
        this.observer.observe(this.$el);

        this.$nextTick(() => {
          this.syncVideos();
          if (this.reducedMotion) {
            this.phase = "reading";
            return;
          }
          this.restartCycle();
        });
      },

      destroy() {
        this.cancelFrame();
        document.removeEventListener("visibilitychange", this.visibilityHandler);
        if (this.motionQuery && this.motionHandler) {
          this.motionQuery.removeEventListener("change", this.motionHandler);
        }
        if (this.observer) this.observer.disconnect();
        this.pauseAllVideos();
      },

      sceneClass(index) {
        if (index !== this.current) return "";
        return `is-active is-${this.phase}`;
      },

      slideNumber(index) {
        return String(index + 1).padStart(2, "0");
      },

      shouldRun() {
        return !this.userPaused && !this.reducedMotion && this.inViewport && !document.hidden;
      },

      restartCycle() {
        this.cancelFrame();
        this.cycleStartedAt = performance.now();
        this.pausedAt = 0;
        this.progress = 0;
        this.phase = "entering";
        this.frameId = requestAnimationFrame((time) => this.tick(time));
      },

      tick(time) {
        const transitionCanRun = this.transitioning && this.inViewport && !document.hidden && !this.reducedMotion;
        if (!this.shouldRun() && !transitionCanRun) {
          this.frameId = null;
          return;
        }

        if (this.transitioning) {
          const transitionElapsed = time - this.transitionStartedAt;
          if (!this.sceneSwapped && transitionElapsed >= 640) {
            this.current = this.transitionTarget;
            this.sceneSwapped = true;
            this.phase = "entering";
            this.progress = 0;
            this.$nextTick(() => this.syncVideos());
          }
          if (transitionElapsed >= 1450) {
            this.transitioning = false;
            this.sceneSwapped = false;
            this.cycleStartedAt = time;
            this.progress = 0;
            this.phase = "entering";
            if (this.userPaused) this.pausedAt = time;
          }
        } else {
          const elapsed = time - this.cycleStartedAt;
          this.progress = Math.min(100, (elapsed / duration) * 100);
          this.phase = elapsed < 1250 ? "entering" : elapsed < duration - 950 ? "reading" : "exiting";
          if (elapsed >= duration) this.beginTransition((this.current + 1) % slideCount, time);
        }

        this.frameId = requestAnimationFrame((nextTime) => this.tick(nextTime));
      },

      beginTransition(target, time) {
        if (this.transitioning || slideCount < 2) return;
        this.transitionTarget = (target + slideCount) % slideCount;
        this.transitionStartedAt = time || performance.now();
        this.transitioning = true;
        this.sceneSwapped = false;
        this.phase = "exiting";
      },

      navigate(target) {
        if (this.transitioning || target === this.current) return;
        if (this.reducedMotion) {
          this.current = (target + slideCount) % slideCount;
          this.phase = "reading";
          this.progress = 0;
          this.$nextTick(() => this.syncVideos());
          return;
        }
        if (this.frameId === null && this.inViewport && !document.hidden) {
          this.frameId = requestAnimationFrame((time) => this.tick(time));
        }
        this.beginTransition(target, performance.now());
      },

      previous() {
        this.navigate(this.current - 1);
      },

      next() {
        this.navigate(this.current + 1);
      },

      togglePause() {
        this.userPaused = !this.userPaused;
        if (this.userPaused) {
          this.pauseClock();
        } else if (!this.reducedMotion && this.inViewport && !document.hidden) {
          this.resumeClock();
        }
        this.syncVideos();
      },

      pauseClock() {
        if (!this.pausedAt) this.pausedAt = performance.now();
        this.cancelFrame();
      },

      resumeClock() {
        if (this.reducedMotion || this.userPaused || !this.inViewport || document.hidden) return;
        const now = performance.now();
        if (this.pausedAt) {
          const pauseDuration = now - this.pausedAt;
          if (this.transitioning) this.transitionStartedAt += pauseDuration;
          else this.cycleStartedAt += pauseDuration;
          this.pausedAt = 0;
        } else if (!this.cycleStartedAt) {
          this.cycleStartedAt = now;
        }
        if (this.frameId === null) this.frameId = requestAnimationFrame((time) => this.tick(time));
      },

      cancelFrame() {
        if (this.frameId !== null) cancelAnimationFrame(this.frameId);
        this.frameId = null;
      },

      pauseAllVideos() {
        this.$el.querySelectorAll("[data-hero-video]").forEach((video) => video.pause());
      },

      syncVideos() {
        this.$el.querySelectorAll("[data-hero-slide]").forEach((scene, index) => {
          const video = scene.querySelector("[data-hero-video]");
          if (!video) return;
          const mayPlay = index === this.current && this.inViewport && !document.hidden && !this.userPaused && !this.reducedMotion;
          if (mayPlay) {
            video.preload = "metadata";
            const playRequest = video.play();
            if (playRequest && typeof playRequest.catch === "function") playRequest.catch(() => {});
          } else {
            video.pause();
          }
        });
      },
    };
  };
})();
