"""Optional native Claude Code command adapter; JSON stdin/stdout, headless ``claude -p``.

Same wire protocol as ``codex.py`` (see ``team/agents.py`` ``CommandAgent``): the
request arrives on stdin and ``{session, result, usage, native_log}`` is written to
stdout. Each role keeps one Claude Code session that is resumed phase after phase.

Example team configuration::

    "agent": {
      "command": ["<venv>/bin/python", "-m", "enrealworld.team.adapters.claude"],
      "config": {"model": "claude-opus-5-5", "permission_mode": "bypassPermissions",
                 "max_budget_usd": 50, "args": ["--setting-sources", "user"]}
    }

Config keys (all optional): ``executable`` (default ``claude``), ``model``,
``permission_mode`` (default ``bypassPermissions``; local runs are unattended),
``max_budget_usd`` (per invocation), ``args`` (appended verbatim), ``env`` and
``config_dir`` (sets ``CLAUDE_CONFIG_DIR``). By default the caller's login is
used; on macOS OAuth credentials live in the keychain, so a separate config_dir
needs its own login or ``ANTHROPIC_API_KEY``.

Claude Code stores sessions per working directory. The runner always invokes a
role from the same work directory, which is what makes ``--resume`` work.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from enrealworld.team.adapters.common import RESULT_CONTRACT, correction_prompt, read_result, result_instruction

MISSING_SESSION = 'No conversation found with session ID'
SUBAGENT_TOOLS = ('Task', 'Agent')


def _add_dirs(paths):
    dirs = []
    for value in paths.values():
        path = Path(value)
        if path.is_file():
            path = path.parent
        if path.is_dir():
            dirs.append(str(path.resolve()))
    return list(dict.fromkeys(dirs))


def execute(request):
    config = request['config']
    home = Path(request['paths']['/session'])
    home.mkdir(parents=True, exist_ok=True)
    log = home/'invocations'/uuid.uuid4().hex
    log.mkdir(parents=True)
    result_path = Path(request['paths']['/role'])/'result.json'
    result_path.unlink(missing_ok=True)
    capabilities = request.get('capabilities', {})
    if 'subagents' in capabilities and type(capabilities['subagents']) is not bool:
        raise ValueError('capabilities.subagents must be a boolean')

    command = [config.get('executable', 'claude'), '-p', '--output-format', 'stream-json', '--verbose']
    if request.get('session'):
        session = request['session']
        command += ['--resume', session]
    else:
        session = str(uuid.uuid4())
        command += ['--session-id', session]
    if config.get('model'):
        command += ['--model', config['model']]
    command += ['--permission-mode', config.get('permission_mode', 'bypassPermissions')]
    if config.get('max_budget_usd') is not None:
        command += ['--max-budget-usd', str(config['max_budget_usd'])]
    for directory in _add_dirs(request['paths']):
        command += ['--add-dir', directory]
    command += config.get('args', [])
    # Explicit capability requirements are applied last so they override caller args.
    if capabilities.get('subagents') is False:
        command += ['--disallowedTools', *SUBAGENT_TOOLS]

    prompt = request['prompt']+'\nRuntime paths: '+json.dumps(request['paths'])
    prompt += RESULT_CONTRACT
    prompt += result_instruction(result_path)
    env = dict(os.environ, **config.get('env', {}))
    if config.get('config_dir'):
        env['CLAUDE_CONFIG_DIR'] = str(config['config_dir'])
    (log/'invocation.json').write_text(json.dumps(dict(command=command, session=request.get('session'))))
    with (log/'events.jsonl').open('w') as out:
        process = subprocess.run(command, input=prompt, text=True, stdout=out,
                                 stderr=subprocess.PIPE, env=env)
    stderr = process.stderr or ''
    (log/'stderr.log').write_text(stderr)
    sys.stderr.write(stderr)

    final = None
    for line in (log/'events.jsonl').read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'system' and event.get('subtype') == 'init' and event.get('session_id'):
            session = event['session_id']
        if event.get('type') == 'result':
            final = event
    usage = None
    if final is not None:
        usage = dict(final.get('usage') or {})
        for key in ('total_cost_usd', 'num_turns', 'duration_ms'):
            if key in final:
                usage[key] = final[key]
    errors = ' '.join(str(e) for e in (final or {}).get('errors', []))

    missing = request.get('session') and process.returncode and MISSING_SESSION in stderr+errors
    if missing and not config.get('_session_recovered') and request.get('recovery_prompt'):
        recovered = execute(dict(request, session=None, prompt=request['recovery_prompt'],
                                 config=dict(config, _session_recovered=True)))
        recovered['session_recovery'] = dict(previous_log=str(log))
        return recovered
    if missing:
        session = None  # The requested session does not exist; never report it as live.
    if process.returncode or (final or {}).get('is_error'):
        subtype = (final or {}).get('subtype', 'no result event')
        detail = errors or str((final or {}).get('result') or '')
        result = dict(status='failed', summary=f'Claude Code exited {process.returncode} ({subtype}); inspect native events'
                      + (': '+detail[:300] if detail else ''))
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
            result = dict(status='failed', summary='Claude Code did not produce a valid result object after envelope correction')
    return dict(session=session, result=result, usage=usage, native_log=str(log))


if __name__ == '__main__':
    json.dump(execute(json.load(sys.stdin)), sys.stdout)
