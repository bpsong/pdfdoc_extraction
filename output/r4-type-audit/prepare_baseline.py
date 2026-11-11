"""Prepare an isolated tracked-HEAD source snapshot without runtime data."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

workspace = Path.cwd()
baseline = Path(tempfile.mkdtemp(prefix='r4-types-head-'))
archive = subprocess.run(['git', 'archive', '--format=tar', 'HEAD'], check=True, capture_output=True).stdout
with tarfile.open(fileobj=io.BytesIO(archive)) as source:
    for member in source:
        if not member.isfile() or not (member.name.endswith(('.py', '.pyi')) or member.name.endswith(('pyrightconfig.json', 'py.typed'))):
            continue
        destination = (baseline / member.name).resolve()
        assert destination.is_relative_to(baseline.resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source.extractfile(member)
        assert content is not None
        destination.write_bytes(content.read())
config = json.loads((baseline / 'pyrightconfig.json').read_text(encoding='utf-8'))
config['venvPath'] = str(workspace)
(baseline / 'pyrightconfig.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
(workspace / 'output/r4-type-audit/baseline-path.txt').write_text(str(baseline), encoding='utf-8')
print(str(baseline))
