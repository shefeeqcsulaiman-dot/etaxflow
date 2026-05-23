import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import QRCode from "qrcode";
import { api, clearToken, getToken, setToken } from "./api";
import "./styles.css";

const TAXFLOW_LEGACY_VERSION = "20260523-dashboard-remove-new-invoice";

function App() {
  const [tokenReady, setTokenReady] = useState(Boolean(getToken()));
  const [error, setError] = useState("");

  useEffect(() => {
    if (!tokenReady) return;
    api("/auth/me").catch((err) => {
      setError(err.message);
      clearToken();
      setTokenReady(false);
    });
  }, [tokenReady]);

  async function login(email, password) {
    setError("");
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(data.access_token);
      setTokenReady(true);
    } catch (err) {
      setError("Could not sign in. Use admin@taxflowapp.com / admin123 and make sure the API is running on 127.0.0.1:8000.");
      throw err;
    }
  }

  if (!tokenReady) return <Login onLogin={login} error={error} />;

  return <TaxFlowLegacyApp onLogout={() => {
    clearToken();
    setTokenReady(false);
  }} />;
}

function TaxFlowLegacyApp({ onLogout }) {
  const mountedRef = useRef(false);
  const [loadMessage, setLoadMessage] = useState("Preparing TaxFlow...");

  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;
    let cancelled = false;

    async function mountOriginalDesign() {
      setLoadMessage("Loading workspace...");
      preloadTaxFlowAssets();
      const response = await fetch(versionedTaxFlowUrl("/taxflow/index.html"), { cache: "default" });
      if (!response.ok) throw new Error(`TaxFlow shell returned ${response.status}`);
      const html = await response.text();
      if (cancelled) return;

      setLoadMessage("Building interface...");
      const doc = new DOMParser().parseFromString(html, "text/html");
      document.body.className = doc.body.className || "theme-light";
      document.title = doc.title || "TaxFlow UAE - Business Management Platform";
      ensureStylesheet("taxflow-fonts", "https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400;500&display=swap");
      ensureStylesheet("taxflow-original-css", versionedTaxFlowUrl("/taxflow/src/styles.css"));

      document.body.innerHTML = doc.body.innerHTML
        .replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/<noscript[\s\S]*?<\/noscript>/gi, "");

      window.__taxflowLogout = onLogout;
      const localApiHost = ["localhost", "::1", ""].includes(window.location.hostname) ? "127.0.0.1" : window.location.hostname;
      window.TAXFLOW_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `http://${localApiHost}:8000/api/v1`;
      window.TaxFlowQRCode = QRCode;
      setLoadMessage("Starting app...");
      await loadScriptOnce("taxflow-original-js", versionedTaxFlowUrl("/taxflow/src/app.js"));
      patchLegacyLogout(onLogout);
      patchBackendBridge();
      if (!window.__taxflowAppInitialized) window.initApp?.();
      window.go?.("dashboard");
      window.setTimeout?.(() => {
        window.forceDbRefresh?.();
      }, 250);
      window.toast?.("TaxFlow app loaded", "ok");
    }

    mountOriginalDesign().catch((err) => {
      document.body.innerHTML = `<div class="mount-error">Could not load TaxFlow design: ${err.message}</div>`;
    });

    return () => {
      cancelled = true;
    };
  }, [onLogout]);

  return (
    <main className="taxflow-loader" aria-live="polite">
      <div className="taxflow-loader-box">
        <div className="loader-brand">Tax<span>Flow</span></div>
        <div className="loader-bar"><span /></div>
        <p>{loadMessage}</p>
      </div>
    </main>
  );
}

function preloadTaxFlowAssets() {
  ensureResourceHint("taxflow-fonts-preconnect", "preconnect", "https://fonts.googleapis.com");
  ensureResourceHint("taxflow-fonts-static-preconnect", "preconnect", "https://fonts.gstatic.com", true);
  ensureResourceHint("taxflow-html-prefetch", "prefetch", versionedTaxFlowUrl("/taxflow/index.html"));
  ensureResourceHint("taxflow-css-preload", "preload", versionedTaxFlowUrl("/taxflow/src/styles.css"), false, "style");
  ensureResourceHint("taxflow-js-preload", "preload", versionedTaxFlowUrl("/taxflow/src/app.js"), false, "script");
}

function versionedTaxFlowUrl(path) {
  return `${path}?v=${TAXFLOW_LEGACY_VERSION}`;
}

function ensureStylesheet(id, href) {
  const existing = document.getElementById(id);
  if (existing) {
    existing.href = href;
    return;
  }
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function ensureResourceHint(id, rel, href, crossOrigin = false, as) {
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = rel;
  link.href = href;
  if (as) link.as = as;
  if (crossOrigin) link.crossOrigin = "";
  document.head.appendChild(link);
}

function loadScriptOnce(id, src) {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id);
    if (existing) {
      if (existing.dataset.loaded === "true") {
        resolve();
        return;
      }
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.id = id;
    script.src = src;
    script.defer = true;
    script.onload = () => {
      script.dataset.loaded = "true";
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(script);
  });
}

function patchLegacyLogout(onLogout) {
  window.logout = () => {
    window.toast?.("Logged out. Session cleared locally.", "info");
    onLogout();
    window.location.reload();
  };
}

function patchBackendBridge() {
  window.TaxFlowAPI = {
    async createInvoice(payload) {
      return api("/invoices", { method: "POST", body: JSON.stringify(payload) });
    },
    async listInvoices() {
      return api("/invoices");
    },
    async runVatSummary() {
      return api("/jobs/vat-summary", { method: "POST", body: JSON.stringify({}) });
    },
  };
}

function Login({ onLogin, error }) {
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await onLogin(form.get("email"), form.get("password"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login-box" onSubmit={submit}>
        <div>
          <div className="brand">Tax<span>Flow</span></div>
          <p>Sign in to open the complete TaxFlow business platform connected to the database.</p>
        </div>
        <input name="email" type="email" defaultValue="admin@taxflowapp.com" required />
        <input name="password" type="password" defaultValue="admin123" required />
        {error && <div className="alert">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
      </form>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
