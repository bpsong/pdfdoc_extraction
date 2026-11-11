/** HTTP boundary for one human-review item. */

export function createHumanReviewApi(docFlow, reviewItemId, getRevision = () => null) {
    const itemUrl = `/api/review/items/${encodeURIComponent(reviewItemId)}`;
    const revision = () => getRevision() ? {expected_revision: getRevision()} : {};
    return {
        load: () => docFlow.apiGet(itemUrl),
        claim: () => docFlow.apiPost(`${itemUrl}/claim`, {}),
        release: () => docFlow.apiPost(`${itemUrl}/release`, {}),
        saveDraft: (corrections) => docFlow.apiPost(`${itemUrl}/draft`, { corrections, ...revision() }),
        previewDiff: (corrections) => docFlow.apiPost(`${itemUrl}/diff`, { corrections }),
        complete: (corrections) => docFlow.apiPost(`${itemUrl}/complete`, { corrections, ...revision() }),
        revalidate: (corrections, requestRevision) => docFlow.apiPost(`${itemUrl}/revalidate`, {
            corrections, ...revision(), request_revision: requestRevision,
        }),
    };
}
