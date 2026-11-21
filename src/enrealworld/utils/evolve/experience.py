"""Copy role-owned experience from a stopped team run; never execute its files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROLES = ('engineer', 'researcher', 'manager')
SCRIPT_SUFFIXES = {'.py', '.sh', '.bash', '.js', '.ts', '.mjs', '.cjs'}
EXCLUDED = {'__pycache__', '.git', 'node_modules', '.venv', 'venv', 'tmp', 'cache', '.cache'}
LABELS = dict(engineer='Construct Tools', researcher='Runtime Cases', manager='Manage Memory')


def _files(root, skipped=None, relative_to=None):
    # Extraction skips links without resolving or reading targets; bundle reads stay strict.
    def skip(path):
        if skipped is None:
            raise ValueError('symlinks forbidden: '+str(path))
        skipped.append(dict(path=str(path.relative_to(relative_to)),
                            reason='symlink_not_followed', target=os.readlink(path)))
    if root.is_symlink():
        skip(root)
        return
    if root.is_file():
        yield root
    elif root.is_dir():
        for directory, folders, names in os.walk(root, followlinks=False):
            folders[:] = sorted(name for name in folders if name not in EXCLUDED)
            for name in folders[:] + sorted(names):
                path = Path(directory)/name
                if path.is_symlink():
                    skip(path)
                    if name in folders:
                        folders.remove(name)
                    continue
                if path.is_file():
                    yield path


def read(bundle, role):
    """Verify a role's files and return its provenance and inventory."""
    if role not in ROLES:
        raise ValueError('unknown role: '+role)
    root = Path(bundle).resolve()/role
    if root.is_symlink():
        raise ValueError('symlinks forbidden: '+str(root))
    record = json.loads((root/'manifest.json').read_text())
    actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in _files(root) if p != root/'manifest.json'}
    if record.get('role') != role or record.get('files') != actual:
        raise ValueError('experience inventory mismatch: '+role)
    return record


def extract(run, destination):
    """Preserve evidence, failures and checklist revisions without claiming generality."""
    source = Path(run).resolve(strict=True)
    target = Path(destination).resolve()
    if target.exists() or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('destination must be new and outside the run')
    result = json.loads((source/'result.json').read_text())
    if result.get('status') not in ('passed', 'incomplete', 'failed'):
        raise ValueError('requires a finalized team result')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.experience-', dir=target.parent) as tmp:
        staging = Path(tmp)/'bundle'
        staging.mkdir()
        for role in ROLES:
            root = staging/role
            root.mkdir()
            receipts = [r for r in result.get('receipts', []) if r.get('role') == role]
            output = source/role/'output'
            skipped = []
            def source_files(path):
                return _files(path, skipped=skipped, relative_to=source)
            evidence = {ref.removeprefix('/role/') for receipt in receipts
                        for ref in receipt.get('result', {}).get('evidence', [])
                        if isinstance(ref, str)}
            selected = [p for p in source_files(output)
                        if not any(part in ('__pycache__', '.git', 'node_modules', '.venv', 'tmp', 'cache')
                                   for part in p.relative_to(output).parts)
                        and (p.suffix in SCRIPT_SUFFIXES or p.name == 'result.json'
                             or str(p.relative_to(output)) in evidence
                             or (role == 'manager' and p.suffix in ('.md', '.json')))]
            if role == 'engineer':
                selected += [p for p in source_files(source/role/'delivery') if p.suffix in SCRIPT_SUFFIXES]
            if role == 'manager':
                for name in ('requirement-history', 'requirements.json', 'history.json', 'requirement-receipt.json', 'requirement-handoff.json'):
                    selected += list(source_files(source/'coordination'/name))
            files = {}
            for path in selected:
                relative = str(path.relative_to(source))
                dest = root/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
                files[relative] = hashlib.sha256(dest.read_bytes()).hexdigest()
            record = dict(schema=1, role=role, title=LABELS[role], source_run=str(source),
                          run_status=result['status'], candidate_digest=result.get('digest'),
                          receipts=receipts, files=files, skipped=skipped)
            (root/'README.md').write_text(
                '# '+LABELS[role]+'\n\nHistorical material from '+str(source)+'\n\n'
                'Read manifest.json for outcomes, role receipts and source-relative paths. '
                'Failures and task-specific assumptions are retained. Review relevance and dependencies '
                'before adapting scripts; these files are never automatically executed. '
                'Missing materials were not invented.\n')
            record['files']['README.md'] = hashlib.sha256((root/'README.md').read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
        staging.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('extract')
    command.add_argument('run')
    command.add_argument('destination')
    command = commands.add_parser('read')
    command.add_argument('bundle')
    command.add_argument('--role', choices=ROLES, required=True)
    args = parser.parse_args()
    if args.command == 'extract':
        print(extract(args.run, args.destination))
    else:
        print(json.dumps(read(args.bundle, args.role), indent=2))


if __name__ == '__main__':
    main()
