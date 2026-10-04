"""Execute the task renderer to verify local controls and safe field editing."""

from test.visual.test_pipeline_controller_modules import _run_module


def test_liteparse_renderer_uses_local_options_and_escapes_instructions() -> None:
    html = _run_module("task-editors.js", """
        const escapeHtml = value => String(value).replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
        const editors = module.createPipelineTaskEditors({
            state: {}, escapeHtml, pathAttr: path => path.join('.'),
            taskKind: () => 'extract', stepsOf: () => [],
            getParam: () => null, selectedTaskFindings: () => [],
        });
        return editors.taskSpecificControls({
            class: 'LiteParseExtractTask', key: 'local',
            params: {document_instructions: '<script>unsafe</script>', fields: {
                reference: {alias: 'Reference', type: 'str'},
                entries: {alias: 'Entries', type: 'List[Any]', is_table: true,
                    item_fields: {quantity: {alias: 'Quantity', type: 'float'}}},
            }},
        });
    """)
    assert 'data-liteparse-controls' in html
    assert 'qwen3.5:9b-q4_K_M' in html
    assert 'HTTP loopback only' in html
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in html
    assert '<script>unsafe</script>' not in html
    assert 'API key' not in html and 'LlamaCloud configuration ID' not in html
    assert 'Selected pages' in html and 'OCR language' in html
    assert 'entries' in html and 'reference' in html
