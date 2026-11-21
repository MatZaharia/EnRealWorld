"""Persist Manager's Markdown checklist as immutable, content-addressed snapshots."""
import hashlib
import json
from pathlib import Path

from enrealworld.utils.files import save


def _read(root):
    path = Path(root)/'coordination/requirements.json'
    return json.loads(path.read_text()) if path.exists() else None


def snapshot(root, state):
    folder = (Path(root)/'coordination/requirement-history').resolve()
    path = (Path(root)/'coordination'/state['snapshot']).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        raise ValueError('accepted checklist snapshot is missing or unsafe')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != state['version']:
        raise ValueError('accepted checklist snapshot does not match its version')
    return data


def submit(root, role, result):
    if 'requirement_checklist' not in result:
        return None
    if role != 'manager':
        raise ValueError('only Manager may submit a checklist')
    ref = result['requirement_checklist']
    if not isinstance(ref, str) or not ref.strip() or Path(ref).is_absolute():
        raise ValueError('checklist must be a file path relative to the Manager role directory')
    base = (Path(root)/'manager/output').resolve()
    path = (base/ref).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError('checklist file is missing or outside the Manager role directory: '+ref)
    data = path.read_bytes()
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('checklist file must be readable UTF-8 Markdown') from exc
    version = hashlib.sha256(data).hexdigest()
    folder = Path(root)/'coordination/requirement-history'
    folder.mkdir(parents=True, exist_ok=True)
    saved = folder/(version+'.md')
    created = False
    try:
        with saved.open('xb') as stream:
            created = True
            stream.write(data)
        saved.chmod(0o444)
    except FileExistsError:
        if saved.read_bytes() != data:
            raise ValueError('existing checklist snapshot does not match its version')
    except OSError:
        if created:
            saved.unlink(missing_ok=True)
        raise
    old = _read(root)
    revision = (old['revision'] if old and old.get('version') == version
                else old.get('revision', 0)+1 if old else 1)
    state = dict(version=version, revision=revision, snapshot='requirement-history/'+saved.name)
    save(Path(root)/'coordination/requirements.json', state)
    return dict(status='accepted', revision=revision, version=version)


# Only deliberate task handoffs leave the manager's private context.
def public_view(value):
    if isinstance(value, list):
        return [public_view(item) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get('role') == 'manager' and 'result' in value:
        value = dict(value, result=manager_handoff(value['result']))
    result = {}
    for key, item in value.items():
        if key in {'requirement_checklist', 'requirements_path', 'requirement_error', 'focus'}:
            continue
        if key == 'tasks' and isinstance(item, dict):
            item = {role: task for role, task in item.items() if role != 'manager'}
        if key == 'dispatch' and isinstance(item, list):
            item = [task for task in item if task.get('role') != 'manager']
        if key == 'manager' and isinstance(item, dict):
            item = manager_handoff(item)
        result[key] = public_view(item)
    return result


def manager_handoff(result):
    result = dict(result)
    if 'messages' in result:
        result['messages'] = [dict(message, refs=[ref for ref in message.get('refs', [])
                              if ref.startswith('/candidate/') or ref == '/candidate-binding.json'])
                              for message in result['messages'] if message.get('to') != 'manager']
    return {key: result[key] for key in
            ('status', 'phase', 'candidate_digest', 'messages', 'dispatch', 'issues')
            if key in result}
