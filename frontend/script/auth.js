(function () {
    "use strict";

    const IN_PAGES = /\/pages\//.test(location.pathname);
    const LOGIN = IN_PAGES ? "login.html" : "pages/login.html";
    const HOME = IN_PAGES ? "../index.html" : "index.html";
    const API = "/api";

    function call(method, path, body) {
        if (window.location.protocol === "file:") {
            return { status: 0, data: { ok: false, error: "server_required" }, json: false };
        }

        try {
            const xhr = new XMLHttpRequest();
            xhr.open(method, API + path, false);
            xhr.setRequestHeader("Content-Type", "application/json");
            xhr.send(body === undefined ? null : JSON.stringify(body));

            let data = {};
            try { data = JSON.parse(xhr.responseText || "{}"); } catch (e) { }

            if (xhr.status >= 500) {
                console.error("Server error (" + xhr.status + "):", data.error || xhr.responseText);
            }

            return {
                status: xhr.status,
                data: data,
                json: (xhr.getResponseHeader("Content-Type") || "").includes("application/json")
            };
        } catch (e) {
            return { status: 0, data: { ok: false, error: "network" }, json: false };
        }
    }

    let cache = null;

    function refresh() {
        const r = call("GET", "/me");
        cache = r.status === 200 && r.data && r.data.user ? r.data.user : null;
        return cache;
    }

    async function refreshAsync() {
        const response = await fetch(API + "/me", { cache: "no-store" });
        if (!response.ok) {
            throw new Error("Could not refresh account data (" + response.status + ").");
        }
        const data = await response.json();
        if (!data.ok || !Object.prototype.hasOwnProperty.call(data, "user")) {
            throw new Error("The account refresh response was invalid.");
        }
        cache = data.user || null;
        if (!cache && document.documentElement.hasAttribute("data-requires-login")) {
            location.replace(LOGIN);
        }
        return cache;
    }

    function refreshGuestSession() {
        if (window.location.protocol === "file:") {
            return;
        }

        const xhr = new XMLHttpRequest();
        xhr.open("GET", API + "/me", true);
        xhr.onload = function () {
            let data = {};
            try {
                data = JSON.parse(xhr.responseText || "{}");
            } catch (e) {
                console.error("Could not check the current login session: invalid server response.");
                return;
            }

            if (xhr.status >= 500) {
                console.error("Could not check the current login session (server error " + xhr.status + ").");
                return;
            }

            cache = xhr.status === 200 && data.user ? data.user : null;
            if (cache && document.documentElement.hasAttribute("data-guest-only")) {
                location.replace(HOME);
            }
        };
        xhr.onerror = function () {
            console.error("Could not reach the server to check the current login session.");
        };
        xhr.send();
    }

    if (document.documentElement.hasAttribute("data-guest-only")) {
        refreshGuestSession();
    } else {
        refresh();
    }

    // --- BAN CHECK HEARTBEAT ---
    // If the user is logged in, check every 15 seconds if they got banned.
    if (cache) {
        setInterval(() => {
            const r = call("GET", "/me");
            if (r.status === 200 && (!r.data || !r.data.user)) {
                alert("Your session has ended or your account is unavailable. Please sign in again.");
                window.location.href = LOGIN;
            }
        }, 15000);
    }

    function normalize(raw) {
        return String(raw || "").trim().toLowerCase();
    }

    const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v);

    const validId = (raw) => {
        const n = normalize(raw);
        return isEmail(n);
    };

    function nameFromId(n) {
        if (!isEmail(n)) {
            return "Patient";
        }

        const words = n
            .split("@")[0]
            .split(/[._\-+0-9]+/)
            .filter(Boolean);

        return (
            words.map((w) => w[0].toUpperCase() + w.slice(1)).join(" ") ||
            "Patient"
        );
    }

    function defaultProfile(n) {
        return {
            name: nameFromId(n),
            email: isEmail(n) ? n : "",
            phone: isEmail(n) ? "" : n,
            code: "+63",
            photo: ""
        };
    }

    function createUser(raw, pw, profile) {
        profile = profile || {};
        const name = String(profile.name || "").trim();

        if (!name || name.length > 200) {
            return { ok: false, error: "invalid_name" };
        }

        const r = call("POST", "/signup", {
            id: raw,
            password: pw,
            profile: { name: name }
        });

        if (r.data && r.data.ok) {
            return { ok: true, id: r.data.id, needs_verification: r.data.needs_verification };
        }

        return {
            ok: false,
            error: (r.data && r.data.error) ||
                (r.status === 0 ? "network" :
                    !r.json ? "server_required" : "error")
        };
    }

    function verifySignup(raw, code) {
        const r = call("POST", "/signup/verify", { id: raw, code: code });
        if (r.data && r.data.ok) {
            return { ok: true };
        }
        return { ok: false, error: (r.data && r.data.error) || "invalid_code" };
    }

    function verify(raw, pw) {
        const r = call("POST", "/verify", { id: raw, password: pw });

        if (r.data && r.data.ok) {
            return { ok: true, id: r.data.id, needsEmail: !!r.data.needs_email, email: r.data.email || "" };
        }

        return {
            ok: false,
            reason: (r.data && r.data.error) || (r.data && r.data.reason) ||
                (r.status === 0 ? "network" :
                    !r.json ? "server_required" : "error")
        };
    }

    function loginStatus(cb) {
        const xhr = new XMLHttpRequest();
        xhr.open("GET", API + "/login-status", true);
        xhr.onload = function () {
            let d = {};
            try { d = JSON.parse(xhr.responseText || "{}"); } catch (e) { }
            cb({ confirmed: !!d.confirmed, expired: !!d.expired });
        };
        xhr.onerror = function () { cb({ confirmed: false, expired: false, network: true }); };
        xhr.send();
    }

    function resendLoginEmail() {
        const r = call("POST", "/login/resend");
        return r.data && r.data.ok
            ? { ok: true }
            : { ok: false, reason: (r.data && r.data.error) || (r.status === 0 ? "network" : "error") };
    }

    function confirmLogin(token) {
        const r = call("POST", "/confirm-login", { token: token });
        return r.data && r.data.ok
            ? { ok: true }
            : { ok: false, reason: (r.data && r.data.error) || (r.status === 0 ? "network" : "error") };
    }

    function current() {
        return cache ? cache.id : null;
    }

    function login(raw) {
        const r = call("POST", "/login", { id: raw });

        if (r.data && r.data.ok) {
            refresh();
            return { ok: true };
        }

        return {
            ok: false,
            reason: (r.data && (r.data.reason || r.data.error)) ||
                (r.status === 0 ? "network" :
                    !r.json ? "server_required" : "error")
        };
    }

    function logout() {
        call("POST", "/logout");
        cache = null;
    }

    function profile() {
        return cache
            ? Object.assign({}, defaultProfile(cache.id), cache.profile || {})
            : defaultProfile("");
    }

    function saveProfile(patch) {
        if (!cache) {
            return null;
        }

        const r = call("PUT", "/profile", patch);

        if (r.data && r.data.ok) {
            cache.profile = r.data.profile;
            return r.data.profile;
        }

        return null;
    }

    function checkPassword(pw) {
        if (!cache) {
            return false;
        }

        const r = call("POST", "/password/check", { password: pw });
        return !!(r.data && r.data.ok);
    }

    function setPassword(pw) {
        if (!cache) {
            return false;
        }

        const r = call("PUT", "/password", { password: pw });
        return !!(r.data && r.data.ok);
    }

    function deleteAccount() {
        if (!cache) {
            return;
        }

        const r = call("DELETE", "/account");

        if (r.data && r.data.ok) {
            cache = null;
        }
    }

    function getData(key, fallback) {
        return cache &&
            cache.data &&
            Object.prototype.hasOwnProperty.call(cache.data, key)
            ? cache.data[key]
            : fallback;
    }

    function setData(key, value) {
        if (!cache) {
            return false;
        }

        const r = call("PUT", "/data/" + encodeURIComponent(key), { value: value });

        if (r.data && r.data.ok) {
            cache.data = cache.data || {};
            cache.data[key] = value;
            return true;
        }

        return false;
    }

    const getAppointments = () => {
        const list = getData("appointments", []);
        const items = (Array.isArray(list) ? list : []);
        
        let maxId = 0;
        items.forEach((a) => {
            const n = parseInt(a.id, 10);
            if (Number.isInteger(n) && n > maxId) maxId = n;
        });
        return items.map((a) => {
            const n = parseInt(a.id, 10);
            return Number.isInteger(n) ? Object.assign({}, a, { id: n }) : Object.assign({}, a, { id: ++maxId });
        });
    };

    const saveAppointments = (list) => setData("appointments", list);

    const todayISO = () => {
        const d = new Date();
        return (
            d.getFullYear() + "-" +
            String(d.getMonth() + 1).padStart(2, "0") + "-" +
            String(d.getDate()).padStart(2, "0")
        );
    };

    function slotEnd(a) {
        if (!a || !a.date) return null;

        const [y, m, d] = String(a.date).slice(0, 10).split("-").map(Number);
        if (!y || !m || !d) return null;

        const times = String(a.time || "").match(/(\d{1,2}):(\d{2})\s*(AM|PM)/gi);
        let h = 23, min = 59;

        if (times && times.length) {
            const t = times[times.length - 1].match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
            h = Number(t[1]) % 12 + (t[3].toUpperCase() === "PM" ? 12 : 0);
            min = Number(t[2]);
        }

        return new Date(y, m - 1, d, h, min);
    }

    function recordState(a) {
        const status = String((a && a.status) || "").toLowerCase();

        if (status === "cancelled") return "Cancelled";
        if (status === "completed") return "Completed";

        const end = slotEnd(a);
        return end && end < new Date() ? "Completed" : "Pending";
    }

    function initials(name) {
        const w = String(name || "").trim().split(/\s+/).filter(Boolean);
        if (!w.length) return "?";
        return ((w[0][0] || "") + (w.length > 1 ? w[w.length - 1][0] : "")).toUpperCase();
    }

    function initSidebar() {
        const $ = (id) => document.getElementById(id);
        const sidebar = $("sidebar");
        const scrim = $("scrim");
        const menuBtn = $("menuBtn");
        const closeBtn = $("closeSidebar");
        const search = $("navSearch");
        const noMatch = $("noMatch");

        if (!sidebar) {
            return { setSidebar: function () { } };
        }

        function setSidebar(open) {
            sidebar.classList.toggle("open", !!open);
            if (scrim) scrim.classList.toggle("open", !!open);
            sidebar.setAttribute("aria-hidden", String(!open));
            if (menuBtn) menuBtn.setAttribute("aria-expanded", String(!!open));

            if (open) {
                if (closeBtn) closeBtn.focus();
            } else if (menuBtn && sidebar.contains(document.activeElement)) {
                menuBtn.focus();
            }
        }

        if (menuBtn) menuBtn.addEventListener("click", () => setSidebar(true));
        if (closeBtn) closeBtn.addEventListener("click", () => setSidebar(false));
        if (scrim) scrim.addEventListener("click", () => setSidebar(false));
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") setSidebar(false);
        });

        function paintAccount() {
            const p = profile();
            const avatar = $("sideAvatar");
            const nameEl = $("sideName");
            const mailEl = $("sideEmail");

            if (nameEl) nameEl.textContent = p.name || "";
            if (mailEl) mailEl.textContent = p.email || p.phone || "";

            if (avatar) {
                avatar.textContent = "";
                const img = document.createElement("img");
                img.alt = "";
                img.onerror = function () {
                    if (!avatar.contains(img)) return;
                    avatar.textContent = initials(p.name);
                };
                img.src = (p.photo || "/api/profile/photo") + "?v=" + Date.now();
                avatar.appendChild(img);
            }
        }
        paintAccount();

        function filterNav() {
            if (!search) return;
            const q = search.value.trim().toLowerCase();
            let shown = 0;

            sidebar.querySelectorAll("#nav a").forEach((a) => {
                const hit = !q || a.textContent.toLowerCase().includes(q);
                a.hidden = !hit;
                if (hit) shown++;
            });

            if (noMatch) noMatch.hidden = shown > 0;
        }
        if (search) search.addEventListener("input", filterNav);
        window.addEventListener("langchange", filterNav);

        document.querySelectorAll(".logout").forEach((logoutLink) => {
            logoutLink.addEventListener("click", () => { logout(); });
        });

        return { setSidebar: setSidebar };
    }

    function requestReset(email) {
        const r = call("POST", "/forgot-password", { email: normalize(email) });
        return r.data && r.data.ok
            ? { ok: true }
            : { ok: false, reason: (r.data && r.data.error) || (r.status === 0 ? "network" : "error") };
    }

    function resetPassword(token, pw) {
        const r = call("POST", "/reset-password", { token: token, password: pw });
        return r.data && r.data.ok
            ? { ok: true }
            : { ok: false, reason: (r.data && r.data.error) || (r.status === 0 ? "network" : "error") };
    }

    const Auth = {
        LOGIN: LOGIN,
        HOME: HOME,

        normalize: normalize,
        isEmail: isEmail,
        validId: validId,

        createUser: createUser,
        verifySignup: verifySignup,
        verify: verify,
        current: current,
        login: login,
        logout: logout,

        profile: profile,
        saveProfile: saveProfile,

        checkPassword: checkPassword,
        setPassword: setPassword,
        deleteAccount: deleteAccount,

        getData: getData,
        setData: setData,

        getAppointments: getAppointments,
        saveAppointments: saveAppointments,
        todayISO: todayISO,
        recordState: recordState,

        initSidebar: initSidebar,
        loginStatus: loginStatus,
        resendLoginEmail: resendLoginEmail,
        confirmLogin: confirmLogin,
        requestReset: requestReset,
        resetPassword: resetPassword,

        refresh: refresh,
        refreshAsync: refreshAsync
    };

    window.Auth = Auth;

    (function enforcePageRules() {
        const html = document.documentElement;

        if (html.hasAttribute("data-requires-login") && !current()) {
            location.replace(LOGIN);
            return;
        }

        if (html.hasAttribute("data-guest-only") && current()) {
            location.replace(HOME);
        }
    })();

    function toggleSignupPassword(inputId, buttonId) {
        const inputField = document.getElementById(inputId);
        const eyeButton = document.getElementById(buttonId);
        if (!inputField || !eyeButton) return;

        const svg = eyeButton.querySelector('svg');
        const existingSlash = document.getElementById(buttonId + "-slash");

        if (inputField.type === "password") {
            inputField.type = "text";
            if (existingSlash) {
                existingSlash.remove();
            }
        } else {
            inputField.type = "password";
            if (!existingSlash) {
                const line = document.createElementNS("http://w3.org", "line");
                line.setAttribute("id", buttonId + "-slash");
                line.setAttribute("x1", "1");
                line.setAttribute("y1", "1");
                line.setAttribute("x2", "23");
                line.setAttribute("y2", "23");
                svg.appendChild(line);
            }
        }
    }
    window.toggleSignupPassword = toggleSignupPassword;
})();