"""Provider-neutral local sessions. Commands consume a JSON request on stdin.

The agent owns session creation/resumption and returns JSON containing ``session``
and ``result``. stdout is reserved for that response; diagnostics go to stderr.
``capabilities.subagents`` declares whether the role needs delegation.
"""
import json
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
import os
import re
import subprocess
import signal
import time


class CommandAgent:
    def __init__(self, config):
        self.config = config
        self.session = None
        self.usage = None
        command = config.get('command')
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError('agent.command must be a nonempty argv list')

    def run(self, request, cwd, timeout, log, cancelled):
        self.usage = None
        request = dict(request, session=self.session, config=self.config.get('config', {}))
        with (log / 'stderr.log').open('w') as err:
            with (log/'response.json').open('w') as out:
                process = subprocess.Popen(self.config['command'], stdin=subprocess.PIPE,
                    stdout=out, stderr=err, text=True, cwd=cwd, start_new_session=True,
                    env=dict(os.environ, **self.config.get('env', {})))
                try:
                    process.stdin.write(json.dumps(request))
                    process.stdin.close()
                    deadline = time.monotonic()+timeout
                    while process.poll() is None:
                        if cancelled.wait(.05) or time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(self.config['command'], timeout)
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, self.config['command'])
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
        response_text = (log/'response.json').read_text()
        response = json.loads(response_text)
        self.session = response.get('session', self.session)
        self.usage = response.get('usage')
        return response['result']


class AgentTeamMixin:
    """Local execution has no filesystem or resource isolation."""

    def phase(self, role, phase, first=False, candidate=None):
        from .runner import REPO, dump, inventory
        import time
        import uuid
        output = self.root/role/'output'
        work = self.root/role/('delivery' if role == 'engineer' else 'output')
        paths = {'/public': self.root/'input', '/input-seed': self.root/'seed-input',
                 '/session': self.root/role/'session', '/role': output, '/workspace/output': work, '/coordination': self.view/role}
        if phase == 'intake':
            paths.pop('/coordination')
        if candidate:
            paths['/candidate-binding.json'] = candidate.parent/(candidate.name+'.json')
            paths['/candidate'] = candidate
        from .scheduling import COMMON_PROTOCOL, phase_protocol
        role_directory = Path(__file__).resolve().parents[1]/'skills'/'team'/role
        if role in ('manager', 'researcher', 'engineer'):
            paths[f'/{role}-tools'] = role_directory/'scripts'
            paths[f'/{role}-skill'] = role_directory
        shared = role_directory.parent/'shared'
        if role in ('manager', 'researcher', 'engineer'):
            paths['/constraint-tools'] = shared/'scripts'
            paths['/shared'] = shared
        phase_text = phase_protocol(role, phase)
        references = (f'\nRole skill and references: /{role}-skill/SKILL.md; '
                      '/shared/references/constraints.md. Use these when relevant.\n')
        full_prompt = (f'You are the {role}, assigned phase {phase}. The task below describes the team deliverable.\n'
                  +self.c['task']+'\n'+COMMON_PROTOCOL+'\n'+phase_text+references)
        def map_paths(value):
            if self.c['runtime'] == 'local':
                for alias in sorted(paths, key=len, reverse=True):
                    value = value.replace(alias, str(paths[alias]))
            else:
                mappings = [(str(Path(path).resolve()), alias) for alias, path in paths.items()]
                mappings += [(str(Path(m['source']).resolve()), m['target'])
                             for m in self.agents[role].config.get('mounts', [])]
                for source, alias in sorted(mappings, key=lambda item: len(item[0]), reverse=True):
                    value = re.sub(re.escape(source) + r'(?=$|[/\s"\x27`,;:)}\]]|[.!?](?=$|[\s"\x27`)}\]]))', lambda _: alias, value)
            return value
        full_prompt = map_paths(full_prompt)
        phase_text = map_paths(COMMON_PROTOCOL+'\n'+phase_text)
        if self.c['runtime'] == 'local':
            aliases = ('/role', '/workspace/output', '/public', '/input-seed', '/coordination',
                       f'/{role}-tools', '/constraint-tools', '/candidate', '/candidate-binding.json')
            local_paths = {alias: str(paths[alias]) for alias in aliases if alias in paths}
            note = '\nDocumentation uses virtual paths; translate them using: '+json.dumps(local_paths)+'\n'
            full_prompt += note
            phase_text += note
        log = self.root/'coordination'/uuid.uuid4().hex
        log.mkdir()
        context_file = log/'context.txt'
        context_file.write_text(full_prompt)
        context_file.chmod(0o444)
        paths['/role-context.txt'] = context_file
        agent = self.agents[role]
        original_config = agent.config
        command = agent.config['command']
        agent.config = dict(agent.config, env=dict(self.c.get('env', {}), **agent.config.get('env', {})))
        if self.c['runtime'] == 'docker':
            name = 'enrealworld-' + uuid.uuid4().hex
            container_paths = {key:key for key in paths}
            argv = ['docker', 'run', '--rm', '-i', '--name', name]
            concurrent = 3 if getattr(self, 'schedule', {}).get('stage') == 'work' else 1
            for key, flag in (('cpus', '--cpus'), ('memory_mib', '--memory')):
                if key in self.c:
                    amount = self.c[key] / concurrent
                    if amount <= 0:
                        raise ValueError('resource budget must be positive')
                    if key == 'cpus':
                        quota = (Decimal(str(self.c[key])) / concurrent).quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
                        if quota <= 0:
                            raise ValueError('CPU allocation is below supported precision')
                        argv += [flag, format(quota, 'f')]
                    else:
                        argv += [flag, str(int(amount))+'m']
            for key, flag in (('user', '--user'), ('platform', '--platform'), ('network', '--network')):
                if key in self.c:
                    argv += [flag, self.c[key]]
            for capability in self.c.get('cap_drop', []):
                argv += ['--cap-drop', capability]
            for option in self.c.get('security_opt', []):
                argv += ['--security-opt', option]
            if self.c.get('read_only', False):
                argv += ['--read-only']
            if self.c.get('tmpfs_size'):
                argv += ['--tmpfs', '/tmp:rw,nosuid,nodev,size='+self.c['tmpfs_size']]
            if self.c.get('pids_limit'):
                argv += ['--pids-limit', str(self.c['pids_limit'])]
            for mount in agent.config.get('mounts', []):
                source = str(Path(mount['source']).resolve(strict=True))
                argv += ['--mount', f"type=bind,src={source},dst={mount['target']}"+(',readonly' if mount.get('readonly', True) else '')]
            for alias, path in paths.items():
                readonly = alias not in ('/session', '/role', '/workspace/output') or (alias == '/workspace/output' and role == 'engineer' and not phase.startswith(('work:', 'self_test:', 'repair:')))
                argv += ['--mount', f'type=bind,src={path},dst={alias}'+(',readonly' if readonly else '')]
            for key, value in dict(self.c.get('env', {}), **agent.config.get('env', {})).items():
                argv += ['-e', f'{key}={value}']
            argv += ['--workdir', '/workspace/output', '--entrypoint', command[0], self.c['image'], *command[1:]]
            agent.config = dict(agent.config, command=argv)
            request_paths = container_paths
        else:
            request_paths = {k:str(v) for k,v in paths.items()}
        request_file = output/'requirement-request.json'
        request_id = None

        def consume_request(result):
            if role != 'manager' or not request_file.exists():
                return result
            try:
                request = json.loads(request_file.read_text())
            finally:
                request_file.unlink(missing_ok=True)
            if not isinstance(request, dict) or request.get('request_id') != request_id:
                raise ValueError('invalid or stale checklist request')
            result = dict(result, requirement_request_id=request_id)
            if isinstance(request.get('error'), str) and request['error']:
                result = dict(result, requirement_error=request['error'])
                result.pop('requirement_checklist', None)
            elif isinstance(request.get('path'), str):
                if 'requirement_checklist' in result and result['requirement_checklist'] != request['path']:
                    raise ValueError('conflicting checklist request and result')
                result = dict(result, requirement_checklist=request['path'])
            else:
                raise ValueError('invalid checklist request')
            return result

        try:
            remaining = self.deadline-time.monotonic()
            if remaining <= 0:
                raise ValueError('task wall budget exhausted')
            from .contracts import validate
            result = None
            for attempt in range(3):
                attempt_log = log/str(attempt)
                attempt_log.mkdir()
                remaining = self.deadline-time.monotonic()
                if remaining <= 0: raise ValueError('task wall budget exhausted')
                if role == 'manager':
                    request_file.unlink(missing_ok=True)
                    request_id = uuid.uuid4().hex
                    dump(output/'requirement-request-context.json',
                         dict(request_id=request_id,
                              request_path='/role/requirement-request.json' if self.c['runtime'] == 'docker' else str(request_file)))
                context_ref = '/role-context.txt' if self.c['runtime'] == 'docker' else str(context_file)
                if not agent.session:
                    prompt = full_prompt + '\nFull task and protocol reference: ' + context_ref
                else:
                    coordination = request_paths.get('/coordination', 'unavailable during intake')
                    binding = request_paths.get('/candidate-binding.json', 'no frozen candidate')
                    prompt = (f'Role: {role}; phase: {phase}. Full task and protocol: {context_ref}. '
                              f'Latest coordination: {coordination}; candidate binding: {binding}.\n'
                              +phase_text)
                if attempt:
                    prompt += '\nCorrect your previous return contract: '+error+'\nReturn a complete corrected result object; preserve real evidence and unknown outcomes.'
                    if role == 'manager':
                        prompt += ' Re-run the checklist submission in this attempt if needed.'
                (attempt_log/'prompt.txt').write_text(prompt)
                result = self.agents[role].run(dict(prompt=prompt, phase=phase, role=role,
                capabilities=dict(subagents=role in ('engineer', 'researcher')),
                paths=request_paths, recovery_prompt=full_prompt + f'\nLatest coordination: {request_paths.get("/coordination", "unavailable during intake")}; candidate binding: {request_paths.get("/candidate-binding.json", "no frozen candidate")}. Continue with existing work and evidence.',
                stage=getattr(self, 'schedule', {}).get('stage'),
                round=getattr(self, 'schedule', {}).get('round')), work, remaining, attempt_log, self.cancelled)
                try:
                    validate(result, role, phase)
                    if role == 'manager' and 'requirement_checklist' in result:
                        raise ValueError('submit the Markdown checklist with checklist_tool.py instead of returning it')
                    result = consume_request(result)
                    valid_evidence = []
                    for ref in result.get('evidence', []):
                        path = (output/ref).resolve()
                        if path.is_relative_to(output.resolve()) and path.is_file():
                            valid_evidence.append(ref)
                        else:
                            result.setdefault('attachment_errors', []).append(dict(ref=ref, reason='requires an existing file inside /role'))
                    result['evidence'] = valid_evidence
                    break
                except (ValueError, TypeError) as exc:
                    dump(attempt_log/'contract-error.json', {'error': str(exc), 'attempt': attempt+1})
                    if attempt == 2: raise
                    error = str(exc)
            inventory(output)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            result = dict(status='failed', summary=str(exc))
            if role == 'manager' and request_id is not None:
                try:
                    result = consume_request(result)
                except (OSError, ValueError, TypeError) as error:
                    result['requirement_error'] = str(error)
        finally:
            agent.config = original_config
            if self.c['runtime'] == 'docker':
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        self.sessions[role] = self.agents[role].session
        receipt = dict(role=role, phase=phase, result=result, session=self.sessions[role], usage=agent.usage)
        self.receipts.append(receipt)
        dump(log/'receipt.json', receipt)
        return result
