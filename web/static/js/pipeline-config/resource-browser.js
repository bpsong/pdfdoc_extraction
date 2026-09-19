/** Directory/file browsing and CSV metadata behavior for pipeline task editors. */

export function createPipelineResourceBrowser(context) {
    const {
        state,
        api,
        render,
        markDirty,
        paramsForSelected,
        setParamsError,
        getParam,
        setParam,
        showError,
        getNewDirectoryName,
    } = context;

    function browserStartPath(value) {
        const text = String(value || ".").replace(/\\/g, "/").trim();
        if (!text || /^[A-Za-z]:\//.test(text) || text.startsWith("/") || text.includes("..")) {
            return ".";
        }
        return text;
    }

    async function loadDirectoryBrowser(path) {
        if (!state.directoryBrowser) {
            return;
        }
        state.directoryBrowser.current = path || ".";
        state.directoryBrowser.loading = true;
        state.directoryBrowser.error = "";
        render();
        try {
            const payload = state.directoryBrowser.mode === "file"
                ? await api.listFiles(path, state.directoryBrowser.extensions)
                : await api.listDirectories(path);
            if (!state.directoryBrowser) {
                return;
            }
            state.directoryBrowser.listing = payload;
            state.directoryBrowser.current = payload.current || path || ".";
            state.directoryBrowser.loading = false;
            state.directoryBrowser.error = "";
        } catch (error) {
            if (!state.directoryBrowser) {
                return;
            }
            state.directoryBrowser.loading = false;
            state.directoryBrowser.error = error.message || "Unable to browse directories";
        }
        render();
    }

    function openDirectoryBrowser(button) {
        let path = [];
        try {
            path = JSON.parse(button.dataset.paramPath || "[]");
        } catch (error) {
            path = [];
        }
        const current = browserStartPath(button.dataset.currentPath || getParam(paramsForSelected(), path, "."));
        state.directoryBrowser = {
            open: true,
            mode: "directory",
            path,
            current,
            listing: null,
            loading: true,
            error: "",
            newDirectory: "",
        };
        loadDirectoryBrowser(current).catch((error) => showError(error));
    }

    function openFileBrowser(button) {
        let path = [];
        try {
            path = JSON.parse(button.dataset.paramPath || "[]");
        } catch (error) {
            path = [];
        }
        const currentValue = String(button.dataset.currentPath || "").replace(/\\/g, "/");
        const parent = currentValue.includes("/") ? currentValue.split("/").slice(0, -1).join("/") : button.dataset.startPath || ".";
        state.directoryBrowser = {
            open: true,
            mode: "file",
            path,
            current: browserStartPath(parent || "."),
            extensions: button.dataset.extensions || "",
            listing: null,
            loading: true,
            error: "",
        };
        loadDirectoryBrowser(state.directoryBrowser.current).catch((error) => showError(error));
    }

    async function loadCsvMetadata(path) {
        if (!path) {
            return;
        }
        try {
            const payload = await api.getCsvMetadata(path);
            state.csvMetadata[path] = payload;
            render();
        } catch (error) {
            state.csvMetadata[path] = { columns: [], error: error.message || "Unable to read CSV header" };
            render();
        }
    }

    function selectFile(path) {
        const browser = state.directoryBrowser;
        const params = paramsForSelected();
        if (!browser || !params) {
            return;
        }
        setParam(params, browser.path, path);
        state.directoryBrowser = null;
        markDirty();
        if (path.toLowerCase().endsWith(".csv")) {
            loadCsvMetadata(path).catch(() => {});
        }
    }

    async function createDirectoryFromBrowser() {
        const browser = state.directoryBrowser;
        if (!browser) {
            return;
        }
        const rawName = String(getNewDirectoryName() || "").trim();
        const safeName = rawName.replace(/[\\/:*?"<>|]+/g, "_").replace(/^_+|_+$/g, "");
        if (!safeName) {
            browser.error = "Enter a folder name.";
            render();
            return;
        }
        const parent = browser.listing && browser.listing.current ? browser.listing.current : browser.current || ".";
        const path = parent === "." ? safeName : `${parent}/${safeName}`;
        try {
            const payload = await api.createDirectory(path);
            await loadDirectoryBrowser(payload.path || path);
        } catch (error) {
            browser.error = error.message || "Unable to create directory";
            render();
        }
    }

    function selectCurrentDirectory() {
        const browser = state.directoryBrowser;
        const params = paramsForSelected();
        if (!browser || !params) {
            return;
        }
        const selected = browser.listing && browser.listing.current ? browser.listing.current : browser.current || ".";
        setParam(params, browser.path, selected);
        state.directoryBrowser = null;
        setParamsError("");
        markDirty();
    }

    return {
        browserStartPath,
        createDirectoryFromBrowser,
        loadCsvMetadata,
        loadDirectoryBrowser,
        openDirectoryBrowser,
        openFileBrowser,
        selectCurrentDirectory,
        selectFile,
    };
}

