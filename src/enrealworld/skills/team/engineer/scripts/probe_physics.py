"""Reproduce a reported problem on its delivered build through the native Session API."""
import argparse
import hashlib
import inspect
import json
import math
from pathlib import Path


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def run(build, actions_path, output, *, problem, checks_path=None):
    build, output = Path(build).resolve(strict=True), Path(output).resolve()
    if output.is_relative_to(build):
        raise ValueError('output must be outside the delivered build')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='unavailable', acceptance_eligible=False, build=str(build),
                  scope='problem-directed local diagnostic; independent Researcher acceptance required',
                  problem=problem,
                  rendering='unavailable: native state keyframes only; no renderer invoked')
    try:
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError('problem must identify an existing failure, anomaly or repair task')
        from enrealworld.utils.backends import dispatch
        actions_bytes = Path(actions_path).read_bytes()
        actions = json.loads(actions_bytes)
        if not isinstance(actions, list) or not actions:
            raise ValueError('actions must be a nonempty JSON list')
        (output/'requested-actions.json').write_bytes(actions_bytes)
        report['actions_sha256'] = hashlib.sha256(actions_bytes).hexdigest()
        report['inputs_sha256'] = hashes(build)
        report['candidate_digest'] = hashlib.sha256(json.dumps(report['inputs_sha256'], sort_keys=True).encode()).hexdigest()
        report['execution_kind'] = 'native_physics'
        desc = json.loads((build/'build.json').read_text())
        config = json.loads((build/'backend-config.json').read_text())
        module = dispatch.load(desc['backend'], config, root=build)
        supported = dispatch.actions(desc['backend'], config, build)
        report['supported_actions'] = sorted(supported)
        report['backend'] = desc['backend']
        report['adapter_sha256'] = hashlib.sha256(Path(inspect.getfile(module)).read_bytes()).hexdigest()
        for action in actions:
            if not isinstance(action, dict) or action.get('type') not in supported:
                raise ValueError('unsupported action: '+str(action))
            duration = action.get('duration_s')
            if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
                raise ValueError('positive finite duration_s required')
        session = module.Session(build, output/'native')
        for action in actions:
            session.advance(action)
        info = session.finish()
        report['session'] = info
        if report['inputs_sha256'] != hashes(build):
            raise ValueError('delivered build changed during probe; evidence invalid')
        states = json.loads((output/'native/states.json').read_text())
        if not states:
            raise ValueError('adapter produced no native states')
        # Native trajectories must remain finite; a completed step loop alone is insufficient.
        def finite(value):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('nonfinite native state')
            if isinstance(value, dict):
                for v in value.values(): finite(v)
            if isinstance(value, list):
                for v in value: finite(v)
        finite(states)
        report['state_keyframes'] = [states[i] for i in sorted({0, len(states)//2, len(states)-1})]
        report['status'] = 'executed'
        report['checks'] = {'structure': 'loaded', 'geometry': 'unknown', 'physical_acceptance': 'unknown'}
        if checks_path:
            from enrealworld.utils.validation.development_checks import evaluate
            check_bytes = Path(checks_path).read_bytes()
            (output/'requested-checks.json').write_bytes(check_bytes)
            spec = json.loads(check_bytes)
            report['checks_sha256'] = hashlib.sha256(check_bytes).hexdigest()
            native = json.loads((output/'native/native.json').read_text())
            contacts = json.loads((output/'native/contacts.json').read_text())
            result = evaluate(spec, states, contacts, native, info)
            report['interaction'] = result
            report['checks']['physical_acceptance'] = result['outcome']
            if result['outcome'] != 'pass':
                report['status'] = 'failed' if result['outcome'] == 'fail' else 'incomplete'

    except Exception as exc:
        report['reason'] = type(exc).__name__+': '+str(exc)
    (output/'probe.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checks', help='Task-declared interaction contract JSON; missing observations remain incomplete')
    parser.add_argument('--problem', required=True, help='Existing issue/evidence reference and symptom or explicit repair task')
    parser.add_argument('--build', required=True)
    parser.add_argument('--actions', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = run(args.build, args.actions, args.output, problem=args.problem, checks_path=args.checks)
    print(json.dumps({k: report[k] for k in ('status', 'reason') if k in report}))
    return 0 if report['status'] == 'executed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
