import {ranges} from './model.js?v=manual-split-3';
import {mountPages} from './viewer.js?v=manual-split-3';

const root = document.getElementById('manual-split-workspace');
const api = window.DocFlow;
const reviewId = root.dataset.reviewId;
const itemUrl = `/api/review/items/${encodeURIComponent(reviewId)}`;
const el = (id) => document.getElementById(id);
let detail, viewer, ready = false, busy = false, dirty = false, stale = false, zoom = 1;
let boundaries = new Set(), lastBoundary = null;

function owned() { return detail?.lock?.locked_by === root.dataset.operator && Date.parse(detail.lock.expires_at) > Date.now(); }
function editable() { return ready && !busy && !stale && owned() && detail?.review_item?.status !== 'completed'; }
function controls() {
    const completed = detail?.review_item?.status === 'completed';
    el('split-claim').disabled = busy || completed;
    el('split-claim').textContent = owned() ? 'Renew claim' : 'Claim';
    el('split-release').disabled = !owned() || busy || completed;
    el('split-save').disabled = !editable();
    el('split-retry').hidden = !completed || !detail.manual_split.can_retry;
    el('split-retry').disabled = busy;
    el('split-complete').disabled = !editable();
    el('split-complete').textContent = completed ? 'Decision saved' : busy ? 'Saving…' : boundaries.size ? 'Confirm split' : 'Continue without splitting';
    root.querySelectorAll('[data-boundary]').forEach((checkbox) => {checkbox.disabled = !editable();});
}
function status(message, error = false) {
    el('split-status').textContent = message;
    el('split-status').classList.toggle('text-error', error);
}
function plan() {
    const sorted = [...boundaries].sort((a, b) => a - b);
    const segments = ranges(sorted, detail.manual_split.page_count);
    el('split-plan-summary').textContent = `${segments.length} ${segments.length === 1 ? 'document' : 'documents'} · ${sorted.length} boundaries selected`;
    el('split-plan').innerHTML = segments.map((segment, index) => `<div class="manual-plan-document"><strong>Document ${index + 1}</strong><span>Pages ${segment.start}–${segment.end}</span></div>${index < sorted.length ? `<button type="button" class="manual-plan-boundary ${sorted[index] === lastBoundary ? 'recent' : ''}" data-jump="${sorted[index]}"><b class="manual-marker">${index + 1}</b>Split after page ${sorted[index]}</button>` : ''}`).join('');
    root.querySelectorAll('[data-boundary]').forEach((checkbox) => {
        const page = Number(checkbox.dataset.boundary), selected = boundaries.has(page);
        checkbox.checked = selected;
        const gap = checkbox.closest('.manual-boundary'), marker = gap.querySelector('.manual-marker');
        gap.classList.toggle('selected', selected);
        marker.hidden = !selected;
        marker.textContent = selected ? String(sorted.indexOf(page) + 1) : '';
    });
    controls();
}
async function load() {
    detail = await api.apiGet(itemUrl);
    boundaries = new Set(detail.manual_split.boundaries);
    el('split-filename').textContent = detail.document.filename;
    el('split-subtitle').textContent = `${detail.manual_split.page_count} pages · Manual split`;
    el('split-progress').hidden = detail.review_item.status !== 'completed';
    el('split-progress').href = `/app/batches/${encodeURIComponent(detail.review_item.batch_id)}`;
    if (detail.review_item.status === 'completed' && detail.document.status === 'failed' && detail.manual_split.phase !== 'applied') {
        status('Decision saved, but processing could not continue. Use Retry continuation if available, or ask an administrator to inspect the failure.', true);
    } else if (detail.review_item.status === 'completed') status(detail.manual_split.phase === 'applied'
        ? 'Decision saved and applied. Follow the remaining workflow using View processing. You can leave this page.'
        : 'Decision saved. Processing will continue in the background. You can leave this page and use View processing.');
    else status(owned() ? 'Claimed by you. Select boundaries or continue without splitting.' : detail.lock && Date.parse(detail.lock.expires_at) > Date.now() ? `Claimed by ${detail.lock.locked_by}. View only.` : 'Claim this document to edit the split plan.');
    dirty = false;
    stale = false;
    plan();
}
async function action(operation) {
    if (busy) return;
    busy = true; controls();
    try { await operation(); }
    catch (error) { status(error.message || 'Unable to save the decision. Reload and try again.', true); }
    finally { busy = false; controls(); }
}
el('split-pages').addEventListener('change', (event) => {
    const checkbox = event.target.closest('[data-boundary]');
    if (!checkbox || !editable()) return;
    const page = Number(checkbox.dataset.boundary);
    checkbox.checked ? boundaries.add(page) : boundaries.delete(page);
    lastBoundary = checkbox.checked ? page : null;
    dirty = true;
    plan(); status('Unsaved boundary changes.');
});
el('split-plan').addEventListener('click', (event) => {
    const button = event.target.closest('[data-jump]');
    if (!button) return;
    lastBoundary = Number(button.dataset.jump); plan();
    const gap = el(`split-boundary-${lastBoundary}`), pages = el('split-pages');
    pages.scrollBy({top: gap.getBoundingClientRect().top - pages.getBoundingClientRect().top - pages.clientHeight / 2 + gap.offsetHeight / 2, behavior: 'smooth'});
});
el('split-claim').addEventListener('click', () => action(async () => {
    await api.apiPost(`${itemUrl}/claim`, {});
    if (dirty) {
        const revision = detail.manual_split.revision;
        detail = await api.apiGet(itemUrl);
        stale = stale || detail.manual_split.revision !== revision;
        status(stale
            ? 'The saved draft changed in another session. Reload before saving or completing. Your unsaved selections are still shown.'
            : 'Claim renewed. Your unsaved changes are preserved.', stale);
    } else await load();
}));
el('split-retry').addEventListener('click', () => action(async () => {const result = await api.apiPost(`${itemUrl}/split/retry`, {}); await load(); if (result.message) status(result.message);}));
el('split-release').addEventListener('click', () => action(async () => { await api.apiPost(`${itemUrl}/release`, {}); await load(); }));
el('split-save').addEventListener('click', () => action(async () => {
    await api.apiPost(`${itemUrl}/split/draft`, {boundaries: [...boundaries].sort((a,b)=>a-b), expected_revision: detail.manual_split.revision});
    await load(); status('Draft saved. Processing remains paused.');
}));
el('split-complete').addEventListener('click', () => action(async () => {
    status('Saving your decision…');
    const result = await api.apiPost(`${itemUrl}/split/complete`, {action: boundaries.size ? 'split' : 'skip', boundaries: [...boundaries].sort((a,b)=>a-b), expected_revision: detail.manual_split.revision});
    // Approval is final even if the following status refresh fails.
    dirty = false;
    detail.review_item.status = 'completed';
    detail.manual_split = result.manual_split;
    controls();
    await load();
}));
function pdfError(error) { ready = false; el('split-pdf-status').textContent = 'Unable to render the PDF. Reload before confirming.'; status(error.message || 'PDF preview unavailable.', true); controls(); }
async function setZoom(value) { if (viewer) {zoom = await viewer.setZoom(value); el('split-zoom').textContent = `${Math.round(zoom * 100)}%`;} }
el('split-zoom-in').addEventListener('click', () => setZoom(zoom + 0.15).catch(pdfError));
el('split-zoom-out').addEventListener('click', () => setZoom(zoom - 0.15).catch(pdfError));
el('split-fit').addEventListener('click', () => setZoom(1).catch(pdfError));
window.addEventListener('beforeunload', (event) => {if (dirty) {event.preventDefault(); event.returnValue = '';}});
setInterval(controls, 15000);
setInterval(async () => {
    if (busy || detail?.review_item?.status !== 'completed' || detail.manual_split.phase === 'applied') return;
    try { await load(); }
    catch { status('Decision saved. Status refresh is unavailable; use View processing to check progress.', true); }
}, 3000);
try {
    await load();
    viewer = await mountPages(el('split-pages'), detail.document.preview_url, detail.manual_split.page_count, pdfError);
    ready = true;
    el('split-pdf-status').textContent = 'All pages in source order. Check a box between pages to split.';
    plan();
} catch (error) {pdfError(error);}
