(function () {
    "use strict";

    const PDFJS_MODULE = "/static/vendor/pdfjs/pdf.min.mjs";
    const PDFJS_WORKER = "/static/vendor/pdfjs/pdf.worker.min.mjs";
    const PDFJS_IMPORT = import(PDFJS_MODULE);

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function asObject(value) {
        return value && typeof value === "object" ? value : {};
    }

    function asArray(value) {
        return Array.isArray(value) ? value : value ? [value] : [];
    }

    function positiveNumber(value) {
        const numeric = Number(value);
        return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
    }

    function pageNumber(value) {
        const numeric = Number(value);
        return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
    }

    function pageDimensions(citation) {
        const dimensions = asObject(citation.page_dimensions || citation.pageDimensions);
        return {
            width: positiveNumber(dimensions.width) || positiveNumber(citation.page_width) || 576,
            height: positiveNumber(dimensions.height) || positiveNumber(citation.page_height) || 792,
        };
    }

    function normalizeBox(box, citation) {
        const value = asObject(box);
        const x = positiveNumber(value.x) ?? positiveNumber(value.x0) ?? 0;
        const y = positiveNumber(value.y) ?? positiveNumber(value.y0) ?? 0;
        const right = positiveNumber(value.x1);
        const bottom = positiveNumber(value.y1);
        const width = positiveNumber(value.w) || positiveNumber(value.width)
            || (right !== null ? right - x : null);
        const height = positiveNumber(value.h) || positiveNumber(value.height)
            || (bottom !== null ? bottom - y : null);
        const page = pageNumber(value.page) || pageNumber(citation.page) || 1;
        if (width === null || height === null || width <= 0 || height <= 0) {
            return null;
        }
        const dimensions = pageDimensions(citation);
        return {
            page,
            x,
            y,
            w: width,
            h: height,
            pageWidth: dimensions.width,
            pageHeight: dimensions.height,
        };
    }

    function collectCitations(value, locations, pages, inheritedPage) {
        if (Array.isArray(value)) {
            value.forEach((item) => collectCitations(item, locations, pages, inheritedPage));
            return;
        }
        if (!value || typeof value !== "object") {
            return;
        }

        const currentPage = pageNumber(value.page) || inheritedPage;
        const dimensions = pageDimensions(value);
        const boxes = value.bounding_boxes || value.boundingBoxes || value.boxes;
        if (Array.isArray(boxes) && boxes.length) {
            boxes.forEach((box) => {
                const citation = { ...value, page: currentPage || 1, page_dimensions: dimensions };
                const normalized = normalizeBox(box, citation);
                if (normalized) {
                    locations.push(normalized);
                    pages.add(normalized.page);
                }
            });
        } else if (currentPage) {
            pages.add(currentPage);
        }

        Object.entries(value).forEach(([key, nested]) => {
            if (["bounding_boxes", "boundingBoxes", "boxes", "page_dimensions", "pageDimensions"].includes(key)) {
                return;
            }
            collectCitations(nested, locations, pages, currentPage);
        });
    }

    function sourceForPath(field, pathParts) {
        const source = asObject(field && field.source);
        if (!Array.isArray(pathParts) || pathParts.length < 2) {
            return source;
        }
        const nestedPath = pathParts.slice(1).join(".");
        const nested = asObject(source.confidence_details)
            && asObject(source.confidence_details.nested_confidences)[nestedPath];
        return nested && nested.source ? asObject(nested.source) : source;
    }

    function normalizeFieldSource(field, pathParts) {
        const source = sourceForPath(field, pathParts);
        const locations = [];
        const pages = new Set();
        collectCitations(source.provider_source, locations, pages, null);
        collectCitations(source.citation || source.citations, locations, pages, null);
        asArray(source.pages).forEach((page) => {
            const normalized = pageNumber(page);
            if (normalized) pages.add(normalized);
        });
        return {
            boxes: locations,
            pages: [...pages].sort((left, right) => left - right),
            locationMode: locations.length ? "bounding_box" : pages.size ? "page_only" : "unavailable",
        };
    }

    function viewerShell(title) {
        return `
            <div class="docflow-pdf-viewer" role="region" aria-label="${escapeHtml(title || "PDF viewer")}">
                <div class="docflow-pdf-toolbar">
                    <div class="docflow-pdf-page-navigation" aria-label="PDF page navigation">
                        <button type="button" class="btn btn-ghost btn-xs btn-square docflow-pdf-page-nav docflow-pdf-prev" aria-label="Previous page" disabled>
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                            </svg>
                        </button>
                        <input type="number" class="docflow-pdf-page-input" min="1" inputmode="numeric" aria-label="Page number" disabled />
                        <span class="docflow-pdf-page-count" aria-hidden="true">of <span class="docflow-pdf-page-total">—</span></span>
                        <button type="button" class="btn btn-ghost btn-xs btn-square docflow-pdf-page-nav docflow-pdf-next" aria-label="Next page" disabled>
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                            </svg>
                        </button>
                    </div>
                    <div class="docflow-pdf-toolbar-group">
                        <button type="button" class="btn btn-outline btn-xs docflow-pdf-zoom-out" aria-label="Zoom out">−</button>
                        <span class="docflow-pdf-zoom-readout" aria-live="polite">—%</span>
                        <button type="button" class="btn btn-outline btn-xs docflow-pdf-zoom-in" aria-label="Zoom in">+</button>
                        <button type="button" class="btn btn-outline btn-xs docflow-pdf-fit-width">Fit width</button>
                    </div>
                </div>
                <div class="docflow-pdf-status" role="status">Loading PDF.js and source document…</div>
                <div class="docflow-pdf-scroll">
                    <div class="docflow-pdf-pages"></div>
                </div>
            </div>
        `;
    }

    function mount(container, options) {
        const settings = options || {};
        if (!container) return null;
        container.innerHTML = viewerShell(settings.title || "PDF viewer");
        const root = container.querySelector(".docflow-pdf-viewer");
        const scroll = container.querySelector(".docflow-pdf-scroll");
        const pagesRoot = container.querySelector(".docflow-pdf-pages");
        const status = container.querySelector(".docflow-pdf-status");
        const pageInput = container.querySelector(".docflow-pdf-page-input");
        const pageTotal = container.querySelector(".docflow-pdf-page-total");
        const zoomReadout = container.querySelector(".docflow-pdf-zoom-readout");
        const previousButton = container.querySelector(".docflow-pdf-prev");
        const nextButton = container.querySelector(".docflow-pdf-next");
        const state = {
            pdf: null,
            pages: [],
            currentPage: 1,
            pendingPage: null,
            pendingCenter: false,
            scale: null,
            fitScale: null,
            selectedLabel: "",
            selectedSource: { boxes: [], pages: [], locationMode: "unavailable" },
            renderToken: 0,
            destroyed: false,
            fitWidthMode: true,
            layoutWidth: 0,
        };

        function setStatus(message) { status.textContent = message; }

        function updateReadout(activePage) {
            const page = Math.max(1, Math.min(state.pdf ? state.pdf.numPages : 1, activePage || 1));
            pageInput.value = state.pdf ? String(page) : "";
            pageInput.disabled = !state.pdf;
            pageTotal.textContent = state.pdf ? String(state.pdf.numPages) : "—";
            zoomReadout.textContent = state.scale ? `${Math.round(state.scale * 100)}%` : "—%";
            previousButton.disabled = !state.pdf || page <= 1;
            nextButton.disabled = !state.pdf || page >= state.pdf.numPages;
        }

        function pageElement(pageNumberValue) {
            return state.pages.find((pageState) => (
                Number(pageState.element.dataset.page) === Number(pageNumberValue)
            )) || null;
        }

        function renderHighlights() {
            state.pages.forEach((pageState) => pageState.highlightLayer.replaceChildren());
            const source = state.selectedSource;
            if (!source || (!source.boxes.length && !source.pages.length)) {
                return;
            }
            source.boxes.forEach((location, index) => {
                const pageState = pageElement(location.page);
                if (!pageState || !pageState.viewport) return;
                const left = location.x * (pageState.viewport.width / location.pageWidth);
                const top = location.y * (pageState.viewport.height / location.pageHeight);
                const width = location.w * (pageState.viewport.width / location.pageWidth);
                const height = location.h * (pageState.viewport.height / location.pageHeight);
                const box = document.createElement("div");
                box.className = "docflow-pdf-bbox";
                box.style.left = `${left}px`;
                box.style.top = `${top}px`;
                box.style.width = `${width}px`;
                box.style.height = `${height}px`;
                box.setAttribute("aria-label", `${state.selectedLabel || "Selected field"} source location`);
                if (index === 0 && state.selectedLabel) {
                    const tag = document.createElement("span");
                    tag.className = "docflow-pdf-bbox-tag";
                    tag.textContent = state.selectedLabel;
                    box.appendChild(tag);
                }
                pageState.highlightLayer.appendChild(box);
            });
        }

        function selectedBounds() {
            const boxes = [...container.querySelectorAll(".docflow-pdf-bbox")];
            if (!boxes.length) return null;
            const page = boxes[0].closest(".docflow-pdf-page");
            const pageRect = page.getBoundingClientRect();
            const rects = boxes.filter((box) => box.closest(".docflow-pdf-page") === page).map((box) => {
                const rect = box.getBoundingClientRect();
                return { left: rect.left - pageRect.left, top: rect.top - pageRect.top, right: rect.right - pageRect.left, bottom: rect.bottom - pageRect.top };
            });
            return {
                page,
                left: Math.min(...rects.map((rect) => rect.left)),
                top: Math.min(...rects.map((rect) => rect.top)),
                right: Math.max(...rects.map((rect) => rect.right)),
                bottom: Math.max(...rects.map((rect) => rect.bottom)),
            };
        }

        function centerSelected({ behavior = "smooth" } = {}) {
            const pageNumberValue = state.selectedSource.boxes[0]?.page || state.selectedSource.pages[0];
            if (!pageNumberValue) return false;
            const targetPage = pageElement(pageNumberValue);
            if (!targetPage) {
                if (state.pdf && state.currentPage !== pageNumberValue) {
                    renderPage(pageNumberValue, { behavior, center: true }).catch((error) => {
                        console.error(error);
                        setStatus("Unable to jump to the selected source location.");
                    });
                    return true;
                }
                return false;
            }
            const bounds = selectedBounds();
            const scrollRect = scroll.getBoundingClientRect();
            const pageRect = targetPage.element.getBoundingClientRect();
            const boundsCenterX = bounds ? (bounds.left + bounds.right) / 2 : pageRect.width / 2;
            const boundsCenterY = bounds ? (bounds.top + bounds.bottom) / 2 : pageRect.height / 2;
            const targetLeft = scroll.scrollLeft + pageRect.left - scrollRect.left + boundsCenterX - scroll.clientWidth / 2;
            const targetTop = scroll.scrollTop + pageRect.top - scrollRect.top + boundsCenterY - scroll.clientHeight / 2;
            scroll.scrollTo({
                left: Math.max(0, Math.min(targetLeft, scroll.scrollWidth - scroll.clientWidth)),
                top: Math.max(0, Math.min(targetTop, scroll.scrollHeight - scroll.clientHeight)),
                behavior,
            });
            window.setTimeout(() => {
                if (!state.destroyed) updateReadout(pageNumberValue);
            }, behavior === "smooth" ? 400 : 0);
            return true;
        }

        async function renderPage(pageNumberValue, { behavior = "auto", center = false } = {}) {
            if (!state.pdf || state.destroyed) return;
            const token = ++state.renderToken;
            const pageNumber = Math.max(1, Math.min(state.pdf.numPages, pageNumberValue || 1));
            state.currentPage = pageNumber;
            const page = await state.pdf.getPage(pageNumber);
            if (token !== state.renderToken || state.destroyed) return;
            const baseViewport = page.getViewport({ scale: 1 });
            const availableWidth = Math.max(scroll.clientWidth - 32, 320);
            state.layoutWidth = scroll.clientWidth;
            if (state.fitWidthMode) {
                state.fitScale = availableWidth / baseViewport.width;
                state.scale = state.fitScale;
            } else {
                if (state.fitScale === null) state.fitScale = availableWidth / baseViewport.width;
                state.scale = state.scale || state.fitScale;
            }
            const viewport = page.getViewport({ scale: state.scale });
            const pageElementNode = document.createElement("div");
            pageElementNode.className = "docflow-pdf-page";
            pageElementNode.dataset.page = String(pageNumber);
            pageElementNode.style.width = `${viewport.width}px`;
            pageElementNode.style.height = `${viewport.height}px`;
            const canvas = document.createElement("canvas");
            const highlightLayer = document.createElement("div");
            highlightLayer.className = "docflow-pdf-highlight-layer";
            pageElementNode.append(canvas, highlightLayer);
            const pixelRatio = window.devicePixelRatio || 1;
            canvas.width = Math.floor(viewport.width * pixelRatio);
            canvas.height = Math.floor(viewport.height * pixelRatio);
            canvas.style.width = `${viewport.width}px`;
            canvas.style.height = `${viewport.height}px`;
            await page.render({ canvasContext: canvas.getContext("2d"), viewport, transform: pixelRatio !== 1 ? [pixelRatio, 0, 0, pixelRatio, 0, 0] : null }).promise;
            if (token !== state.renderToken || state.destroyed) return;
            pagesRoot.replaceChildren(pageElementNode);
            state.pages = [{ element: pageElementNode, highlightLayer, viewport }];
            scroll.scrollTo({ left: 0, top: 0, behavior: "auto" });
            updateReadout(pageNumber);
            renderHighlights();
            if (center) centerSelected({ behavior });
        }

        async function load() {
            if (!settings.url) {
                setStatus("Source PDF unavailable.");
                return;
            }
            try {
                const pdfjsLib = await PDFJS_IMPORT;
                if (state.destroyed) return;
                pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
                state.pdf = await pdfjsLib.getDocument({ url: settings.url }).promise;
                const initialPage = state.pendingPage || 1;
                const shouldCenter = state.pendingCenter;
                state.pendingPage = null;
                state.pendingCenter = false;
                await renderPage(initialPage, { center: shouldCenter });
                setStatus("PDF ready. Select a field to locate its source.");
            } catch (error) {
                console.error(error);
                setStatus("Unable to render the source PDF.");
            }
        }

        function currentPage() {
            return state.currentPage;
        }

        function goToPage(pageNumberValue) {
            if (!state.pdf) return;
            const page = Math.max(1, Math.min(state.pdf.numPages, pageNumberValue || 1));
            if (page === state.currentPage && pageElement(page)) return;
            renderPage(page, { behavior: "smooth" }).catch((error) => {
                console.error(error);
                setStatus("Unable to render the selected PDF page.");
            });
        }

        function submitPageInput() {
            if (!state.pdf) return;
            const requestedPage = Number.parseInt(pageInput.value, 10);
            if (!Number.isInteger(requestedPage)) {
                updateReadout(currentPage());
                return;
            }
            goToPage(requestedPage);
        }

        const onResize = () => {
            state.fitScale = null;
            if (state.fitWidthMode) state.scale = null;
            renderPage(currentPage(), { center: Boolean(state.selectedSource.boxes.length || state.selectedSource.pages.length) }).catch((error) => {
                console.error(error);
                setStatus("Unable to resize the source PDF.");
            });
        };
        previousButton.addEventListener("click", () => goToPage(currentPage() - 1));
        nextButton.addEventListener("click", () => goToPage(currentPage() + 1));
        pageInput.addEventListener("change", submitPageInput);
        pageInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                submitPageInput();
                pageInput.blur();
            }
        });
        container.querySelector(".docflow-pdf-zoom-in").addEventListener("click", () => {
            state.fitWidthMode = false;
            state.scale = Math.min((state.scale || state.fitScale || 1) * 1.15, 3);
            renderPage(currentPage(), { center: Boolean(state.selectedSource.boxes.length || state.selectedSource.pages.length) }).catch((error) => {
                console.error(error);
                setStatus("Unable to zoom the source PDF.");
            });
        });
        container.querySelector(".docflow-pdf-zoom-out").addEventListener("click", () => {
            state.fitWidthMode = false;
            state.scale = Math.max((state.scale || state.fitScale || 1) / 1.15, 0.45);
            renderPage(currentPage(), { center: Boolean(state.selectedSource.boxes.length || state.selectedSource.pages.length) }).catch((error) => {
                console.error(error);
                setStatus("Unable to zoom the source PDF.");
            });
        });
        container.querySelector(".docflow-pdf-fit-width").addEventListener("click", () => {
            state.fitWidthMode = true;
            state.fitScale = null;
            state.scale = null;
            renderPage(currentPage(), { center: Boolean(state.selectedSource.boxes.length || state.selectedSource.pages.length) }).catch((error) => {
                console.error(error);
                setStatus("Unable to fit the source PDF to width.");
            });
        });
        window.addEventListener("resize", onResize);
        let resizeObserver = null;
        if (typeof ResizeObserver !== "undefined") {
            resizeObserver = new ResizeObserver(() => {
                if (state.destroyed || !scroll.clientWidth || scroll.clientWidth === state.layoutWidth) return;
                state.fitScale = null;
                if (state.fitWidthMode) state.scale = null;
                renderPage(currentPage(), { center: Boolean(state.selectedSource.boxes.length || state.selectedSource.pages.length) }).catch((error) => {
                    console.error(error);
                    setStatus("Unable to resize the source PDF.");
                });
            });
            resizeObserver.observe(root);
        }

        const controller = {
            selectField(key, field, pathParts, label) {
                state.selectedLabel = String(label || "");
                state.selectedSource = normalizeFieldSource(field, pathParts || []);
                const firstPage = state.selectedSource.boxes[0]?.page || state.selectedSource.pages[0];
                if (firstPage) updateReadout(firstPage);
                setStatus(state.selectedSource.locationMode === "bounding_box"
                    ? `Showing ${state.selectedLabel || "selected field"} source location.`
                    : state.selectedSource.locationMode === "page_only"
                        ? `${state.selectedLabel || "Selected field"} is located on page ${firstPage}. GLM-OCR returned page-only evidence.`
                        : `${state.selectedLabel || "Selected field"} has no source location available.`);
                renderHighlights();
                if (!firstPage) return;
                state.pendingPage = firstPage;
                state.pendingCenter = true;
                if (!state.pdf) return;
                state.pendingPage = null;
                state.pendingCenter = false;
                if (state.currentPage !== firstPage || !pageElement(firstPage)) {
                    renderPage(firstPage, { behavior: "auto", center: true }).catch((error) => {
                        console.error(error);
                        setStatus("Unable to jump to the selected source location.");
                    });
                    return;
                }
                requestAnimationFrame(() => centerSelected({ behavior: "auto" }));
            },
            centerSelected() {
                const centered = centerSelected({ behavior: "auto" });
                if (centered) {
                    setStatus(state.selectedLabel
                        ? `Centered on ${state.selectedLabel} source location.`
                        : "Centered on selected source location.");
                }
                return centered;
            },
            destroy() {
                state.destroyed = true;
                state.renderToken += 1;
                window.removeEventListener("resize", onResize);
                if (resizeObserver) resizeObserver.disconnect();
                if (state.pdf && state.pdf.destroy) state.pdf.destroy();
                root.remove();
            },
        };
        container._docflowPdfViewer = controller;
        load();
        return controller;
    }

    window.DocFlowPdfViewer = { mount, normalizeFieldSource };
})();
