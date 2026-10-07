const PAGE_COUNT = 18;
const boundaries = new Set();
const pageList = document.querySelector('#pageList');
const documentList = document.querySelector('#documentList');
const toast = document.querySelector('#toast');
let toastTimer;

function pageMarkup(page) {
  const invoice = page === 1;
  const body = invoice
    ? `<div class="page-header"><strong>NORTHSTAR OFFICE SUPPLY</strong><span>INVOICE · 2026</span></div><div class="paper-company">Northstar Office Supply</div><h3 class="paper-title">Invoice #NS-20481</h3><div class="paper-meta">BILL TO: ACME INDUSTRIES<br>Invoice date: September 28, 2026 &nbsp; · &nbsp; Due: October 28, 2026<br>Purchase order: PO-88421</div><div class="paper-grid"><span>Description</span><span>Qty</span><span>Amount</span><span>Printer paper, A4</span><span>24</span><span>$144.00</span><span>Shipping &amp; handling</span><span>1</span><span>$18.50</span><span>Tax</span><span>—</span><span>$13.00</span></div><div class="paper-total">TOTAL DUE &nbsp; $175.50</div><div class="paper-foot"><span>Thank you for your business</span><span>Page 1 of 2</span></div>`
    : `<div class="page-header"><strong>${page < 3 ? 'NORTHSTAR OFFICE SUPPLY' : 'ACME INDUSTRIES'}</strong><span>${page < 3 ? 'INVOICE · 2026' : 'DOCUMENT PAGE'}</span></div><div class="paper-section">${page === 2 ? 'Payment details & remittance advice' : page === 3 ? 'Packing slip · Shipment 88421' : page % 3 === 0 ? 'Supporting document' : 'Transaction details'}</div><div class="paper-meta">Reference: NS-20481 &nbsp; · &nbsp; Date: September 28, 2026<br>Customer: Acme Industries</div><div class="paper-lines" style="margin-top:28px"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><div class="paper-foot"><span>Confidential business document</span><span>Page ${page} of ${PAGE_COUNT}</span></div>`;
  return `<article class="pdf-page" data-page="${page}" aria-label="Page ${page}">${body}<span class="page-label">PAGE ${page}</span></article>`;
}

function renderPages() {
  let html = '';
  for (let page = 1; page <= PAGE_COUNT; page += 1) {
    html += pageMarkup(page);
    if (page < PAGE_COUNT) {
      const isSelected = boundaries.has(page);
      const boundaryNumber = [...boundaries].sort((a, b) => a - b).indexOf(page) + 1;
      html += `<div class="page-separator${isSelected ? ' selected' : ''}" data-boundary="${page}"><label class="split-check"><input type="checkbox" data-split="${page}" ${isSelected ? 'checked' : ''} aria-label="Split after page ${page}"><span class="split-number">${boundaryNumber}</span><span>Split after page ${page}</span></label></div>`;
    }
  }
  pageList.innerHTML = html;
}

function rangesFromBoundaries() {
  const points = [0, ...[...boundaries].sort((a, b) => a - b), PAGE_COUNT];
  return points.slice(0, -1).map((start, index) => ({ start: start + 1, end: points[index + 1] }));
}

function renderPlan() {
  const ranges = rangesFromBoundaries();
  document.querySelector('#docCount').textContent = `${ranges.length} ${ranges.length === 1 ? 'document' : 'documents'} · ${boundaries.size} ${boundaries.size === 1 ? 'boundary' : 'boundaries'}`;
  document.querySelector('#boundaryCount').textContent = String(boundaries.size);
  document.querySelector('#progressBar').style.width = `${Math.min(boundaries.size * 14, 100)}%`;
  document.querySelector('#planHint').textContent = boundaries.size ? 'Purple markers match the selected checkboxes.' : 'Your source file will remain unchanged.';
  let html = '';
  ranges.forEach((range, index) => {
    const nextBoundary = range.end < PAGE_COUNT ? range.end : null;
    const marker = nextBoundary === null ? '' : `<div class="boundary-row active"><span class="boundary-dot">${index + 1}</span><span>Split after page ${nextBoundary}</span></div>`;
    html += `<div class="doc-row${index === 0 && boundaries.size === 0 ? ' active-doc' : ''}" data-range="${range.start}-${range.end}"><div class="doc-title"><span class="doc-number">▤</span> Document ${index + 1}${index === 0 && boundaries.size === 0 ? '<span class="doc-badge">Single file</span>' : ''}</div><p class="doc-range">Pages ${range.start}–${range.end}</p></div>${marker}`;
  });
  documentList.innerHTML = html;
  renderPages();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
}

function showScreen(screen) {
  const isSplit = screen === 'split';
  document.querySelector('#queueScreen').classList.toggle('hidden', isSplit);
  document.querySelector('#splitScreen').classList.toggle('hidden', !isSplit);
  document.querySelector('#breadcrumb').innerHTML = isSplit ? 'Review Queue <span>/</span> Manual split' : 'Review Queue';
  document.querySelector('#pageTitle').textContent = isSplit ? 'Split document' : 'Review Queue';
  document.querySelector('#pageSubtitle').textContent = isSplit ? 'Set the page boundaries for this document.' : 'Work documents that require human review.';
  ['#backButton', '#savedState', '#saveButton', '#confirmButton'].forEach((selector) => document.querySelector(selector).classList.toggle('hidden', !isSplit));
  document.querySelector('#refreshButton').classList.toggle('hidden', isSplit);
  if (!isSplit) history.replaceState(null, '', location.pathname + location.search);
  else history.replaceState(null, '', '#split');
  window.scrollTo(0, 0);
}

document.querySelectorAll('.open-split,.doc-link').forEach((element) => element.addEventListener('click', (event) => {
  event.preventDefault();
  showScreen('split');
}));
document.querySelector('#backButton').addEventListener('click', () => showScreen('queue'));
document.querySelector('#refreshButton').addEventListener('click', () => showToast('Review queue refreshed.'));
window.addEventListener('hashchange', () => showScreen(location.hash === '#split' ? 'split' : 'queue'));

pageList.addEventListener('change', (event) => {
  const input = event.target.closest('[data-split]');
  if (!input) return;
  const page = Number(input.dataset.split);
  input.checked ? boundaries.add(page) : boundaries.delete(page);
  renderPlan();
  const target = pageList.querySelector(`[data-boundary="${page}"]`);
  target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
});

pageList.addEventListener('scroll', () => {
  const pages = [...pageList.querySelectorAll('.pdf-page')];
  const closest = pages.find((page) => page.getBoundingClientRect().bottom > 110) || pages.at(-1);
  if (closest) document.querySelector('#currentPage').textContent = closest.dataset.page;
});

document.querySelectorAll('#confirmButton,#confirmButtonSide').forEach((button) => button.addEventListener('click', () => {
  if (!boundaries.size) return showToast('Select at least one page boundary to split this PDF.');
  showToast(`Split plan confirmed: ${boundaries.size + 1} documents created.`);
}));
document.querySelector('#saveButton').addEventListener('click', () => showToast('Draft saved on this server.'));
document.querySelector('#cancelButton').addEventListener('click', () => {
  boundaries.clear();
  renderPlan();
  showToast('Split selections cleared.');
});

renderPlan();
showScreen(location.hash === '#split' ? 'split' : 'queue');
