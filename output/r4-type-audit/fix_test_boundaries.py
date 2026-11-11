"""Apply narrow runtime assertions without reformatting existing test bodies."""
import ast
import json
from pathlib import Path

diagnostics = json.loads(Path('output/r4-type-audit/current-initial.json').read_text(encoding='utf-8-sig'))['generalDiagnostics']
mock_files = {'test/services/test_pipeline_template_branches.py', 'test/services/test_review_schema_version_branches.py',
              'test/services/test_review_service_branches.py', 'test/tools/config_check/test_stored_validator_complete.py'}
present_files = {'test/integration/test_business_validation_acceptance.py', 'test/services/test_review_business_validation.py',
                 'test/services/test_business_validation_schema.py', 'test/visual/test_business_validation_acceptance_visual.py',
                 'test/visual/test_review_validation_visual.py', 'test/services/test_upload_receiver.py',
                 'test/services/test_review_service_branches.py'}
for filename in sorted(mock_files | present_files):
    path = Path(filename)
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    mock_lines = {item['range']['start']['line'] + 1 for item in diagnostics
                  if Path(item['file']).resolve() == path.resolve() and item.get('rule') == 'reportAttributeAccessIssue'}
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    spans = {}
    for node in ast.walk(tree):
        helper = None
        if filename in mock_files and isinstance(node, ast.Attribute) and node.lineno in mock_lines:
            if node.attr in {'return_value', 'side_effect', 'assert_called', 'assert_called_once', 'assert_called_with'}:
                node, helper = node.value, 'require_mock'
        if filename in present_files and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            parent = parents.get(node)
            if (method in {'get_detail', 'find_latest_for_document', 'normalize_schema', 'bounding_box'}
                    and not isinstance(parent, ast.Compare)):
                helper = 'require_present'
            if method == 'get' and isinstance(node.func.value, ast.Call):
                owner = node.func.value.func
                if isinstance(owner, ast.Name) and owner.id in {'ReviewRepository', 'DocumentRepository'}:
                    helper = 'require_present'
            if method == 'get' and filename.endswith('test_upload_receiver.py'):
                if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == 'Path':
                    helper = 'require_present'
        if filename in present_files and isinstance(node, ast.Attribute) and node.attr == 'post_data_json':
            helper = 'require_present'
        if helper:
            start = offsets[node.lineno - 1] + node.col_offset
            stop = offsets[node.end_lineno - 1] + node.end_col_offset
            spans[(start, stop)] = helper
    insertions = []
    for (start, stop), helper in spans.items():
        insertions.extend([(start, helper + '('), (stop, ')')])
    for position, value in sorted(insertions, reverse=True):
        text = text[:position] + value + text[position:]
    helpers = sorted(set(spans.values()))
    if helpers:
        marker = 'import pytest\n'
        assert marker in text
        text = text.replace(marker, marker + '\nfrom test.helpers_assertions import ' + ', '.join(helpers) + '\n', 1)
    if filename.endswith('test_review_service_branches.py'):
        text = text.replace('# pyright: reportOptionalSubscript=false\n', '')
    ast.parse(text)
    path.write_text(text, encoding='utf-8')
    print(filename, len(spans))
