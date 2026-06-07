/**
 * status.js
 * Small helper utilities for auth handling and periodic polling on dashboard pages.
 */

(function () {
    function getToken() {
        return null;
    }

    function ensureAuth() {
        return true;
    }

    async function authFetch(url, options = {}) {
        ensureAuth();
        const resp = await fetch(
            url,
            Object.assign({}, options, { credentials: options.credentials || 'same-origin' })
        );
        if (resp.status === 401) {
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
