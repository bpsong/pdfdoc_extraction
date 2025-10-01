/**
 * status.js
 * Small helper utilities for auth handling and periodic polling on dashboard pages.
 */

(function () {
    function getToken() {
        return localStorage.getItem('access_token');
    }

    function ensureAuth() {
        const t = getToken();
        if (!t) {
            window.location.href = '/login';
            return null;
        }
        return t;
    }

    async function authFetch(url, options = {}) {
        const token = ensureAuth();
        if (!token) {
            throw new Error('No token');
        }
        const headers = Object.assign({}, options.headers || {}, {
            'Authorization': 'Bearer ' + token
        });
        const resp = await fetch(url, Object.assign({}, options, { headers }));
        if (resp.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
            throw new Error('Unauthorized');
        }
        return resp;
    }

    // Expose helpers
    window.StatusHelpers = {
        getToken,
        ensureAuth,
        authFetch
    };
})();