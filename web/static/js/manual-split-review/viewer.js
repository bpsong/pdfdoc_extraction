/** Local PDF.js vertical page stack with lazy canvases and boundary controls. */
export async function mountPages(container, url, expectedCount, onError) {
    const pdfjs = await import('/static/vendor/pdfjs/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
    const pdf = await pdfjs.getDocument({url}).promise;
    if (pdf.numPages !== expectedCount) throw new Error('PDF page count changed. Reload or re-ingest the source.');
    let zoom = 1;
    const records = [];
    for (let number = 1; number <= pdf.numPages; number += 1) {
        const article = document.createElement('article');
        article.className = 'manual-page';
        article.dataset.page = String(number);
        article.setAttribute('aria-label', `Page ${number}`);
        const heading = document.createElement('div');
        heading.className = 'manual-page-number';
        heading.textContent = `Page ${number}`;
        const canvas = document.createElement('canvas');
        canvas.setAttribute('aria-label', `PDF page ${number}`);
        article.append(heading, canvas);
        container.append(article);
        records.push({article, canvas, number, task: null, renderedZoom: null});
        if (number < pdf.numPages) {
            const gap = document.createElement('div');
            gap.className = 'manual-boundary';
            gap.id = `split-boundary-${number}`;
            gap.innerHTML = `<label><input type="checkbox" class="checkbox checkbox-primary checkbox-sm" data-boundary="${number}" disabled><span class="manual-marker" hidden></span><span>Split after page ${number}</span></label>`;
            container.append(gap);
        }
    }
    async function render(record) {
        if (record.loading || record.task || record.renderedZoom === zoom) return;
        record.loading = true;
        try {
            const page = await pdf.getPage(record.number);
            const base = page.getViewport({scale: 1});
            const width = Math.min(720, container.clientWidth - 54) * zoom;
            const viewport = page.getViewport({scale: Math.max(width, 200) / base.width});
            const ratio = Math.min(window.devicePixelRatio || 1, 2);
            record.canvas.width = Math.floor(viewport.width * ratio);
            record.canvas.height = Math.floor(viewport.height * ratio);
            record.canvas.style.width = `${viewport.width}px`;
            record.canvas.style.height = `${viewport.height}px`;
            record.article.style.width = `${viewport.width}px`;
            record.article.style.minHeight = `${viewport.height}px`;
            const targetZoom = zoom;
            record.task = page.render({canvasContext: record.canvas.getContext('2d'), viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0]});
            try { await record.task.promise; record.renderedZoom = targetZoom; }
            finally { record.task = null; }
        } finally { record.loading = false; }
    }
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            const record = records[Number(entry.target.dataset.page) - 1];
            if (entry.isIntersecting) render(record).catch(onError);
            else if (!record.loading && record.renderedZoom !== null) {
                record.canvas.width = 1; record.canvas.height = 1;
                record.renderedZoom = null;
            }
        });
    }, {root: container, rootMargin: '700px 0px'});
    records.forEach((record) => observer.observe(record.article));
    await render(records[0]);
    return {
        async setZoom(value) {
            zoom = Math.max(0.55, Math.min(value, 1.8));
            for (const record of records) {
                if (record.task) await record.task.promise;
                record.renderedZoom = null;
            }
            for (const record of records) {
                const rect = record.article.getBoundingClientRect(), parent = container.getBoundingClientRect();
                if (rect.bottom > parent.top - 300 && rect.top < parent.bottom + 300) await render(record);
            }
            return zoom;
        },
        destroy() { observer.disconnect(); pdf.destroy(); },
    };
}
