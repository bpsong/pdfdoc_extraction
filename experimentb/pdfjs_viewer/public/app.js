const PDFJS_VERSION = "4.10.38";
const PDFJS_BASE = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

const state = {
    payload: null,
    pdf: null,
    page: null,
    viewport: null,
    fitScale: null,
    scale: null,
    selectedKey: null,
    renderTask: null,
};

const elements = {
    canvas: document.querySelector("#pdf-canvas"),
    documentName: document.querySelector("#document-name"),
    fieldCount: document.querySelector("#field-count"),
    fieldsList: document.querySelector("#fields-list"),
    highlightLayer: document.querySelector("#highlight-layer"),
    pageReadout: document.querySelector("#page-readout"),
    pdfPage: document.querySelector("#pdf-page"),
    pdfScroll: document.querySelector("#pdf-scroll"),
    selectionNote: document.querySelector("#selection-note span:last-child"),
    viewerStatus: document.querySelector("#viewer-status"),
    zoomReadout: document.querySelector("#zoom-readout"),
};

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function humanizeKey(key) {
    return key.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatValue(value) {
    if (value === null || value === undefined || value === "") return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}

function metadataFor(key) {
    return state.payload?.extract_metadata?.field_metadata?.document_metadata?.[key] || {};
}

function locationsFor(key) {
    const metadata = metadataFor(key);
    return (metadata.citation || []).flatMap((citation) => (
        (citation.bounding_boxes || []).map((box) => ({
            ...box,
            page: citation.page || 1,
            pageDimensions: citation.page_dimensions || { width: 576, height: 792 },
        }))
    ));
}

function confidenceFor(key) {
    const confidence = metadataFor(key).confidence;
    return Number.isFinite(confidence) ? `${Math.round(confidence * 100)}% confidence` : "No confidence";
}

function renderFields() {
    const values = state.payload?.data || {};
    const keys = Object.keys(values);
    elements.fieldCount.textContent = `${keys.length} fields`;
    elements.fieldsList.replaceChildren();

    keys.forEach((key) => {
        const template = document.querySelector("#field-template");
        const card = template.content.firstElementChild.cloneNode(true);
        const locations = locationsFor(key);
        const label = card.querySelector(".field-label");
        const input = card.querySelector(".field-input");
        const confidence = card.querySelector(".confidence-badge");
        const locationBadge = card.querySelector(".location-badge");

        card.dataset.fieldKey = key;
        label.htmlFor = `field-${key}`;
        label.textContent = humanizeKey(key);
        input.id = `field-${key}`;
        input.name = key;
        input.value = formatValue(values[key]);
        input.placeholder = values[key] === null ? "Not provided" : "Enter a value";
        if (key === "client_address" || formatValue(values[key]).length > 70) {
            input.rows = 2;
        }
        confidence.textContent = confidenceFor(key);
        locationBadge.textContent = locations.length ? `${locations.length} source ${locations.length === 1 ? "box" : "boxes"}` : "No citation available";
        locationBadge.classList.add(locations.length ? "has-location" : "no-location");
        card.querySelector(".field-key").textContent = key;

        card.addEventListener("click", () => selectField(key));
        input.addEventListener("focus", () => selectField(key));
        input.addEventListener("input", () => {
            state.payload.data[key] = input.value;
        });
        elements.fieldsList.append(card);
    });

    if (keys.length) selectField(keys[0]);
}

function setViewerStatus(message) {
    elements.viewerStatus.textContent = message;
}

function selectField(key) {
    state.selectedKey = key;
    document.querySelectorAll(".field-card").forEach((card) => {
        card.classList.toggle("is-selected", card.dataset.fieldKey === key);
    });
    const locations = locationsFor(key);
    if (locations.length) {
        elements.selectionNote.textContent = `${humanizeKey(key)} · ${locations.length} highlighted ${locations.length === 1 ? "box" : "boxes"}`;
        setViewerStatus(`Showing ${humanizeKey(key)} on page ${locations[0].page}.`);
    } else {
        elements.selectionNote.textContent = `${humanizeKey(key)} has no bounding box in the LlamaCloud response.`;
        setViewerStatus(`${humanizeKey(key)} has no source citation to highlight.`);
    }
    renderHighlights();
    scheduleCenterSelectedCitation();
}

function renderHighlights() {
    elements.highlightLayer.replaceChildren();
    if (!state.viewport || !state.selectedKey) return;

    const locations = locationsFor(state.selectedKey);
    locations.forEach((location, index) => {
        if (location.page !== 1) return;
        const pageWidth = location.pageDimensions.width || 576;
        const pageHeight = location.pageDimensions.height || 792;
        const box = document.createElement("div");
        box.className = "bbox";
        box.dataset.fieldKey = state.selectedKey;
        box.dataset.boxIndex = String(index);
        box.style.left = `${location.x * (state.viewport.width / pageWidth)}px`;
        box.style.top = `${location.y * (state.viewport.height / pageHeight)}px`;
        box.style.width = `${location.w * (state.viewport.width / pageWidth)}px`;
        box.style.height = `${location.h * (state.viewport.height / pageHeight)}px`;
        if (index === 0) {
            const tag = document.createElement("span");
            tag.className = "bbox-tag";
            tag.textContent = humanizeKey(state.selectedKey);
            box.append(tag);
        }
        elements.highlightLayer.append(box);
    });
}

function selectedHighlightBounds() {
    const boxes = [...elements.highlightLayer.querySelectorAll(".bbox")];
    if (!boxes.length) return null;
    const pageRect = elements.pdfPage.getBoundingClientRect();
    const rects = boxes.map((box) => {
        const rect = box.getBoundingClientRect();
        return {
            left: rect.left - pageRect.left,
            top: rect.top - pageRect.top,
            right: rect.right - pageRect.left,
            bottom: rect.bottom - pageRect.top,
        };
    });
    return {
        left: Math.min(...rects.map((rect) => rect.left)),
        top: Math.min(...rects.map((rect) => rect.top)),
        right: Math.max(...rects.map((rect) => rect.right)),
        bottom: Math.max(...rects.map((rect) => rect.bottom)),
    };
}

function centerSelectedCitation({ behavior = "smooth" } = {}) {
    const bounds = selectedHighlightBounds();
    if (!bounds) return;

    const scrollRect = elements.pdfScroll.getBoundingClientRect();
    const pageRect = elements.pdfPage.getBoundingClientRect();
    const citationCenterX = (bounds.left + bounds.right) / 2;
    const citationCenterY = (bounds.top + bounds.bottom) / 2;
    const targetLeft = elements.pdfScroll.scrollLeft
        + pageRect.left - scrollRect.left
        + citationCenterX - elements.pdfScroll.clientWidth / 2;
    const targetTop = elements.pdfScroll.scrollTop
        + pageRect.top - scrollRect.top
        + citationCenterY - elements.pdfScroll.clientHeight / 2;
    const maxLeft = Math.max(0, elements.pdfScroll.scrollWidth - elements.pdfScroll.clientWidth);
    const maxTop = Math.max(0, elements.pdfScroll.scrollHeight - elements.pdfScroll.clientHeight);
    elements.pdfScroll.scrollTo({
        left: Math.min(Math.max(targetLeft, 0), maxLeft),
        top: Math.min(Math.max(targetTop, 0), maxTop),
        behavior,
    });
}

function scheduleCenterSelectedCitation() {
    window.requestAnimationFrame(() => centerSelectedCitation());
}

async function renderPage() {
    if (!state.page) return;
    if (state.renderTask) state.renderTask.cancel();

    const baseViewport = state.page.getViewport({ scale: 1 });
    const availableWidth = Math.max(elements.pdfScroll.clientWidth - 44, 320);
    if (state.fitScale === null) state.fitScale = availableWidth / baseViewport.width;
    const viewport = state.page.getViewport({ scale: state.scale || state.fitScale });
    state.viewport = viewport;
    elements.pdfPage.style.width = `${viewport.width}px`;
    elements.pdfPage.style.height = `${viewport.height}px`;
    elements.canvas.style.width = `${viewport.width}px`;
    elements.canvas.style.height = `${viewport.height}px`;
    const pixelRatio = window.devicePixelRatio || 1;
    elements.canvas.width = Math.floor(viewport.width * pixelRatio);
    elements.canvas.height = Math.floor(viewport.height * pixelRatio);

    state.renderTask = state.page.render({
        canvasContext: elements.canvas.getContext("2d"),
        viewport,
        transform: pixelRatio !== 1 ? [pixelRatio, 0, 0, pixelRatio, 0, 0] : null,
    });
    try {
        await state.renderTask.promise;
        elements.pageReadout.textContent = `Page 1 of ${state.pdf.numPages}`;
        elements.zoomReadout.textContent = `${Math.round((state.scale || state.fitScale) * 100)}%`;
        renderHighlights();
        scheduleCenterSelectedCitation();
    } catch (error) {
        if (error?.name !== "RenderingCancelledException") throw error;
    }
}

async function loadPdf() {
    const pdfjsLib = await import(`${PDFJS_BASE}/pdf.min.mjs`);
    pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_BASE}/pdf.worker.min.mjs`;
    state.pdf = await pdfjsLib.getDocument(state.payload.pdf_url).promise;
    state.page = await state.pdf.getPage(1);
    state.fitScale = null;
    await renderPage();
    setViewerStatus("PDF ready. Focus a field to show its source location.");
}

async function load() {
    try {
        state.payload = await fetch("/api/data", { cache: "no-store" }).then((response) => {
            if (!response.ok) throw new Error(`Data request failed (${response.status})`);
            return response.json();
        });
        elements.documentName.textContent = state.payload.source_filename || "Source PDF";
        renderFields();
        await loadPdf();
    } catch (error) {
        console.error(error);
        setViewerStatus("Unable to load the experiment inputs.");
        elements.fieldsList.innerHTML = `<div class="error-card">${escapeHtml(error.message || "Unknown error")}</div>`;
    }
}

document.querySelector("#zoom-in").addEventListener("click", async () => {
    state.scale = Math.min((state.scale || state.fitScale) * 1.15, 3);
    await renderPage();
});
document.querySelector("#zoom-out").addEventListener("click", async () => {
    state.scale = Math.max((state.scale || state.fitScale) / 1.15, 0.45);
    await renderPage();
});
document.querySelector("#zoom-reset").addEventListener("click", async () => {
    state.scale = state.fitScale;
    await renderPage();
});
document.querySelector("#center-citation").addEventListener("click", () => {
    centerSelectedCitation({ behavior: "smooth" });
});

let resizeTimer;
window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(async () => {
        state.fitScale = null;
        state.scale = null;
        await renderPage();
    }, 120);
});

load();
