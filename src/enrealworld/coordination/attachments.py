"""Recipient-scoped attachment snapshots, retained across coordination publications."""
import json
from pathlib import Path
import shutil


def publish_attachments(team, recipient, target, hide_engineer, *, dump, inventory):
    from .scene_graph import private_graph_file
    cache = team.root/'coordination'/'attachment-cache'/recipient
    records = []
    for index, receipt in enumerate(team.receipts):
        sender, result = receipt['role'], receipt['result']
        if sender == recipient:
            continue
        folder = Path(sender)/str(index)
        snapshot = cache/folder
        manifest = snapshot/'index.json'
        if not manifest.exists():
            source = team.root/sender/'output'
            inventory(source)
            paths, errors = {}, []
            messages = [m for m in result.get('messages', []) if m.get('to') == recipient]
            refs = set(result.get('evidence', [])) if recipient == 'manager' else set()
            refs.update(r for m in messages for r in m.get('refs', []))
            for ref in sorted(refs):
                if ref.startswith('/candidate/') or ref == '/candidate-binding.json':
                    continue
                if sender == 'manager':
                    errors.append('Private Manager attachment withheld; provide actionable conditions in the message.')
                    continue
                relative = ref.removeprefix('/role/')
                path = (source/relative).resolve()
                if Path(relative).is_absolute() or not path.is_relative_to(source.resolve()) or not path.is_file():
                    errors.append('missing handoff file or outside role output: '+ref)
                    continue
                if recipient == 'engineer' and private_graph_file(path):
                    errors.append('Private scene record withheld; provide public object/code details in the message.')
                    continue
                dest = snapshot/'files'/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
                exported = target/'attachments'/folder/'files'/relative
                paths[ref] = str(exported) if team.c['runtime'] == 'local' else '/coordination/'+str(exported.relative_to(target))
            dump(manifest, dict(sender=sender, receipt=index, phase=receipt.get('phase'),
                                candidate_digest=result.get('candidate_digest'), paths=paths,
                                errors=sorted(set(errors))))
        if sender == 'engineer' and hide_engineer:
            continue
        record = json.loads(manifest.read_text())
        if record['paths']:
            shutil.copytree(snapshot/'files', target/'attachments'/folder/'files', dirs_exist_ok=True)
        records.append(record)
    dump(target/'attachments.json', records)
    return records
