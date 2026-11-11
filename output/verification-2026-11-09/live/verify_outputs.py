"""Check local walkthrough outputs without printing document values."""

from pathlib import Path
import hashlib
import json
import sqlite3

from pypdf import PdfReader
import yaml

ROOT = Path(__file__).resolve().parents[3]
source = ROOT / 'sample stock invoices from internet/invoice_Aaron Bergman_36258.pdf'
source_text = PdfReader(source).pages[0].extract_text()
assert all(value in source_text for value in ('36258', '50.10', '48.71'))
config = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
database = (ROOT / config['database']['path']).resolve()
document_ids = [
    '5cb6a14d-5edf-4dd8-a074-fe4affc38daf',
    'a6b21b8c-566d-4509-82ab-43f7e7eae767',
]
results = []
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    for index, document_id in enumerate(document_ids):
        document = conn.execute('SELECT status FROM documents WHERE id = ?', (document_id,)).fetchone()
        assert document is not None and document['status'] == 'completed'
        files = conn.execute('SELECT file_type, file_path FROM document_files WHERE document_id = ?', (document_id,)).fetchall()
        exported = [Path(row['file_path']) for row in files if row['file_type'] == 'export_json']
        originals = [Path(row['file_path']) for row in files if row['file_type'] == 'source_original']
        assert len(exported) == 1 and len(originals) == 1
        assert hashlib.sha256(originals[0].read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest()
        payload = json.loads(exported[0].read_text(encoding='utf-8'))
        fields = conn.execute('SELECT field_key, final_value_json FROM extracted_fields WHERE document_id = ?', (document_id,)).fetchall()
        final = {row['field_key']: json.loads(row['final_value_json']) for row in fields}
        assert payload == final
        assert payload['invoice_number'] == '36258' and payload['invoice_total'] == 50.1
        assert len(payload['line_items']) == 1
        line = payload['line_items'][0]
        assert line['line_total'] == line['unit_price'] == 48.71 and line['quantity'] == 1
        correct_name = exported[0].name == f'{document_id}.json'
        assert correct_name if index == 1 else exported[0].name == 'unknown_8.json'
        results.append({'document_id': document_id, 'status': 'completed', 'filename': exported[0].name,
                        'filename_correct': correct_name, 'values_match_accepted_fields': True,
                        'source_hash_matches': True, 'printed_amounts_match': True})
summary = {'before_fix_and_after_fix': results, 'both_documents_preserved': True}
(Path(__file__).parent / 'output-verification.local.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('Verified two completed documents, accepted JSON values, source PDF hashes, and corrected filename.')
