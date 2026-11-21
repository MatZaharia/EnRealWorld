import hashlib
import math
import json
from pathlib import Path
import shutil
import time
import threading
from .agents import CommandAgent, AgentTeamMixin
from .scheduling import execute as execute_schedule

ROLES = ('manager', 'engineer', 'researcher')
REPO = Path(__file__).resolve().parents[3]


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + '\n')


def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('symlinks forbidden in role artifacts')
        if p.is_file():
            result[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def digest(root):
    return hashlib.sha256(json.dumps(inventory(root), sort_keys=True).encode()).hexdigest()


class Team(AgentTeamMixin):
    def __init__(self, config):
        self.cancelled = threading.Event()
        self.c = config
        if 'workflow' in config:
            raise ValueError('workflow was removed; parallel work and meetings are the only workflow')
        for key in ('root', 'public', 'task', 'wall_seconds', 'runtime'):
            if key not in config:
                raise ValueError('required explicit configuration: ' + key)
        if config['runtime'] not in ('local', 'docker') or config['wall_seconds'] <= 0:
            raise ValueError('invalid runtime or budget')
        for key, minimum in (('cpus', 0), ('memory_mib', 3)):
            if key in config and (not isinstance(config[key], (int, float))
                                  or not math.isfinite(config[key])
                                  or config[key] < minimum or config[key] == 0):
                raise ValueError('invalid resource budget: '+key)
        self.agents = {role: CommandAgent(config.get('agents', {}).get(role, config.get('agent', {}))) for role in ROLES}
        if config['runtime'] == 'docker' and not config.get('image'):
            raise ValueError('docker requires an explicit image containing the configured agent adapter')
        self.root = Path(config['root']).resolve()
        public=Path(config['public']).resolve()
        if self.root.is_relative_to(public) or public.is_relative_to(self.root):
            raise ValueError('run root and public input must not overlap')
        inventory(public)
        self.root.mkdir(parents=True, exist_ok=False)
        self.deadline = time.monotonic() + config['wall_seconds']
        self.sessions = {}
        self.receipts = []
        self.version = 0
        self.view = self.root / 'coordination' / 'view'
        self.view.mkdir(parents=True)
        shutil.copytree(config['public'], self.root / 'input')
        inventory(self.root / 'input')
        seed=self.root/'seed-input'
        if config.get('seed_output'):
            inventory(Path(config['seed_output']))
            shutil.copytree(config['seed_output'],seed)
        else: seed.mkdir()
        for role in ROLES:
            dump(self.view/role/'original-seed-binding.json', {'files':inventory(seed)})
        for role in ROLES:
            (self.root / role / 'output').mkdir(parents=True)
            (self.root / role / 'session').mkdir()
            if role == 'engineer':
                (self.root / role / 'delivery').mkdir()
            if role == 'engineer' and config.get('seed_output'):
                inventory(Path(config['seed_output']))
                shutil.copytree(config['seed_output'], self.root / role / 'delivery', dirs_exist_ok=True)
        dump(self.root / 'config.json', config)

    def publish(self):
        # Share role reports and evidence at work barriers and meeting turns.
        from enrealworld.coordination.scene_graph import engineer_view
        from enrealworld.coordination.requirements import public_view, manager_handoff, _read, snapshot
        for recipient in ROLES:
            target = self.view/recipient
            if target.exists(): shutil.rmtree(target)
            dump(target/'original-seed-binding.json', {'files':inventory(self.root/'seed-input')})
            hide_engineer = recipient != 'engineer' and getattr(self, 'schedule', {}).get('stage') in ('work', 'self_test', 'review')

            from enrealworld.coordination.attachments import publish_attachments
            attachment_records = publish_attachments(self, recipient, target, hide_engineer, dump=dump, inventory=inventory)

            def view(value):
                def filter_shared(item):
                    if isinstance(item, list):
                        return [filter_shared(v) for v in item]
                    if not isinstance(item, dict):
                        return item
                    item = dict(item)
                    if hide_engineer and item.get('role') == 'engineer' and 'result' in item:
                        item['result'] = {}
                    if 'latest' in item and hide_engineer:
                        item['latest'] = {k: v for k, v in item['latest'].items() if k != 'engineer'}
                    if 'messages' in item:
                        item['messages'] = [m for m in item['messages'] if m.get('to') == recipient]
                    return {k: filter_shared(v) for k, v in item.items()}
                filtered = filter_shared(value)
                return filtered if recipient == 'manager' else public_view(filtered)
            if hasattr(self, 'schedule'):
                dump(target/'state.json', view(engineer_view(self.schedule) if recipient == 'engineer' else self.schedule))
            for name in ('requirements.json', 'history.json', 'scene-graph.json', 'graph-review.json'):
                if recipient != 'manager' and name in ('requirements.json', 'graph-review.json'):
                    continue
                if recipient == 'engineer' and name == 'scene-graph.json':
                    continue
                source_record = self.root/'coordination'/name
                if source_record.exists():
                    if recipient != 'manager':
                        value = view(json.loads(source_record.read_text()))
                        dump(target/name, engineer_view(value) if recipient == 'engineer' else value)
                    else:
                        dump(target/name, view(json.loads(source_record.read_text())))
            for name, allowed in (('requirement-receipt.json', ('manager',)),
                                  ('requirement-handoff.json', ('engineer',))):
                source_record = self.root/'coordination'/name
                if recipient in allowed and source_record.exists():
                    dump(target/name, json.loads(source_record.read_text()))
            if recipient in ('manager', 'engineer') and (self.root/'coordination/requirement-handoff.json').exists():
                state = _read(self.root)
                handoff = json.loads((self.root/'coordination/requirement-handoff.json').read_text())
                if state and handoff.get('version') == state.get('version'):
                    (target/'requirement-checklist.md').write_bytes(snapshot(self.root, state))
            messages = []
            for sender in ROLES:
                if sender == recipient: continue
                latest = next((r['result'] for r in reversed(self.receipts) if r['role'] == sender), {})
                if sender == 'engineer' and hide_engineer:
                    latest = {}
                directed = [dict(m) for m in latest.get('messages', []) if m.get('to') == recipient]
                attachment = next((r for r in reversed(attachment_records) if r['sender'] == sender), None)
                if attachment:
                    for message in directed:
                        message['attachment_paths'] = {ref: attachment['paths'][ref] for ref in message.get('refs', []) if ref in attachment['paths']}
                        if attachment['errors']:
                            message['attachment_errors'] = list(attachment['errors'])
                paths = attachment['paths'] if attachment else {}
                for message in directed:
                    message['refs'] = [ref for ref in message.get('refs', [])
                                       if ref in paths or ref.startswith('/candidate/')
                                       or ref == '/candidate-binding.json']
                # Keep the existing latest-file paths as aliases of the saved snapshot.
                exported = []
                for ref, saved in paths.items():
                    relative = ref.removeprefix('/role/')
                    source = Path(saved) if self.c['runtime'] == 'local' else target/saved.removeprefix('/coordination/')
                    dest = target/sender/relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, dest)
                    exported.append(relative)
                summary = {key:latest[key] for key in
                           ('status', 'summary', 'candidate_digest', 'issues', 'world_state', 'focus', 'repairs', 'exploration') if key in latest}
                if sender == 'manager':
                    summary = manager_handoff(summary)
                summary.update(evidence=exported, messages=directed)
                dump(target/sender/'result.json', view(summary))
                messages.extend(dict(message, **{'from':sender}) for message in directed)
            dump(target/'messages.json', view(messages))

    def freeze(self, version):
        source=self.root/'engineer'/'delivery'
        if not source.is_dir(): raise ValueError('engineer package missing')
        files = inventory(source)
        target=self.root/'candidates'/f'v{version:03}'
        staging=target.with_name(target.name+'.staging')
        try:
            shutil.copytree(source, staging)
            if inventory(staging) != files or inventory(source) != files:
                raise ValueError('Engineer delivery changed while freezing')
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        identity=digest(target)
        dump(target.parent/f'v{version:03}.json', {'digest':identity,'files':files})
        self.last_frozen={'candidate':str(target),'digest':identity}
        return target,identity

    def current_candidate(self, candidate=None):
        source = self.root/'engineer'/'delivery'
        if candidate is None or digest(source) != digest(candidate):
            self.version += 1
            candidate, _ = self.freeze(self.version)
            self.publish()
        return candidate

    def finalize(self, result):
        """Called after scheduling has stopped every writer, including on failure."""
        snapshots = []
        errors = []
        for path in sorted((self.root/'candidates').glob('v[0-9]*')):
            try:
                binding = json.loads(path.with_suffix('.json').read_text())
                files = inventory(path)
                if files and files == binding['files'] and digest(path) == binding['digest']:
                    snapshots.append(dict(candidate=str(path), digest=binding['digest']))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        latest = None
        try:
            source = self.root/'engineer/delivery'
            if not inventory(source):
                raise ValueError('Engineer delivery contains no files')
            identity = digest(source)
            latest = next((item for item in reversed(snapshots) if item['digest'] == identity), None)
            if latest is None:
                self.version += 1
                path, identity = self.freeze(self.version)
                latest = dict(candidate=str(path), digest=identity)
                snapshots.append(latest)
            selection = 'latest Engineer delivery after writers stopped'
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
            latest = snapshots[-1] if snapshots else None
            selection = 'fallback to latest intact frozen version' if latest else 'no usable Engineer delivery or frozen version'
        verified = None
        manager = result.get('manager') or {}
        acceptance = dict(status=manager.get('status', 'unknown'),
                          candidate_digest=manager.get('candidate_digest'),
                          summary=manager.get('summary', 'No final Manager decision'))
        if result.get('status') == 'passed' and acceptance['status'] == 'passed':
            verified = next((item for item in reversed(snapshots)
                             if item['digest'] == acceptance['candidate_digest']), None)
        result['status'] = ('passed' if verified == latest else 'incomplete') if latest else 'failed'
        result['acceptance'] = acceptance
        result['process_status'] = 'completed' if manager else 'interrupted'
        history_path = self.root/'coordination/history.json'
        if history_path.exists():
            try:
                latest_errors = {}
                for entry in json.loads(history_path.read_text()):
                    if entry['role'] in ROLES:
                        latest_errors[entry['role']] = {k:v for k,v in entry['result'].items() if k.endswith('_error')}
                result['submission_errors'] = {role:errors for role,errors in latest_errors.items() if errors}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append('coordination history unreadable: '+str(exc))
        result.update(candidate=latest['candidate'] if latest else None,
                      digest=latest['digest'] if latest else None,
                      delivery=dict(available=latest is not None, selection=selection,
                                    errors=errors, latest=latest, verified=verified),
                      last_frozen=snapshots[-1] if snapshots else None,
                      sessions=self.sessions, receipts=self.receipts)
        dump(self.root/'result.json', result)
        return result

    def execute(self):
        try:
            result = execute_schedule(self)
        except (Exception, KeyboardInterrupt) as exc:
            result = dict(status='failed', reason=type(exc).__name__+': '+str(exc))
        finally:
            self.cancelled.set()
        return self.finalize(result)


def run(config):
    return Team(config).execute()
