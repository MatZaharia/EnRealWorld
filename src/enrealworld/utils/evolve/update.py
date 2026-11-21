"""Prepare agent updates and publish a complete, versioned experience library."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .experience import ROLES, LABELS, _files, read


def prepare_update(bundle, destination, previous=None):
    """Give each role its current evidence, previous library and editable output."""
    bundle = Path(bundle).resolve(strict=True)
    previous = Path(previous).resolve(strict=True) if previous else None
    target = Path(destination).resolve()
    sources = [bundle] + ([previous] if previous else [])
    if target.exists() or any(target.is_relative_to(p) or p.is_relative_to(target) for p in sources):
        raise ValueError('update directory must be new and outside input directories')
    for role in ROLES:
        read(bundle, role)
        if previous:
            record = read(previous, role)
            if record.get('kind') != 'experience-library' or not (previous/role/'experience.md').is_file():
                raise ValueError('previous must be a published experience library')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        staging = Path(tmp)/'update'
        for role in ROLES:
            root = staging/role
            shutil.copytree(bundle/role, root/'current')
            if previous:
                shutil.copytree(previous/role, root/'previous')
                shutil.copytree(previous/role, root/'output')
                (root/'output/manifest.json').unlink()
                (root/'output/changes.md').unlink(missing_ok=True)
            else:
                (root/'output').mkdir()
            shutil.copyfile(Path(__file__).with_name('refine_experience.md'), root/'instructions.md')
        staging.rename(target)
    return target


def publish_update(workspace, destination):
    """Publish only complete agent-authored outputs, preserving prior versions."""
    workspace = Path(workspace).resolve(strict=True)
    target = Path(destination).resolve()
    if target.exists() or target.is_relative_to(workspace) or workspace.is_relative_to(target):
        raise ValueError('library directory must be new and outside the update workspace')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        staging = Path(tmp)/'library'
        for role in ROLES:
            root = workspace/role
            # Verify the role-scoped source snapshots before accepting the update.
            current = _verify_snapshot(root/'current', role)
            previous = _verify_snapshot(root/'previous', role) if (root/'previous').exists() else None
            output = root/'output'
            files = list(_files(output))
            for name in ('experience.md', 'changes.md'):
                if not (output/name).is_file() or not (output/name).read_text().strip():
                    raise ValueError(f'{role} must write {name}')
            dest = staging/role
            dest.mkdir(parents=True)
            hashes = {}
            for path in files:
                relative = path.relative_to(output)
                if relative == Path('manifest.json'):
                    continue
                saved = dest/relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, saved)
                hashes[str(relative)] = hashlib.sha256(saved.read_bytes()).hexdigest()
            record = dict(schema=1, kind='experience-library', role=role, title=LABELS[role],
                          revision=(previous.get('revision', 0) if previous else 0)+1,
                          source_run=current.get('source_run'), files=hashes,
                          current_manifest_sha256=hashlib.sha256((root/'current/manifest.json').read_bytes()).hexdigest(),
                          previous_manifest_sha256=hashlib.sha256((root/'previous/manifest.json').read_bytes()).hexdigest() if previous else None)
            (dest/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
        staging.rename(target)
    return target


def _verify_snapshot(path, role):
    record = json.loads((path/'manifest.json').read_text())
    actual = {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in _files(path) if p != path/'manifest.json'}
    if record.get('role') != role or record.get('files') != actual:
        raise ValueError('source snapshot mismatch: '+str(path))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('bundle')
    prepare.add_argument('destination')
    prepare.add_argument('--previous')
    publish = commands.add_parser('publish')
    publish.add_argument('workspace')
    publish.add_argument('destination')
    args = parser.parse_args()
    if args.command == 'prepare':
        print(prepare_update(args.bundle, args.destination, args.previous))
    else:
        print(publish_update(args.workspace, args.destination))


if __name__ == '__main__':
    main()
