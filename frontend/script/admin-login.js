(function () {
  "use strict";

  const form = document.getElementById("loginForm");
  if (!form) return;

  const tabs = Array.from(form.querySelectorAll("[data-login-tab]"));
  const panels = {
    patient: document.getElementById("patientLoginPanel"),
    admin: document.getElementById("adminLoginPanel")
  };
  const credentials = document.getElementById("adminCredentials");
  const verification = document.getElementById("adminVerification");
  const submitButton = document.getElementById("adminSubmit");
  const message = document.getElementById("adminMsg");
  let verifyingCode = false;

  function setMode(mode, updateUrl) {
    document.body.dataset.loginMode = mode;
    tabs.forEach((tab) => {
      const active = tab.dataset.loginTab === mode;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    Object.entries(panels).forEach(([name, panel]) => {
      panel.hidden = name !== mode;
    });
    if (updateUrl) {
      const url = new URL(window.location.href);
      if (mode === "admin") url.searchParams.set("tab", "admin");
      else url.searchParams.delete("tab");
      window.history.replaceState(null, "", url);
    }
  }

  function setMessage(text, isError) {
    message.textContent = text;
    message.classList.toggle("error", Boolean(isError));
  }

  async function sendCode() {
    const email = document.getElementById("adminEmail").value.trim();
    const password = document.getElementById("adminPassword").value;
    if (!email || !password) {
      setMessage("Enter your admin email and password.", true);
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Checking credentials...";
    setMessage("", false);
    try {
      const response = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: email, password })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        const error = data.error === "not_admin"
          ? "This account does not have administrator access."
          : data.error === "invalid_credentials"
            ? "Invalid admin email or password."
            : data.error === "too_many"
              ? "Too many attempts. Please wait and try again."
              : data.error === "email_unavailable"
                ? "Unable to send a verification code right now. Please try again later."
                : "Could not verify admin credentials. Please try again.";
        setMessage(error, true);
        return;
      }

      verifyingCode = true;
      credentials.hidden = true;
      verification.hidden = false;
      document.getElementById("adminEmailDisplay").textContent = email;
      submitButton.textContent = "Verify & Sign In";
      document.getElementById("adminCode").focus();
      setMessage("Verification code sent. Check your email.", false);
    } catch (error) {
      console.error("Admin login request failed:", error);
      setMessage("Unable to reach the server. Check your connection and try again.", true);
    } finally {
      submitButton.disabled = false;
      if (!verifyingCode) submitButton.textContent = "Continue";
    }
  }

  async function verifyCode() {
    const email = document.getElementById("adminEmail").value.trim();
    const code = document.getElementById("adminCode").value.trim();
    if (!/^\d{6}$/.test(code)) {
      setMessage("Enter the 6-digit verification code.", true);
      document.getElementById("adminCode").focus();
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Verifying...";
    setMessage("", false);
    try {
      const response = await fetch("/api/admin/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: email, code })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setMessage(
          data.error === "expired_code"
            ? "That code has expired. Request a new one."
            : "Invalid verification code. Please try again.",
          true
        );
        return;
      }
      window.location.replace("/admin");
    } catch (error) {
      console.error("Admin verification request failed:", error);
      setMessage("Unable to reach the server. Check your connection and try again.", true);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Verify & Sign In";
    }
  }

  function submit() {
    if (verifyingCode) verifyCode();
    else sendCode();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      setMode(tab.dataset.loginTab, true);
      if (tab.dataset.loginTab === "admin") document.getElementById("adminEmail").focus();
    });
    tab.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      next.click();
    });
  });

  document.getElementById("adminResend").addEventListener("click", sendCode);
  document.getElementById("adminCode").addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "").slice(0, 6);
  });
  document.getElementById("adminEye").addEventListener("click", () => {
    const input = document.getElementById("adminPassword");
    const slash = document.getElementById("adminEyeSlash");
    const visible = input.type === "password";
    input.type = visible ? "text" : "password";
    slash.style.display = visible ? "none" : "";
    document.getElementById("adminEye").setAttribute("aria-label", visible ? "Hide password" : "Show password");
  });

  const initialMode = new URLSearchParams(window.location.search).get("tab") === "admin" ? "admin" : "patient";
  setMode(initialMode, false);
  window.AdminLogin = { submit };
})();
