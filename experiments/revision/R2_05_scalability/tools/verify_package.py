"""Check every packaged file against PACKAGE_MANIFEST.json (standard library only)."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    'worker.py', 'verify_sources.py', 'PACKAGE_MANIFEST.json', 'run.py',
    'original_runtime.py', 'run_baseline.py', 'README.md',
    'requirements.txt', 'requirements-tested.txt',
    'configs/baseline.json', 'configs/formal.json', 'configs/smoke.json',
    'configs/traffic_couplings.json', 'provenance/original_sources.json',
    'provenance/integration_fingerprint.json', 'validation/baseline_gate.json',
    'integration/path_planner_lifelong.py',
)


def main():
    errors = []
    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            errors.append('Missing required file: ' + name)
    for name in ('vendor', 'configs'):
        if not (ROOT / name).is_dir() or not any((ROOT / name).rglob('*')):
            errors.append('Missing or empty required directory: ' + name)
    manifest_path = ROOT / 'PACKAGE_MANIFEST.json'
    if not manifest_path.is_file():
        print('\n'.join(errors))
        return 1
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    listed = set()
    for row in manifest['files']:
        name = row['path']
        path = ROOT / name
        if name in listed or not path.resolve().is_relative_to(ROOT):
            errors.append('Invalid or duplicated manifest path: ' + name)
            continue
        listed.add(name)
        if not path.is_file() or path.is_symlink():
            errors.append('Missing or linked file: ' + name)
            continue
        data = path.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            errors.append('Size or SHA-256 mismatch: ' + name)
    for name in REQUIRED_FILES:
        if name != 'PACKAGE_MANIFEST.json' and name not in listed:
            errors.append('Required file absent from manifest: ' + name)
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'PASS: {len(listed)} packaged files match size and SHA-256; required files/directories present.')
    print('PACKAGE_MANIFEST.json intentionally excludes its own hash. Runtime outputs are not package inputs.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
