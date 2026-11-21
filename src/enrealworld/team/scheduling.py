"""Parallel work rounds separated by synchronous team meetings."""
import concurrent.futures as cf
import json
import time

COMMON_PROTOCOL = """Preserve original input values, cite sources and distinguish estimates from evidence.
Try supplied data and explicit form/template values first, even if they look illustrative.
Fill placeholders from evidence or documented estimates; select among listed options.
Before substitution, retain the baseline check and result, evidence of failure or concrete incompatibility, and the replacement and reason.
Missing tools or unrun checks mean unverified, not failed.
A failed attempt does not authorize relaxing fixed task constraints.
Use /coordination/state.json and history.json for assignments and handoffs when available.
Return JSON with status=passed/failed and summary; optional evidence paths are relative to /role, and messages are [{to, summary, refs}].
Never modify a frozen /candidate.
Share files with attachment_paths; see /coordination/attachments.json for prior shares."""

PHASE_INSTRUCTIONS = {
    ('manager', 'intake'): """Read /manager-skill/SKILL.md.
Register sources and propositions as found.
Before submitting, compare the checklist with original inputs for omitted or weakened requirements, supplied values, prohibitions, deliverables and acceptance conditions.
Include checks that try supplied data and template values first.
Submit with the checklist tool.
Engineer and Researcher work in parallel.""",
    ('manager', 'work'): """Track requirements and assignments.
Check the runner receipt in /coordination/requirement-receipt.json; correct and resubmit if rejected.
Execution outcomes may remain unverified and open questions need not all be closed.""",
    ('manager', 'manager_review'): """Review the candidate, Engineer repair record and Researcher findings against the accepted checklist.
Check the receipt and candidate/evidence versions; if Engineer did not report the current checklist version, treat its self-test coverage as unconfirmed.
Identify the unchecked or unreported checklist items; do not infer a pass from silence.
Compare actual inputs and values with the original sources.
For any substitution, verify the baseline result, failure or concrete incompatibility evidence, and replacement rationale.
Record input conformance and actual visual/physical effects separately and identify unverified checks.
Close material implementation findings with experiment-backed changes and independent retests, not reporting alone.""",
    ('manager', 'meeting'): """Chair the decision: return decision=engineer/researcher to ask a respondent with questions in messages, continue with optional dispatch [{role,instruction}], or finish with status and the reviewed candidate_digest.
Do not certify unverified conditions.
Continue while a feasible distinguishing test remains within budget.
Otherwise record attempted tests, blockers and unmet conditions.""",
    ('engineer', 'work'): """Implement and test /workspace/output from the original inputs.
Do not wait for the checklist before generating.
Provide an execution entry and evidence.""",
    ('engineer', 'self_test'): """Generation has finished.
Read the accepted checklist in /coordination/requirement-checklist.md and its version in /coordination/requirement-handoff.json; check its items against the implementation and correct discovered gaps where feasible.
Report the supplied inputs and values actually used; document substitutions with the baseline check/result, failure or concrete incompatibility evidence, and replacement rationale.
Return the checklist version used in the JSON field requirement_version, and report checked and unchecked items, findings and evidence.
Do not claim a check that was not run.""",
    ('engineer', 'repair'): """Address Researcher's findings and evidence for /candidate once.
Run distinguishing tests, update the mutable artifact from observations and rerun affected checks.
Keep blocked or inconclusive findings unresolved, with evidence.
Use any available /coordination/requirement-checklist.md for self-tests.
Return the version used in requirement_version, checked and unchecked items, findings and execution evidence.
The version is in /coordination/requirement-handoff.json.
Do not claim checks that were not run.""",
    ('researcher', 'work'): """Independently derive tests from original inputs.
Consult /researcher-skill/references/physical-probing.md as needed.""",
    ('researcher', 'review'): """Independently test the frozen /candidate against original inputs, including appearance, motion and physical interactions.
Record input conformance and observed effects separately, with evidence and candidate_digest.
Report requirement conflicts to Manager.
For material ambiguity or discrepancies, state competing explanations and design a distinguishing test using original inputs or independent observations.
Run where possible and send Manager evidence and proposed Engineer updates through messages/attachments.
Keep unresolved material findings failed, with attempted tests and blockers.""",
    ('researcher', 'retest'): """Retest affected findings on the new /candidate, with evidence and candidate_digest.
Rerun distinguishing tests and original failing checks against the baseline.
Reporting alone does not close an implementation discrepancy.""",
}


def phase_protocol(role, phase):
    name = phase.split(':', 1)[0]
    instruction = PHASE_INSTRUCTIONS.get((role, name))
    if instruction is None and name == 'meeting':
        instruction = 'Answer Manager with evidence and unresolved issues; do not decide the meeting.'
    if instruction is None:
        instruction = 'Follow the current assignment and report evidence and unresolved issues.'
    if role in ('engineer', 'researcher') and name in ('work', 'self_test', 'repair', 'review', 'retest'):
        instruction += f'\nFollow /{role}-skill/SKILL.md for delegation and role ownership.'
    return 'Phase instructions:\n' + instruction + '\n'


def execute(team):
    from .runner import ROLES, digest, dump
    from enrealworld.coordination import requirements
    history, tasks, latest = [], {}, {}
    candidate, final, identity, handed_version = None, None, None, None
    round_number = 0
    pool = cf.ThreadPoolExecutor(max_workers=3)

    def accepted_receipt():
        path = team.root/'coordination'/'requirement-receipt.json'
        state = requirements._read(team.root)
        receipt = json.loads(path.read_text()) if path.exists() else {}
        if state and receipt.get('status') == 'accepted':
            try:
                if receipt.get('version') != state['version']:
                    raise ValueError('receipt and checklist snapshot versions differ')
                requirements.snapshot(team.root, state)
                return receipt
            except (ValueError, KeyError, OSError) as exc:
                receipt.update(status='rejected', error=str(exc))
                dump(path, receipt)
        return None

    def publish(stage):
        team.schedule = dict(requirements_path='/coordination/requirements.json', stage=stage, round=round_number,
                             tasks=tasks, latest=latest,
                             focus=latest.get('manager', {}).get('focus', []),
                             history_path='/coordination/history.json',
                             candidate_digest=digest(candidate) if candidate else None)
        for entry in latest.values():
            tested = entry.get('world_state_source', {}).get('candidate_digest')
            entry['version_relation'] = ('unknown' if not tested else 'current' if candidate and tested == digest(candidate) else 'other_version')
        from enrealworld.coordination.scene_graph import status as graph_status
        team.schedule['scene_graph'] = graph_status(team.root, team.schedule['candidate_digest'])
        team.publish()
        dump(team.root/'coordination'/'state.json', team.schedule)

    def record(role, phase, result):
        from enrealworld.coordination.scene_graph import submit
        try:
            submit(team.root, role, result, digest(candidate) if candidate else None)
        except (ValueError, KeyError, TypeError, OSError, AttributeError, IndexError, StopIteration) as exc:
            result = dict(result, graph_error=str(exc))
        try:
            if role == 'manager' and result.get('requirement_error'):
                raise ValueError(result['requirement_error'])
            receipt = requirements.submit(team.root, role, result)
            if role == 'manager' and phase == 'intake' and receipt is None:
                detail = result.get('summary') if result.get('status') == 'failed' else None
                raise ValueError('No checklist submitted; run checklist_tool.py submit.'
                                 + (' Manager error: '+detail if detail else ''))
            if receipt is not None:
                if result.get('requirement_request_id'):
                    receipt['request_id'] = result['requirement_request_id']
                dump(team.root/'coordination'/'requirement-receipt.json', receipt)
                handoff = dict(version=receipt['version'], checklist_path='/coordination/requirement-checklist.md')
                dump(team.root/'coordination'/'requirement-handoff.json', handoff)
        except (ValueError, KeyError, TypeError, OSError, AttributeError, IndexError, StopIteration) as exc:
            result = dict(result, requirement_error=str(exc))
            if role == 'manager':
                state = requirements._read(team.root)
                receipt = dict(status='rejected', error=str(exc), revision=state['revision'] if state else None,
                               version=state.get('version') if state else None)
                if result.get('requirement_request_id'):
                    receipt['request_id'] = result['requirement_request_id']
                dump(team.root/'coordination'/'requirement-receipt.json', receipt)
        previous = latest.get(role, {})
        source = (dict(candidate_digest=result.get('candidate_digest'), phase=phase,
                       evidence=result.get('evidence', [])) if 'world_state' in result
                  else previous.get('world_state_source', {}))
        latest[role] = dict(phase=phase, summary=result.get('summary'),
                            world_state=result.get('world_state', latest.get(role, {}).get('world_state')),
                            focus=result.get('focus', latest.get(role, {}).get('focus', [])),
                            exploration=result.get('exploration', previous.get('exploration', [])),
                            evidence=result.get('evidence', []),
                            requirement_version=result.get('requirement_version'),
                            candidate_digest=result.get('candidate_digest'))
        latest[role]['world_state_source'] = source
        latest[role]['submission_errors'] = {k:result[k] for k in ('graph_error', 'requirement_error') if k in result}
        history.append(dict(role=role, phase=phase, result=result,
                            candidate_digest=result.get('candidate_digest'),
                            available_candidate_digest=digest(candidate) if candidate else None))
        dump(team.root/'coordination'/'history.json', history)
        return result

    def check_snapshot():
        if candidate and digest(candidate) != identity:
            raise ValueError('candidate mutated during team round')

    try:
        if time.monotonic() >= team.deadline:
            return dict(status='failed', reason='task wall budget exhausted', rounds=0, candidate=None, digest=None)
        while time.monotonic() < team.deadline and final is None:
            round_number += 1
            publish('work')
            phases = {role: 'intake' if role == 'manager' and round_number == 1
                      else f'work:{round_number}' for role in ROLES}
            futures = {role: pool.submit(team.phase, role, phases[role],
                       first=round_number == 1, candidate=candidate) for role in ROLES}
            # Record Manager's submission while Engineer continues its current generation.
            manager_result = futures['manager'].result()
            record('manager', phases['manager'], manager_result)
            results = {role: futures[role].result() for role in ('engineer', 'researcher')}
            check_snapshot()
            for role, result in results.items():
                record(role, phases[role], result)
            if time.monotonic() >= team.deadline:
                break
            for _ in range(2):
                if accepted_receipt():
                    break
                tasks['manager'] = 'Correct the checklist submission using /coordination/requirement-receipt.json.'
                publish('work')
                phase = f'work:{round_number}'
                record('manager', phase, team.phase('manager', phase, candidate=candidate))
            receipt = accepted_receipt()
            if not receipt:
                path = team.root/'coordination'/'requirement-receipt.json'
                error = json.loads(path.read_text()).get('error', 'missing acceptance') if path.exists() else 'missing acceptance'
                raise ValueError('Manager checklist not accepted: '+error)
            if receipt['version'] != handed_version:
                tasks['engineer'] = 'Self-test the accepted checklist against the completed generation and fix feasible gaps.'
                publish('self_test')
                current = accepted_receipt()
                if not current or current['version'] != receipt['version']:
                    raise ValueError('Accepted checklist is unavailable for self-test')
                phase = f'self_test:{round_number}'
                result = team.phase('engineer', phase, candidate=candidate)
                check_snapshot()
                record('engineer', phase, result)
                handed_version = receipt['version']
            if time.monotonic() >= team.deadline:
                break
            candidate = team.current_candidate(candidate)
            identity = digest(candidate)
            publish('review')
            phase = f'review:{round_number}'
            review = team.phase('researcher', phase, candidate=candidate)
            check_snapshot()
            if digest(team.root/'engineer'/'delivery') != identity:
                raise ValueError('engineering project changed during review')
            record('researcher', phase, review)
            if time.monotonic() >= team.deadline:
                break
            if review.get('status') != 'passed':
                tasks['engineer'] = ('Address Researcher findings and evidence for candidate '
                                     + identity + '; repair once or explain. Leave requirement disputes to Manager.')
                publish('repair')
                phase = f'repair:{round_number}'
                repair = team.phase('engineer', phase, candidate=candidate)
                check_snapshot()
                record('engineer', phase, repair)
                if time.monotonic() >= team.deadline:
                    break
                if digest(team.root/'engineer'/'delivery') != identity:
                    candidate = team.current_candidate(candidate)
                    identity = digest(candidate)
                    tasks['researcher'] = 'Retest affected findings against the new candidate; bind evidence to its digest.'
                    publish('retest')
                    phase = f'retest:{round_number}'
                    retest = team.phase('researcher', phase, candidate=candidate)
                    check_snapshot()
                    if digest(team.root/'engineer'/'delivery') != identity:
                        raise ValueError('engineering project changed during retest')
                    record('researcher', phase, retest)
                    if time.monotonic() >= team.deadline:
                        break
            publish('manager_review')
            phase = f'manager_review:{round_number}'
            result = team.phase('manager', phase, candidate=candidate)
            check_snapshot()
            if digest(team.root/'engineer'/'delivery') != identity:
                raise ValueError('engineering project changed during manager review')
            record('manager', phase, result)
            if time.monotonic() >= team.deadline:
                break
            publish('meeting')
            phase = f'meeting:{round_number}'
            role = 'manager'
            while time.monotonic() < team.deadline:
                result = team.phase(role, phase, candidate=candidate)
                check_snapshot()
                if digest(team.root/'engineer'/'delivery') != identity:
                    raise ValueError('engineering project changed during meeting')
                record(role, phase, result)
                publish('meeting')
                if role != 'manager':
                    role = 'manager'
                    continue
                decision = result.get('decision')
                if decision in ('engineer', 'researcher'):
                    role = decision
                    continue
                if decision == 'finish':
                    current = accepted_receipt()
                    if result.get('status') == 'passed' and (result.get('candidate_digest') != identity
                            or not current or current['version'] != handed_version):
                        record('runner', phase, dict(status='failed',
                               summary='Finish requires the reviewed candidate and a checklist handed to Engineer for self-testing.'))
                        break
                    final = result
                    break
                if decision != 'continue':
                    record('runner', phase, dict(status='failed',
                           summary='Manager decision must be engineer, researcher, continue or finish; continuing next round.'))
                proposed = result.get('dispatch', [])
                if (not isinstance(proposed, list) or any(
                    not isinstance(item, dict) or item.get('role') not in ROLES
                    or not isinstance(item.get('instruction'), str) for item in proposed)):
                    record('runner', phase, dict(status='failed', summary='Use dispatch [{role, instruction}]; messages remain available.'))
                    proposed = []
                tasks = {item['role']: item['instruction'] for item in proposed}
                break

    finally:
        team.cancelled.set()
        pool.shutdown(wait=True, cancel_futures=True)
    check_snapshot()
    return dict(status=final['status'] if final else 'failed',
                reason=final.get('summary', '') if final else 'task wall budget exhausted',
                manager=final, rounds=round_number,
                candidate=str(candidate) if candidate else None, digest=identity)
