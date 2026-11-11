"""Compare static diagnostics by file/rule/message, independent of shifted lines."""
from collections import Counter
import json
from pathlib import Path

root = Path.cwd()
base = Path('output/r4-type-audit/baseline-path.txt').read_text(encoding='utf-8').strip()
old = json.loads(Path('output/r4-type-audit/head-baseline.json').read_text(encoding='utf-8-sig'))
new_path = Path(__import__('sys').argv[1] if len(__import__('sys').argv) > 1 else 'output/r4-type-audit/current-initial.json')
new = json.loads(new_path.read_text(encoding='utf-8-sig'))

def key(item, parent):
    file = Path(item['file']).relative_to(parent).as_posix()
    message = item['message'].replace(str(parent), '<project>')
    return file, item.get('rule', ''), message

counts = Counter(key(item, Path(base)) for item in old['generalDiagnostics'])
added = []
for item in new['generalDiagnostics']:
    identity = key(item, root)
    if counts[identity]:
        counts[identity] -= 1
    else:
        added.append({'file': identity[0], 'line': item['range']['start']['line'] + 1,
                      'rule': identity[1], 'message': identity[2], 'severity': item['severity']})
Path('output/r4-type-audit/introduced.json').write_text(json.dumps(added, indent=2), encoding='utf-8')
print('HEAD:', old['summary'])
print('Current:', new['summary'])
print('Introduced diagnostics by file:', dict(Counter(item['file'] for item in added)))
for item in added:
    if not item['file'].startswith('test/'):
        print(json.dumps(item))
print('Introduced tests:', sum(item['file'].startswith('test/') for item in added))
