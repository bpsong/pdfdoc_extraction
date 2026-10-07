/** Pure page-boundary calculations; the server validates the same contract. */
export function ranges(boundaries, pageCount) {
    const points = [0, ...[...boundaries].sort((a, b) => a - b), pageCount];
    return points.slice(0, -1).map((start, index) => ({start: start + 1, end: points[index + 1]}));
}
