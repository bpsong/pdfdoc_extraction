/** Visibility-aware, non-overlapping polling for feature controllers. */
export function createPollingController({
    task,
    intervalMs,
    windowRef = window,
    documentRef = document,
}) {
    let timer = null;
    let active = false;
    let running = false;
    let stopped = false;

    function clearTimer() {
        if (timer !== null) {
            windowRef.clearInterval(timer);
            timer = null;
        }
    }

    async function runNow() {
        if (stopped || running || documentRef.hidden) {
            return false;
        }
        running = true;
        try {
            await task();
            return true;
        } finally {
            running = false;
        }
    }

    function schedule() {
        clearTimer();
        if (active && !stopped && !documentRef.hidden) {
            timer = windowRef.setInterval(runNow, intervalMs);
        }
    }

    function setActive(value) {
        active = Boolean(value);
        schedule();
    }

    function handleVisibilityChange() {
        if (documentRef.hidden) {
            clearTimer();
            return;
        }
        schedule();
        if (active) {
            void runNow();
        }
    }

    function stop() {
        stopped = true;
        active = false;
        clearTimer();
        documentRef.removeEventListener("visibilitychange", handleVisibilityChange);
    }

    documentRef.addEventListener("visibilitychange", handleVisibilityChange);
    return { runNow, setActive, stop };
}
