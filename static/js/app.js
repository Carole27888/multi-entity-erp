/* App shell behaviour. Plain JS, no bundler. Load before alpine.min.js. */
(function () {
  "use strict";

  /* ---------- CSRF on every HTMX request ---------- */
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }
  document.addEventListener("htmx:configRequest", function (event) {
    event.detail.headers["X-CSRFToken"] = csrfToken();
  });

  /* ---------- Toasts ---------- */
  function toast(message, level, action) {
    var box = document.getElementById("toasts");
    if (!box || !message) return;
    var el = document.createElement("div");
    el.className = "toast toast--" + (level || "info");
    el.setAttribute("role", level === "error" || level === "danger" ? "alert" : "status");
    var text = document.createElement("span");
    text.textContent = message;
    el.appendChild(text);
    if (action) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--sm";
      btn.textContent = action.label;
      btn.addEventListener("click", action.onClick);
      el.appendChild(btn);
    }
    var close = document.createElement("button");
    close.type = "button";
    close.className = "toast__close";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = "&times;";
    close.addEventListener("click", function () { el.remove(); });
    el.appendChild(close);
    box.appendChild(el);
    if (!action) setTimeout(function () { el.remove(); }, 5000);
  }
  window.App = window.App || {};
  window.App.toast = toast;

  // Server sends: HX-Trigger: {"toast": {"message": "Lead saved", "level": "success"}}
  document.body.addEventListener("toast", function (event) {
    var d = event.detail || {};
    toast(d.message || d.value, d.level);
  });
  document.addEventListener("htmx:responseError", function (event) {
    var status = event.detail.xhr ? event.detail.xhr.status : 0;
    toast(status === 403 ? "You do not have permission to do that." : "Something went wrong. Please try again.", "error");
  });
  document.addEventListener("htmx:sendError", function () {
    toast("You appear to be offline. Check your connection.", "warning");
  });

  // Django messages rendered on the page load become toasts.
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-django-message]").forEach(function (node) {
      toast(node.textContent.trim(), node.getAttribute("data-level"));
      node.remove();
    });
  });

  /* ---------- Click to call: open the dialer, then the "log call" form when the agent comes back ---------- */
  var PENDING_CALL_KEY = "app-pending-call";
  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-log-call]");
    if (!link) return;
    try { sessionStorage.setItem(PENDING_CALL_KEY, link.getAttribute("data-log-call")); } catch (e) { /* ignore */ }
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible" || !window.htmx) return;
    var url = null;
    try { url = sessionStorage.getItem(PENDING_CALL_KEY); sessionStorage.removeItem(PENDING_CALL_KEY); } catch (e) { /* ignore */ }
    if (url) window.htmx.ajax("GET", url, { target: "#modal-root" });
  });

  /* ---------- Server asks for a form: HX-Trigger {"openModal": "<url>"} ---------- */
  document.body.addEventListener("openModal", function (event) {
    var url = event.detail && event.detail.value;
    if (url && window.htmx) window.htmx.ajax("GET", url, { target: "#modal-root" });
  });

  /* ---------- Installable app (PWA) ---------- */
  var deferredPrompt = null;
  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: window-controls-overlay)").matches ||
      window.navigator.standalone === true;
  }
  function isIOS() {
    var ua = window.navigator.userAgent;
    var iPadOS = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
    return /iPad|iPhone|iPod/.test(ua) || iPadOS;
  }
  function isIOSSafari() {
    var ua = window.navigator.userAgent;
    return isIOS() && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
  }
  var IOS_DISMISS_KEY = "app-ios-install-dismissed";
  var FOURTEEN_DAYS = 14 * 24 * 60 * 60 * 1000;
  function iosBannerDismissed() {
    try {
      var at = parseInt(localStorage.getItem(IOS_DISMISS_KEY) || "0", 10);
      return at && Date.now() - at < FOURTEEN_DAYS;
    } catch (e) { return false; }
  }

  document.addEventListener("alpine:init", function () {
    window.Alpine.store("pwa", {
      canInstall: false,
      installed: isStandalone(),
      isIOS: isIOS(),
      showIOSBanner: isIOSSafari() && !isStandalone() && !iosBannerDismissed(),
      install: function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(function () {
          deferredPrompt = null;
          window.Alpine.store("pwa").canInstall = false;
        });
      },
      dismissIOS: function () {
        try { localStorage.setItem(IOS_DISMISS_KEY, String(Date.now())); } catch (e) { /* private mode */ }
        this.showIOSBanner = false;
      }
    });
  });

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;
    if (window.Alpine) window.Alpine.store("pwa").canInstall = true;
  });
  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    if (window.Alpine) {
      window.Alpine.store("pwa").canInstall = false;
      window.Alpine.store("pwa").installed = true;
    }
    toast((document.querySelector("meta[name=application-name]") || {}).content + " is installed.", "success");
  });

  /* ---------- Service worker ---------- */
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (reg) {
        function offerUpdate(worker) {
          toast("A new version is available", "info", {
            label: "Refresh",
            onClick: function () { worker.postMessage({ type: "SKIP_WAITING" }); }
          });
        }
        if (reg.waiting && navigator.serviceWorker.controller) offerUpdate(reg.waiting);
        reg.addEventListener("updatefound", function () {
          var worker = reg.installing;
          if (!worker) return;
          worker.addEventListener("statechange", function () {
            if (worker.state === "installed" && navigator.serviceWorker.controller) offerUpdate(worker);
          });
        });
      }).catch(function () { /* SW is an enhancement */ });

      // Reload only when a new version replaces an existing worker (not on the very first install).
      var hadController = !!navigator.serviceWorker.controller;
      var reloading = false;
      navigator.serviceWorker.addEventListener("controllerchange", function () {
        if (reloading || !hadController) return;
        reloading = true;
        window.location.reload();
      });
    });
  }
})();
