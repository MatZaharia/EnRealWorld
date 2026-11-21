"""Native Antigravity CLI adapter with JSON stdin/stdout and explicit role sessions.

Install ``agy`` and sign in once with an interactive ``agy`` session before
running the team; headless runs reuse the cached credentials. Check model IDs
with ``agy models``. Example for a local run::

    "agent": {
      "command": ["/path/to/.venv/bin/python", "-m", "enrealworld.team.adapters.antigravity"],
      "config": {"model": "gemini-4-neon-medium", "skip_permissions": true}
    }

Config keys (all optional): ``executable`` (default ``agy``), ``model``,
``reasoning_effort`` (``--effort``), ``mode`` (``--mode``), ``sandbox``
(``--sandbox``), ``skip_permissions`` (default false) and ``env``. Model slugs
such as ``gemini-4-neon-medium`` already select an effort level; omit
``reasoning_effort`` for them, because ``agy`` rejects a conflicting ``--effort``.

Permissions: headless ``agy`` cannot ask for approval, so actions that need it
are soft-denied while the run still reports success. Roles must run simulators
and test scripts, so either grant every required command in
``permissions.allow`` (``~/.gemini/antigravity-cli/settings.json``) or opt in
to unattended approval with ``"skip_permissions": true``, which passes
``--dangerously-skip-permissions``. Any denied action reported by ``agy``
(``denied_actions``, or a permission notice on stderr) fails the phase, and the
failure is kept even if a later envelope correction succeeds.

Limitations compared with the Codex and Claude adapters:

- Subagent access is not enforced by the CLI. For roles without the
  ``subagents`` capability (the Manager), the prompt asks the role to work
  without delegation.
- ``agy`` loads the user's global rules, skills and plugins. Use a clean
  account configuration for controlled experiments.
- Credentials live in the host keyring, so this adapter supports
  ``runtime: local`` only unless the image provides its own ``agy`` login.

Native events and diagnostics are saved under each role's
``session/invocations/`` directory.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from enrealworld.team.adapters.common import RESULT_CONTRACT, correction_prompt, read_result, result_instruction


MISSING_CONVERSATION = re.compile(
    r'no conversation found|unknown conversation|conversation[^\n:]*\bnot found', re.I
)
# Headless agy reports soft-denied tool calls on stderr and still exits 0.
PERMISSION_NOTICE = re.compile(
    r'^.*\b(?:permission|approval)\b.*\b(?:denied|required|not granted|soft-denied)\b.*$', re.I | re.M
)


def _skip_permissions(config):
    value = config.get('skip_permissions', False)
    if type(value) is not bool:
        raise ValueError('skip_permissions must be a boolean')
    return value


def _command(config, paths, session):
    command = [config.get('executable', 'agy'), '--input-format', 'stream-json',
               '--output-format', 'stream-json']
    if session:
        command += ['--conversation', session]
    for key, flag in (('model', '--model'), ('reasoning_effort', '--effort'), ('mode', '--mode')):
        if config.get(key):
            command += [flag, config[key]]
    if config.get('sandbox'):
        command.append('--sandbox')
    if _skip_permissions(config):
        command.append('--dangerously-skip-permissions')

    directories = {}
    for value in paths.values():
        path = Path(value)
        directory = path.parent if path.is_file() else path
        if directory.is_dir() and directory != directory.parent:
            directories[str(directory.resolve())] = None
    for directory in directories:
        command += ['--add-dir', directory]
    return command


def _native_result(events_path):
    final = None
    with events_path.open(encoding='utf-8', errors='replace') as events:
        for line in events:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get('event') == 'result':
                if final is not None or not isinstance(event.get('result'), dict):
                    raise ValueError('Expected one Antigravity result object per turn')
                final = event['result']
    return final or {}


def _denials(events_path, stderr, skip_permissions):
    """Collect actions agy denied for lack of approval during this invocation."""
    denied = []
    with events_path.open(encoding='utf-8', errors='replace') as events:
        for line in events:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            for payload in (event, event.get('result'), event.get('step_update')):
                actions = payload.get('denied_actions') if isinstance(payload, dict) else None
                if isinstance(actions, list):
                    denied.extend(actions)
                elif actions:
                    denied.append(actions)
    if not skip_permissions:
        denied.extend(PERMISSION_NOTICE.findall(stderr))
    unique = []
    for action in denied:
        if action not in unique:
            unique.append(action)
    return unique


def execute(request, *, recover_session=True, corrections=0, prior_denials=()):
    config = request['config']
    paths = request['paths']
    session = request.get('session')
    subagents = request.get('capabilities', {}).get('subagents', True)
    if type(subagents) is not bool:
        raise ValueError('capabilities.subagents must be a boolean')

    log = Path(paths['/session']) / 'invocations' / uuid.uuid4().hex
    log.mkdir(parents=True)
    result_path = Path(paths['/role']) / 'result.json'
    result_path.unlink(missing_ok=True)
    command = _command(config, paths, session)
    (log / 'invocation.json').write_text(json.dumps(dict(command=command, session=session)))

    prompt = request['prompt'] + '\nRuntime paths: ' + json.dumps(paths)
    if not subagents:
        prompt += '\nPerform this phase yourself without delegating to subagents.'
    prompt += RESULT_CONTRACT + result_instruction(result_path)
    event = json.dumps({'event': 'user', 'message': {'content': prompt}}) + '\n'
    events_path = log / 'events.jsonl'
    try:
        with events_path.open('w', encoding='utf-8') as events:
            process = subprocess.run(command, input=event, encoding='utf-8', errors='replace',
                                     stdout=events, stderr=subprocess.PIPE,
                                     env=dict(os.environ, **config.get('env', {})))
        returncode, stderr = process.returncode, process.stderr or ''
    except OSError as exc:
        returncode, stderr = None, f'Could not launch Antigravity CLI: {exc}\n'
    (log / 'stderr.log').write_text(stderr, encoding='utf-8')
    sys.stderr.write(stderr)

    response = dict(session=session, usage=None, native_log=str(log))
    denials = list(prior_denials)
    for action in _denials(events_path, stderr, _skip_permissions(config)):
        if action not in denials:
            denials.append(action)
    if denials:
        (log / 'denied-actions.json').write_text(json.dumps(denials, indent=2))
    try:
        final = _native_result(events_path)
    except ValueError as exc:
        return dict(response, result=dict(status='failed', summary=str(exc)))
    error = str(final.get('error') or '')
    native_session = final.get('conversation_id')
    failed = returncode != 0 or final.get('status') != 'SUCCESS'
    changed_session = session and native_session and native_session != session
    # agy may warn about a missing ID, then run the prompt in a fresh conversation.
    if session and (failed or changed_session) and MISSING_CONVERSATION.search(stderr + '\n' + error):
        if result_path.is_file():
            shutil.copyfile(result_path, log / 'unbound-result.json')
        if recover_session and request.get('recovery_prompt'):
            recovered = execute(dict(request, session=None, prompt=request['recovery_prompt']),
                                recover_session=False, corrections=corrections, prior_denials=denials)
            recovered['session_recovery'] = dict(previous_log=str(log))
            return recovered
        result = dict(status='failed', summary='Antigravity could not resume the previous conversation')
        return dict(response, session=None, result=result)
    elif isinstance(native_session, str) and native_session:
        if changed_session:
            result = dict(status='failed', summary='Antigravity returned a different conversation ID on resume')
            return dict(response, session=None, result=result)
        response['session'] = native_session

    if isinstance(final.get('usage'), dict):
        # Native counters may include earlier turns. Keep their scope explicit.
        response['usage'] = dict(final['usage'], scope='conversation')
    if failed:
        detail = error or stderr.strip()
        outcome = final.get('status', 'no result event')
        summary = f'Antigravity CLI exited {returncode} ({outcome})'
        result = dict(status='failed', summary=summary + (f': {detail[:300]}' if detail else ''))
        return dict(response, result=result)
    if not isinstance(native_session, str) or not native_session:
        result = dict(status='failed', summary='Antigravity completed without a conversation ID')
        return dict(response, result=result)

    try:
        result = read_result(result_path, request, log)
    except (OSError, ValueError) as exc:
        if result_path.is_file():
            shutil.copyfile(result_path, log / 'invalid-result.txt')
        (log / 'protocol-error.json').write_text(json.dumps(dict(error=str(exc), session=native_session)))
        if corrections < 2:
            corrected = execute(dict(request, session=native_session, prompt=correction_prompt(exc, result_path)),
                                recover_session=False, corrections=corrections + 1, prior_denials=denials)
            corrected['protocol_recovery'] = dict(previous_log=str(log), attempts=corrections + 1)
            return corrected
        result = dict(status='failed', summary='Antigravity did not produce a valid result after envelope correction')
    if denials:
        # A denied action means the role could not run part of its work. Keep the
        # failure across envelope corrections, which only repair the JSON file.
        result = dict(result, status='failed', denied_actions=denials[:20],
                      summary='Antigravity soft-denied tool calls without approval; '
                              'grant them in permissions.allow or enable skip_permissions. '
                              + str(result.get('summary', '')))
    return dict(response, result=result)


if __name__ == '__main__':
    json.dump(execute(json.load(sys.stdin)), sys.stdout)
