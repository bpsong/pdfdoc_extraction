/** HTTP boundary for one human-review item. */

export function createHumanReviewApi(docFlow, reviewItemId) {
    const itemUrl = `/api/review/items/${encodeURIComponent(reviewItemId)}`;
    return {
        load: () => docFlow.apiGet(itemUrl),
        claim: () => docFlow.apiPost(`${itemUrl}/claim`, {}),
        release: () => docFlow.apiPost(`${itemUrl}/release`, {}),
        saveDraft: (corrections) => docFlow.apiPost(`${itemUrl}/draft`, { corrections }),
        previewDiff: (corrections) => docFlow.apiPost(`${itemUrl}/diff`, { corrections }),
        complete: (corrections) => docFlow.apiPost(`${itemUrl}/complete`, { corrections }),
    };
}
