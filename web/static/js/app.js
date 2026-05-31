(function () {
    "use strict";

    async function apiRequest(url, options) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                "Accept": "application/json",
                ...(options && options.headers ? options.headers : {}),
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

    function setActiveNav() {
        const path = window.location.pathname;
        let bestMatch = null;
        document.querySelectorAll(".nav-link[href]").forEach((link) => {
            link.classList.remove("active");
            const href = link.getAttribute("href");
            if (!href) {
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

    window.DocFlow = {
        apiGet,
        apiPost,
        formatDateTime,
        showToast,
        setActiveNav,
    };

    document.addEventListener("DOMContentLoaded", setActiveNav);
})();
