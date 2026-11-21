"""Named Python propositions and small, version-bound Z3 checks.

Definition files are Python code and must come from a trusted source.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    import z3
except ImportError:
    z3 = None


@dataclass(frozen=True)
class Proposition:
    description: str
    applies_when: str
    source_refs: tuple[str, ...]
    object_refs: tuple[str, ...]
    version: str
    expression: object


@dataclass(frozen=True)
class LoadedProposition:
    ref: str
    source_sha256: str
    proposition: Proposition


def _load_refs(refs):
    if z3 is None:
        raise RuntimeError('install the optional z3-solver dependency in this runtime')
    files, loaded = {}, []
    for ref in refs:
        if not isinstance(ref, str):
            raise ValueError('proposition reference must be path.py::symbol')
        filename, separator, name = ref.rpartition('::')
        if not separator or not filename or not name.isidentifier():
            raise ValueError('proposition reference must be path.py::symbol')
        path = Path(filename).resolve(strict=True)
        if path not in files:
            source = path.read_bytes()
            namespace = {'__name__': '__constraint_definition__', '__file__': str(path)}
            # Allow a definition to import neighboring Python files. The executed
            # expression is recorded too, so the evidence reflects the actual input.
            sys.path.insert(0, str(path.parent))
            try:
                exec(compile(source, str(path), 'exec'), namespace)
            finally:
                del sys.path[0]
            files[path] = (hashlib.sha256(source).hexdigest(), namespace)
        source_hash, namespace = files[path]
        value = namespace.get(name)
        if not isinstance(value, Proposition):
            raise ValueError(f'{ref} must name a Proposition')
        for field in ('description', 'applies_when', 'version'):
            if not isinstance(getattr(value, field), str) or not getattr(value, field).strip():
                raise ValueError(f'{ref}: {field} must be a nonempty string')
        for field in ('source_refs', 'object_refs'):
            items = getattr(value, field)
            if not isinstance(items, (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in items):
                raise ValueError(f'{ref}: {field} must be a list of nonempty references')
        if not value.source_refs:
            raise ValueError(f'{ref}: at least one source reference is required')
        if not z3.is_bool(value.expression):
            raise ValueError(f'{ref}: expression must be a Z3 Boolean expression')
        loaded.append(LoadedProposition(ref, source_hash, value))
    return loaded


def load_proposition(ref):
    """Read one named definition; checks accept the same path.py::symbol reference."""
    return _load_refs([ref])[0]


def candidate_digest_from(binding_path):
    """Read the existing runner's candidate-binding.json."""
    digest = json.loads(Path(binding_path).read_text())['digest']
    _validate_digest(digest)
    return digest


def _validate_digest(digest):
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('candidate_digest must be a SHA-256 digest from the candidate binding')


def _inputs(refs, allow_empty=False):
    if not isinstance(refs, (list, tuple)) or (not refs and not allow_empty):
        raise ValueError('provide a list of proposition references')
    return list(refs)


def _result(kind, refs, candidate_digest, timeout_ms):
    return {'kind': kind, 'scope': 'encoded_model',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'candidate_digest': candidate_digest, 'timeout_ms': timeout_ms,
            'solver_version': z3.get_full_version() if z3 is not None else None,
            'requested': refs, 'propositions': [], 'checks': {}, 'status': 'error'}


def _validate_context(candidate_digest, timeout_ms):
    if candidate_digest is not None:
        _validate_digest(candidate_digest)
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise ValueError('timeout_ms must be a positive integer')


def _describe(items):
    return [dict(ref=item.ref, source_sha256=item.source_sha256,
                 description=item.proposition.description,
                 applies_when=item.proposition.applies_when,
                 source_refs=list(item.proposition.source_refs),
                 object_refs=list(item.proposition.object_refs),
                 version=item.proposition.version,
                 expression=item.proposition.expression.sexpr()) for item in items]


def _solver():
    return z3.Solver()


def _solve(expressions, timeout_ms):
    check = {'status': 'error'}
    try:
        solver = _solver()
        solver.set(timeout=timeout_ms)
        solver.add(*expressions)
        check['smt2'] = solver.to_smt2()
        outcome = solver.check()
        if outcome == z3.sat:
            model = solver.model()
            check.update(status='sat', model=[{'name': str(decl.name()),
                         'sort': str(decl.range()), 'value': str(model[decl])}
                         for decl in sorted(model.decls(), key=lambda d: str(d.name()))])
        elif outcome == z3.unsat:
            check['status'] = 'unsat'
        else:
            check.update(status='unknown', reason=solver.reason_unknown())
    except Exception as exc:
        check.update(status='error', reason=f'{type(exc).__name__}: {exc}')
    return check


def check_consistency(refs, *, candidate_digest=None, timeout_ms=5000):
    """Check whether the named requirements and assumptions can hold together."""
    result = _result('consistency', {'constraints': refs}, candidate_digest, timeout_ms)
    try:
        _validate_context(candidate_digest, timeout_ms)
        items = _load_refs(_inputs(refs))
        result['propositions'] = _describe(items)
        check = _solve([item.proposition.expression for item in items], timeout_ms)
        result['checks']['consistency'] = check
        result['status'] = check['status']
    except Exception as exc:
        result['reason'] = f'{type(exc).__name__}: {exc}'
    return result


def find_counterexample(premises, conclusion, *, candidate_digest=None, timeout_ms=5000):
    """Find premises AND NOT conclusion, after checking that premises are satisfiable."""
    result = _result('counterexample', {'premises': premises, 'conclusion': conclusion},
                     candidate_digest, timeout_ms)
    try:
        _validate_context(candidate_digest, timeout_ms)
        refs = _inputs(premises, allow_empty=True)
        if not isinstance(conclusion, str):
            raise ValueError('conclusion must be a proposition reference')
        items = _load_refs(refs+[conclusion])
        result['propositions'] = _describe(items)
        expressions = [item.proposition.expression for item in items[:-1]]
        precheck = _solve(expressions, timeout_ms)
        result['checks']['premises'] = precheck
        if precheck['status'] == 'unsat':
            result['status'] = 'inconsistent_premises'
        elif precheck['status'] != 'sat':
            result['status'] = precheck['status']
        else:
            check = _solve(expressions+[z3.Not(items[-1].proposition.expression)], timeout_ms)
            result['checks']['counterexample'] = check
            result['status'] = check['status']
    except Exception as exc:
        result['reason'] = f'{type(exc).__name__}: {exc}'
    return result


def save_evidence(result, path):
    """Save one result without overwriting prior evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    return path
