/** Browser-independent upload validation and formatting. */
export function createModel(limits) {
    const { maxUploadMb, maxUploadBytes, maxUploadFiles, maxUploadRequestMb, maxUploadRequestBytes } = limits;
    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatBytes(bytes) {
        if (!bytes) {
            return "0 B";
        }
        const units = ["B", "KB", "MB", "GB"];
        const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        const value = bytes / Math.pow(1024, index);
        return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function validateFile(file) {
        const name = file.name || "";
        if (!name.toLowerCase().endsWith(".pdf")) {
            return "Only PDF files are accepted";
        }
        if (file.type && file.type !== "application/pdf" && file.type !== "application/x-pdf") {
            return "Browser reported a non-PDF file type";
        }
        if (file.size > maxUploadBytes) {
            return `File exceeds ${maxUploadMb} MB`;
        }
        return "";
    }

    function fileKey(file) {
        return `${file.name}:${file.size}:${file.lastModified}`;
    }

    function validateBatch(entries) {
        if (entries.length > maxUploadFiles) {
            return `A batch can contain at most ${maxUploadFiles} files`;
        }
        const fileBytes = entries.reduce((total, entry) => total + entry.file.size, 0);
        const estimatedMultipartOverhead = 8192 + (entries.length * 1024);
        if (fileBytes + estimatedMultipartOverhead > maxUploadRequestBytes) {
            return `Batch exceeds the ${maxUploadRequestMb} MB request limit`;
        }
        return "";
    }
    return { escapeHtml, formatBytes, validateFile, fileKey, validateBatch };
}
