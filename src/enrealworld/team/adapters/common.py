"""Provider-neutral helpers shared by native agent adapters (Codex, Claude Code, Antigravity)."""
import json
from pathlib import Path
import shutil


RESULT_CONTRACT = ('\nAdapter phase result contract: write one JSON object with status exactly passed or failed and a string summary. '
                   'Use passed only for phase requirements verified by evidence. '
                   'Use failed for unmet or unverified requirements; identify untested claims as unknown.')


def result_instruction(result_path):
    return '\nWrite your response object (status, summary and any coordination fields) to '+str(result_path)+'.'


def correction_prompt(exc, result_path):
    return ('Adapter could not parse your phase result: '+str(exc)+
            '. Repair only the JSON envelope at '+str(result_path)+
            '. Preserve all existing work and evidence. status must be exactly passed or failed; '
            'Use passed only for phase requirements verified by evidence. '
            'Use failed for unmet or unverified requirements; mark untested claims unknown. '
            'Preserve decision, candidate_digest, requirement_version, messages, dispatch and evidence when applicable. '
            'Do not redo implementation or retest during this envelope correction.')


def normalize_evidence(result, paths):
    """Rewrite evidence and message refs to files inside /role.

    Roles sometimes cite delivery/candidate paths rather than /role. Files under
    other permitted task paths are preserved as byte-identical snapshots in /role;
    anything else is reported in ``attachment_errors``. No test outcome is inferred.
    Returns the list of rewrites performed.
    """
    rewrites = []
    normalized_refs = {}
    evidence = []
    role_root = Path(paths['/role']).resolve()
    refs = list(result.get('evidence', []))
    for message in result.get('messages', []):
        refs.extend(ref for ref in message.get('refs', [])
                    if not ref.startswith('/candidate/') and ref != '/candidate-binding.json')
    refs = list(dict.fromkeys(refs))
    for ref in refs:
        if not isinstance(ref, str):
            raise ValueError('evidence references must be strings')
        try:
            source = Path(ref) if Path(ref).is_absolute() else role_root/ref
            if not source.is_file() and not Path(ref).is_absolute():
                source = Path(paths.get('/workspace/output', role_root))/ref
            source = source.resolve()
            if not source.is_file():
                raise ValueError('evidence is not an existing file: '+ref)
            if source.is_relative_to(role_root):
                evidence.append(str(source.relative_to(role_root)))
                normalized_refs[ref] = evidence[-1]
                continue
            for alias in ('/workspace/output', '/candidate', '/public', '/coordination'):
                base = Path(paths.get(alias, '/__unmounted__')).resolve()
                if source.is_relative_to(base):
                    relative = source.relative_to(base)
                    target = role_root/'adapter-evidence'/alias.strip('/').replace('/', '-')/relative
                    if not target.resolve().is_relative_to(role_root):
                        raise ValueError('evidence destination outside role directory')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    evidence.append(str(target.relative_to(role_root)))
                    normalized_refs[ref] = evidence[-1]
                    rewrites.append(dict(original=ref, evidence=evidence[-1], action='byte-identical evidence copy; no test outcome inferred'))
                    break
            else:
                raise ValueError('evidence outside permitted task paths: '+ref)
        except (OSError, ValueError) as exc:
            result.setdefault('attachment_errors', []).append(dict(ref=ref, reason=str(exc)))
    result['evidence'] = list(dict.fromkeys(evidence))
    for message in result.get('messages', []):
        message['refs'] = [normalized_refs.get(ref, ref) for ref in message.get('refs', [])
                           if ref in normalized_refs or ref.startswith('/candidate/') or ref == '/candidate-binding.json']
        if result.get('attachment_errors'):
            message['attachment_errors'] = result['attachment_errors']
    return rewrites


def read_result(result_path, request, log):
    """Load, validate and normalize the role's result object; raise on an invalid envelope."""
    result = json.loads(Path(result_path).read_text())
    if isinstance(result, dict):
        from enrealworld.team.contracts import validate
        validate(result, request.get('role'), request.get('phase'))
        rewrites = normalize_evidence(result, request['paths'])
        if rewrites:
            (Path(log)/'evidence-rewrites.json').write_text(json.dumps(rewrites, indent=2))
            Path(result_path).write_text(json.dumps(result, indent=2))
    if (not isinstance(result, dict) or result.get('status') not in ('passed', 'failed')
            or not isinstance(result.get('summary'), str)):
        raise ValueError('invalid result')
    return result
