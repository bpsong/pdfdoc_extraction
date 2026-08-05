"""Regression coverage for the separate production GLM-OCR task editor."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "web/static/js/pipeline_config.js"
LLAMA_RENDERER_SHA256 = (
    "ed79faeabc7f874093ebcfcc5233a08c638c4f1b1dbf4ceb52fb6c0a4cedead0"
)


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return start + source.split(start, 1)[1].split(end, 1)[0]


def test_glm_renderer_is_dispatched_before_generic_extraction_renderer() -> None:
    source = _source()
    dispatcher = _between(
        source,
        "    function taskSpecificControls(step) {",
        "    function selectedTaskFindings(step) {",
    )

    assert 'step.class === "GlmOcrExtractTask"' in dispatcher
    assert "return glmOcrExtractControls(step);" in dispatcher
    assert dispatcher.index('step.class === "GlmOcrExtractTask"') < dispatcher.index(
        'kind === "extract"'
    )


def test_glm_renderer_has_an_independent_dom_contract() -> None:
    source = _source()
    renderer = _between(
        source,
        "    function glmOcrExtractControls(step) {",
        "    function extractionFieldNames() {",
    )

    for marker in (
        "data-glm-ocr-controls",
        'textControl("Ollama host"',
        'textControl("Model"',
        'textareaControl("Document instructions"',
        'numberControl("PDF render DPI"',
        'numberControl("Context length"',
        'numberControl("Prediction length"',
        'numberControl("Timeout (seconds)"',
        "extractionFieldControls(step",
        "structuredFieldSchemaDrawer(step)",
        "does not provide confidence scores",
        "every extracted field is sent for operator review",
    ):
        assert marker in renderer

    for llama_only_marker in (
        "API key",
        "configuration_id",
        "Tier",
        "cite_sources",
        "Project ID",
        "Organization ID",
        "confidence_scores",
        "provider-mode",
    ):
        assert llama_only_marker not in renderer


def test_glm_renderer_reuses_scalar_object_and_table_field_primitives() -> None:
    source = _source()
    neutral_fields = _between(
        source,
        "    function extractionFieldControls(step, hint) {",
        "    function structuredFieldSchemaDrawer(step) {",
    )

    for marker in (
        "Field key",
        "Alias",
        "Extraction guidance",
        "Required field",
        'value: "Dict[str, Any]"',
        'value: "List[Any]"',
        "object_fields",
        "item_fields",
        "tableKeys.length >= 1",
    ):
        assert marker in neutral_fields

    storage_copy = _between(
        source,
        '        if (action === "toggle-storage-extraction") {',
        '        if (action === "apply-object-json") {',
    )
    assert 'taskKind(item) === "extract"' in storage_copy
    assert "params.extraction = { fields: clone(sourceFields) };" in storage_copy


def test_glm_defaults_and_summary_are_local_and_non_secret() -> None:
    source = _source()
    renderer = _between(
        source,
        "    function glmOcrExtractControls(step) {",
        "    function extractionFieldNames() {",
    )

    assert (
        'GlmOcrExtractTask: { ollama_host: "http://127.0.0.1:11434", '
        'model: "glm-ocr:latest", document_instructions: "", dpi: 216, '
        "num_ctx: 8192, num_predict: 2048, timeout_seconds: 300, fields: {} }"
    ) in source
    for label in ("Model", "Ollama host", "Fields", "Table status"):
        assert label in renderer
    assert "secretControl(" not in renderer


def test_existing_llamacloud_renderer_and_defaults_are_byte_unchanged() -> None:
    source = _source()
    llama_renderer = _between(
        source,
        "    function extractControls(step) {",
        "    function glmOcrExtractControls(step) {",
    )

    assert hashlib.sha256(llama_renderer.encode()).hexdigest() == LLAMA_RENDERER_SHA256
    assert (
        'ExtractPdfTask: { api_key: "", tier: "agentic", '
        'extraction_target: "per_doc", confidence_scores: true, '
        'poll_interval_seconds: 2, timeout_seconds: 1800, fields: {} }'
    ) in source
    assert source.count('data-param-action="provider-mode"') == 2
    assert "state.providerModes[step.key]" not in _between(
        source,
        "    function glmOcrExtractControls(step) {",
        "    function extractionFieldNames() {",
    )
