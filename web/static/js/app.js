(function () {
    "use strict";

    const CSRF_COOKIE_NAME = "csrf_token";
    const CSRF_HEADER_NAME = "X-CSRF-Token";
    const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
    const FAILURE_NOTIFICATION_CACHE_KEY = "docflow.failureNotifications";
    const FAILURE_NOTIFICATION_CACHE_TTL_MS = 60_000;

    function readCookie(name) {
        const prefix = `${encodeURIComponent(name)}=`;
        const cookies = document.cookie ? document.cookie.split(";") : [];
        for (const rawCookie of cookies) {
            const cookie = rawCookie.trim();
            if (cookie.startsWith(prefix)) {
                return decodeURIComponent(cookie.slice(prefix.length));
            }
        }
        return "";
    }

    function csrfHeaders(method) {
        const requestMethod = String(method || "GET").toUpperCase();
        const token = readCookie(CSRF_COOKIE_NAME);
        if (SAFE_METHODS.has(requestMethod) || !token) {
            return {};
        }
        return { [CSRF_HEADER_NAME]: token };
    }

    async function apiRequest(url, options) {
        const requestOptions = options || {};
        const requestMethod = requestOptions.method || "GET";
        const response = await fetch(url, {
            credentials: "same-origin",
            ...requestOptions,
            headers: {
                "Accept": "application/json",
                ...csrfHeaders(requestMethod),
                ...(requestOptions.headers ? requestOptions.headers : {}),
            },
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return null;
        }

        if (!response.ok) {
            let detail = response.statusText;
            try {
                const payload = await response.json();
                detail = payload.detail || detail;
            } catch (error) {
                detail = response.statusText;
            }
            throw new Error(detail || `Request failed with status ${response.status}`);
        }

        if (response.status === 204) {
            return null;
        }

        return response.json();
    }

    async function apiGet(url) {
        return apiRequest(url, { method: "GET" });
    }

    async function apiPost(url, payload) {
        return apiRequest(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload || {}),
        });
    }

    async function apiPut(url, payload) {
        return apiRequest(url, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload || {}),
        });
    }

    function formatDateTime(isoString) {
        if (!isoString) {
            return "";
        }
        const value = new Date(isoString);
        if (Number.isNaN(value.getTime())) {
            return String(isoString);
        }
        return new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "short",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        }).format(value);
    }

    function ensureToastRoot() {
        let root = document.getElementById("toast-root");
        if (!root) {
            root = document.createElement("div");
            root.id = "toast-root";
            root.className = "toast toast-end z-50";
            document.body.appendChild(root);
        }
        return root;
    }

    function showToast(message, type) {
        const toastType = type || "info";
        const alert = document.createElement("div");
        alert.className = `alert alert-${toastType} shadow-lg text-sm`;
        alert.textContent = message;
        ensureToastRoot().appendChild(alert);
        window.setTimeout(() => alert.remove(), 4500);
    }

    function storageGet(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            // Ignore storage failures; the visible toggle state still updates.
        }
    }

    function isReviewDetailPath(path) {
        return /^\/app\/review\/[^/]+/.test(path || "");
    }

    function shouldAutoCollapseSidebar() {
        return isReviewDetailPath(window.location.pathname)
            && window.matchMedia("(max-width: 1535px)").matches;
    }

    function applySidebarCollapsed(collapsed) {
        const toggle = document.getElementById("sidebar-collapse-toggle");
        document.body.classList.toggle("sidebar-collapsed", collapsed);
        if (!toggle) {
            return;
        }
        toggle.setAttribute("aria-pressed", collapsed ? "true" : "false");
        toggle.setAttribute("aria-label", collapsed ? "Expand navigation" : "Collapse navigation");
        toggle.title = collapsed ? "Expand navigation" : "Collapse navigation";
    }

    function initializeSidebar() {
        const toggle = document.getElementById("sidebar-collapse-toggle");
        if (!toggle) {
            return;
        }
        const path = window.location.pathname;
        document.body.classList.toggle("review-detail-route", isReviewDetailPath(path));
        const stored = storageGet("docflow.sidebarCollapsed");
        const initialCollapsed = stored === "true" || (stored !== "false" && shouldAutoCollapseSidebar());
        applySidebarCollapsed(initialCollapsed);
        toggle.addEventListener("click", () => {
            const collapsed = !document.body.classList.contains("sidebar-collapsed");
            storageSet("docflow.sidebarCollapsed", collapsed ? "true" : "false");
            applySidebarCollapsed(collapsed);
        });
        const laptopQuery = window.matchMedia("(max-width: 1535px)");
        const syncAutoCollapse = () => {
            if (storageGet("docflow.sidebarCollapsed") === null) {
                applySidebarCollapsed(shouldAutoCollapseSidebar());
            }
        };
        if (typeof laptopQuery.addEventListener === "function") {
            laptopQuery.addEventListener("change", syncAutoCollapse);
        } else if (typeof laptopQuery.addListener === "function") {
            laptopQuery.addListener(syncAutoCollapse);
        }
    }

    function setActiveNav() {
        const path = window.location.pathname;
        const routeAlias = path === "/app/processing" || path.startsWith("/app/batches") || path.startsWith("/app/documents")
            ? "/app/upload"
            : null;
        let bestMatch = null;
        document.querySelectorAll(".nav-link[href]").forEach((link) => {
            link.classList.remove("active");
            const href = link.getAttribute("href");
            if (!href) {
                return;
            }
            if (routeAlias && href === routeAlias) {
                bestMatch = { href, link };
                return;
            }
            const exact = path === href;
            const nested = href !== "/app/upload" && path.startsWith(`${href}/`);
            if (exact || nested) {
                if (!bestMatch || href.length > bestMatch.href.length) {
                    bestMatch = { href, link };
                }
            }
        });
        if (bestMatch) {
            bestMatch.link.classList.add("active");
        }
    }

    function readFailureNotificationCache() {
        const rawValue = storageGet(FAILURE_NOTIFICATION_CACHE_KEY);
        if (!rawValue) {
            return null;
        }
        try {
            const cached = JSON.parse(rawValue);
            const count = Number(cached.count || 0);
            const cachedAt = Number(cached.cachedAt || 0);
            if (!Number.isFinite(count) || !Number.isFinite(cachedAt) || cachedAt <= 0) {
                return null;
            }
            return { count, cachedAt };
        } catch (error) {
            return null;
        }
    }

    function writeFailureNotificationCache(count) {
        storageSet(FAILURE_NOTIFICATION_CACHE_KEY, JSON.stringify({
            count,
            cachedAt: Date.now(),
        }));
    }

    function applyFailureNotifications(payload) {
        const button = document.getElementById("failure-notification-button");
        const badge = document.getElementById("failure-notification-badge");
        if (!button || !badge) {
            return payload || { count: 0 };
        }
        const count = Number(payload && payload.count ? payload.count : 0);
        if (count > 0) {
            badge.textContent = count > 99 ? "99+" : String(count);
            badge.classList.remove("hidden");
            button.disabled = false;
            button.classList.remove("btn-disabled");
            button.title = `${count} fatal failure${count === 1 ? "" : "s"}`;
            button.setAttribute("aria-label", `${count} fatal failure notifications`);
            button.onclick = () => {
                window.location.href = "/app/failures";
            };
        } else {
            badge.classList.add("hidden");
            badge.textContent = "0";
            button.disabled = true;
            button.classList.add("btn-disabled");
            button.title = "No fatal failure notifications";
            button.setAttribute("aria-label", "No fatal failure notifications");
            button.onclick = null;
        }
        return { ...(payload || {}), count };
    }

    async function refreshFailureNotifications(options) {
        const requestOptions = options || {};
        const cached = readFailureNotificationCache();
        if (
            !requestOptions.force
            && cached
            && Date.now() - cached.cachedAt < FAILURE_NOTIFICATION_CACHE_TTL_MS
        ) {
            return applyFailureNotifications({ ...cached, cached: true });
        }
        try {
            const payload = await apiGet("/api/failures/notifications");
            const count = Number(payload && payload.count ? payload.count : 0);
            writeFailureNotificationCache(count);
            return applyFailureNotifications({ ...(payload || {}), count });
        } catch (error) {
            if (cached) {
                return applyFailureNotifications({
                    ...cached,
                    stale: true,
                    error: error.message || "Unable to load failure notifications",
                });
            }
            applyFailureNotifications({ count: 0 });
            return { count: 0, error: error.message || "Unable to load failure notifications" };
        }
    }

    window.DocFlow = {
        apiGet,
        apiPost,
        apiPut,
        csrfHeaders,
        formatDateTime,
        showToast,
        setActiveNav,
        refreshFailureNotifications,
    };

    document.addEventListener("DOMContentLoaded", () => {
        initializeSidebar();
        setActiveNav();
        refreshFailureNotifications();
    });
})();
