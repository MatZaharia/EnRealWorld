# Shared constraints

Use Z3 for disputed Boolean or numeric conditions.
Install `.[constraints]` in the role runtime; run scripts with `PYTHONPATH=/constraint-tools`.

Keep definitions in trusted `/role/*.py` files, referenced as `path.py::symbol`.
Record meaning, sources, object IDs, definition version, units and scope.
Encode applicability in the premises (`applies_when` is descriptive).
Reuse symbols for identical quantities; distinguish objects, frames and phases.

Define `/role/height.py`:

```python
from z3 import And, Real, RealVal
from constraints import Proposition
h = Real('height_m')
reachable = Proposition('terminal height is between 0 and 0.08 m',
    'in the measured configuration', ('observation:measurement.json',), ('jar',), '1',
    And(h >= 0, h <= RealVal('0.08')))
required = Proposition('terminal height is at least 0.10 m',
    'at the task endpoint', ('requirement:input/task.md#height',), ('jar',), '1',
    h >= RealVal('0.10'))
```

Check from `/role/check_height.py`:

```python
from constraints import candidate_digest_from, check_consistency, find_counterexample, save_evidence
base = '/role/height.py::reachable'
goal = '/role/height.py::required'
digest = candidate_digest_from('/candidate-binding.json')
save_evidence(check_consistency([base, goal], candidate_digest=digest), '/role/evidence/conflict.json')
save_evidence(find_counterexample([base], goal, candidate_digest=digest), '/role/evidence/counterexample.json')
```

Run `PYTHONPATH=/constraint-tools python /role/check_height.py`.
Use the current candidate binding; omit `candidate_digest` before a candidate exists.
`timeout_ms` defaults to 5000 per solver check.
`load_proposition(ref)` reads a definition.

| Result | Consistency | Counterexample search |
|---|---|---|
| `sat` | Conditions can coexist | Model counterexample; reproduce in actual tests |
| `unsat` | Conditions conflict | No counterexample within encoded premises |
| `inconsistent_premises` | — | Revise contradictory premises |
| `unknown` / `error` | Unresolved; inspect reason | Unresolved; inspect reason |

Results record definitions, hashes, solver inputs, candidate digest and outcome.
Save each run to a fresh evidence path.
Acceptance requires actual test evidence.

Messages cite the proposition, candidate version, change and evidence path.
Share needed definitions, helpers and results as attachments.
Load files through message `attachment_paths`; `/coordination/attachments.json` indexes historical snapshots by sender, receipt and candidate.
Snapshots retain the original relative directory layout.
Manager includes public conditions and object/code locations in repair messages; private definitions stay private.
A bare private ID is insufficient for a handoff.
Engineer can use the same constraint tools for public definitions.
After repairs, rerun affected constraints and reproduce the relevant actual tests.
