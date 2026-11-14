(function () {
  "use strict";

  if (window.ESFECookieConsent) {
    window.ESFECookieConsent.init();
    return;
  }

  var COOKIE_NAME = "esfe_cookie_consent";

  function getCookie(name) {
    var prefix = name + "=";
    var parts = document.cookie ? document.cookie.split(";") : [];
    for (var index = 0; index < parts.length; index += 1) {
      var item = parts[index].trim();
      if (item.indexOf(prefix) === 0) {
        var raw = item.substring(prefix.length);
        // Read preferences already saved by Django's former quoted JSON cookie.
        if (raw.charAt(0) === '"' && raw.charAt(raw.length - 1) === '"') {
          raw = raw.slice(1, -1).replace(/\\([0-3][0-7]{2}|[\s\S])/g, function (_, escaped) {
            return /^[0-3][0-7]{2}$/.test(escaped)
              ? String.fromCharCode(parseInt(escaped, 8)) : escaped;
          });
        }
        try {
          return decodeURIComponent(raw);
        } catch (error) {
          return null;
        }
      }
    }
    return null;
  }

  function parseConsent() {
    var raw = getCookie(COOKIE_NAME);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  function init() {
    var roots = document.querySelectorAll('[id="cookie-consent-root"]');
    var root = roots[0];
    if (!root) {
      return;
    }
    // A full-page fragment or a history restore must not create a second banner.
    for (var index = 1; index < roots.length; index += 1) {
      roots[index].remove();
    }

    var banner = root.querySelector("#cookie-banner");
    if (!banner) {
      return;
    }
    var endpoint = root.dataset.endpoint;
    var consentVersion = Number(root.dataset.consentVersion || 1);
    var maxAge = Number(root.dataset.consentMaxAge || 15552000);

    function showBanner() {
      banner.classList.remove("hidden");
    }

    function hideBanner() {
      banner.classList.add("hidden");
    }

    function currentConsentIsValid() {
      var consent = parseConsent();
      var timestamp = consent && Date.parse(consent.timestamp);
      return consent && Number(consent.version) === consentVersion && consent.necessary === true
        && (consent.status === "accepted" || consent.status === "rejected")
        && Number.isFinite(timestamp)
        && Date.now() - timestamp < maxAge * 1000;
    }

    function saveConsent(status) {
      consentVersion = Number(root.dataset.consentVersion || 1);
      maxAge = Number(root.dataset.consentMaxAge || 15552000);
      var payload = {
        version: consentVersion,
        necessary: true,
        status: status,
        timestamp: new Date().toISOString()
      };

      // Save the same first-party cookie immediately, including on a stale-CSRF
      // page or before navigation cancels the optional server acknowledgement.
      document.cookie = COOKIE_NAME + "=" + encodeURIComponent(JSON.stringify(payload))
        + "; Max-Age=" + maxAge
        + "; Expires=" + new Date(Date.now() + maxAge * 1000).toUTCString()
        + "; Path=/; SameSite=Lax" + (window.location.protocol === "https:" ? "; Secure" : "");
      if (!currentConsentIsValid()) {
        showBanner();
        return Promise.resolve();
      }
      hideBanner();
      document.dispatchEvent(new CustomEvent("cookies:updated", { detail: payload }));

      if (!endpoint) {
        return Promise.resolve();
      }
      return fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken") || root.dataset.csrfToken || "",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify(payload),
        credentials: "same-origin",
        keepalive: true
      }).then(function (response) {
        if (!response.ok) {
          throw new Error("Cookie preference acknowledgement failed");
        }
      }).catch(function () {
        // A failed acknowledgement does not discard the browser's saved choice.
        if (!currentConsentIsValid()) {
          showBanner();
        }
      });
    }

    // DOM properties are not serialized into HTMX history snapshots: a restored
    // node needs its own listeners even if its saved markup was initialized.
    if (!root.esfeCookieConsentBound) {
      root.querySelector("#cookie-accept-all").addEventListener("click", function () {
        saveConsent("accepted");
      });
      root.querySelector("#cookie-reject-all").addEventListener("click", function () {
        saveConsent("rejected");
      });
      root.esfeCookieConsentBound = true;
    }

    if (currentConsentIsValid()) {
      hideBanner();
    } else {
      showBanner();
    }
  }

  window.ESFECookieConsent = { init: init };
  window.openCookieSettings = function () {
    init();
    var banner = document.getElementById("cookie-banner");
    var accept = document.getElementById("cookie-accept-all");
    if (banner && accept) {
      banner.classList.remove("hidden");
      accept.focus();
    }
  };
  document.addEventListener("htmx:afterSwap", init);
  document.addEventListener("htmx:historyRestore", init);
  window.addEventListener("pageshow", init);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
