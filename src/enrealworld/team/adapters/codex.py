"""Optional native Codex command adapter; JSON stdin/stdout, persistent /session."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from enrealworld.team.adapters.common import RESULT_CONTRACT, correction_prompt, read_result, result_instruction


def execute(request):
    config = request['config']
    home = Path(request['paths']['/session'])
    home.mkdir(parents=True, exist_ok=True)
    # Credentials are explicitly supplied by the caller, never returned in logs.
    if config.get('auth_file'):
        shutil.copyfile(config['auth_file'], home/'auth.json')
        (home/'auth.json').chmod(0o600)
    if config.get('config_file'):
        shutil.copyfile(config['config_file'], home/'config.toml')
    log = home/'invocations'/uuid.uuid4().hex
    log.mkdir(parents=True)
    result_path = Path(request['paths']['/role'])/'result.json'
    result_path.unlink(missing_ok=True)
    command = [config.get('executable', 'codex'), 'exec']
    if request.get('session'):
        command += ['resume', request['session']]
    command += ['--skip-git-repo-check', '--json', '--model', config['model'],
                '-c', 'model_reasoning_effort='+json.dumps(config['reasoning_effort'])]
    command += config.get('args', [])
    # Explicit capability requirements override copied and caller-provided config.
    capabilities = request.get('capabilities', {})
    if 'subagents' in capabilities:
        if type(capabilities['subagents']) is not bool:
            raise ValueError('capabilities.subagents must be a boolean')
        enabled = str(capabilities['subagents']).lower()
        command += ['-c', 'features.multi_agent='+enabled, '-c', 'agents.enabled='+enabled]
    command += ['-']
    prompt = request['prompt']+'\nRuntime paths: '+json.dumps(request['paths'])
    prompt += RESULT_CONTRACT
    prompt += result_instruction(result_path)
    (log/'invocation.json').write_text(json.dumps(dict(command=command, session=request.get('session'))))
    with (log/'events.jsonl').open('w') as out:
        process = subprocess.run(command, input=prompt, text=True, stdout=out,
                                 stderr=subprocess.PIPE, env=dict(os.environ, CODEX_HOME=str(home)))
    stderr = process.stderr or ''
    (log/'stderr.log').write_text(stderr)
    sys.stderr.write(stderr)
    session = request.get('session')
    usage = None
    for line in (log/'events.jsonl').read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'thread.started':
            session = event['thread_id']
        if event.get('type') == 'turn.completed':
            usage = event.get('usage')
    missing = (request.get('session') and process.returncode and
               re.search(r'no rollout found for thread id ' + re.escape(request['session']) + r'\s*\(code -32600\)', stderr))
    if missing and not config.get('_session_recovered') and request.get('recovery_prompt'):
        recovered = execute(dict(request, session=None, prompt=request['recovery_prompt'],
                                 config=dict(config, _session_recovered=True)))
        recovered['session_recovery'] = dict(previous_log=str(log))
        return recovered
    if process.returncode:
        result = dict(status='failed', summary=f'Codex exited {process.returncode}; inspect native events')
    else:
        try:
            result = read_result(result_path, request, log)
        except (OSError, ValueError) as exc:
            # Keep the original response before asking the SAME session to repair
            # only its response envelope. Never infer physics success from aliases.
            if result_path.exists():
                shutil.copyfile(result_path, log/'invalid-result.txt')
            (log/'protocol-error.json').write_text(json.dumps(dict(error=str(exc), session=session)))
            retries = config.get('_protocol_retries', 0)
            if session and retries < 2:
                correction = dict(request, session=session,
                    config=dict(config, _protocol_retries=retries+1),
                    prompt=correction_prompt(exc, result_path))
                recovered = execute(correction)
                recovered['protocol_recovery'] = dict(previous_log=str(log), attempts=retries+1)
                return recovered
            result = dict(status='failed', summary='Codex did not produce a valid result object after envelope correction')
    return dict(session=session, result=result, usage=usage, native_log=str(log))


if __name__ == '__main__':
    json.dump(execute(json.load(sys.stdin)), sys.stdout)
