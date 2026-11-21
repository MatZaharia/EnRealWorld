"""Researcher-owned graph and manager review, published at team barriers."""
import json
from pathlib import Path
from enrealworld.skills.team.researcher.scripts.scene_graph_schema import CollaborationGraph
from enrealworld.utils.files import save, digest


def submit(root, role, result, candidate_digest=None):
    root = Path(root)
    path = root/'coordination'/'scene-graph.json'
    if 'scene_graph' in result:
        if role != 'researcher':
            raise ValueError('only researcher updates scene_graph')
        graph = CollaborationGraph.model_validate(result['scene_graph'])
        old = json.loads(path.read_text()) if path.exists() else None
        if old != graph.model_dump(mode='json'):
            if graph.revision != (old['revision'] + 1 if old else 1):
                raise ValueError('graph revision must advance exactly once')
            if old and graph.scene_id != old['scene_id']:
                raise ValueError('scene identity cannot change')
            save(path.parent/'graph-history'/f'{graph.revision:04d}.json', graph.model_dump(mode='json'))
            save(path, graph.model_dump(mode='json'))
    if 'graph_review' in result:
        if role != 'manager' or not path.exists():
            raise ValueError('manager reviews an existing researcher graph')
        review = result['graph_review']
        if review.get('graph_sha256') != digest(path):
            raise ValueError('review must bind the exact graph digest')
        if not candidate_digest or review.get('candidate_digest') != candidate_digest:
            raise ValueError('review must bind the tested candidate')
        graph = CollaborationGraph.model_validate_json(path.read_text())
        targets = {e.id for e in graph.entities} | {r.id for r in graph.relations} | {c.id for e in graph.entities for c in e.requirements}
        for finding in review['findings']:
            if finding['target'] not in targets or finding['status'] not in ('verified', 'failed', 'unknown'):
                raise ValueError('unknown target or verification status')
            if not finding.get('summary'):
                raise ValueError('finding needs a summary')
            refs = finding.get('evidence_refs', [])
            if finding['status'] != 'unknown' and not refs:
                raise ValueError('verification requires actual result evidence')
            hashes = {}
            for ref in refs:
                evidence = (root/'manager'/'output'/ref).resolve()
                if not evidence.is_relative_to((root/'manager'/'output').resolve()) or not evidence.is_file():
                    raise ValueError('missing manager review evidence')
                hashes[ref] = digest(evidence)
            finding['evidence_sha256'] = hashes
        review = dict(review, reviewer='manager')
        folder = path.parent/'graph-reviews'
        folder.mkdir(exist_ok=True)
        save(folder/f'{len(list(folder.glob("*.json")))+1:04d}.json', review)
        save(path.parent/'graph-review.json', review)


def status(root, candidate_digest):
    folder = Path(root)/'coordination'
    path = folder/'scene-graph.json'
    if not path.exists():
        return dict(status='missing', owner='researcher')
    review_path = folder/'graph-review.json'
    review = json.loads(review_path.read_text()) if review_path.exists() else None
    current = bool(review and review.get('reviewer') == 'manager' and review['graph_sha256'] == digest(path) and review['candidate_digest'] == candidate_digest)
    if current:
        for finding in review['findings']:
            for ref, sha in finding.get('evidence_sha256', {}).items():
                p = Path(root)/'manager'/'output'/ref
                current = current and p.is_file() and digest(p) == sha
    return dict(owner='researcher', reviewer='manager', path='/coordination/scene-graph.json', sha256=digest(path),
                review_status='current' if current else 'unreviewed_or_stale',
                review_path='/coordination/graph-review.json' if review else None)


def engineer_view(value):
    """Remove private graph contracts from shared structured history/state."""
    if isinstance(value, dict):
        if 'scene_id' in value and 'entities' in value and 'relations' in value:
            return None
        if 'graph_sha256' in value and 'findings' in value:
            return None
        return {k: engineer_view(v) for k, v in value.items()
                if k not in ('scene_graph', 'graph_review', 'graph_error')}
    if isinstance(value, list):
        return [engineer_view(item) for item in value]
    return value


def private_graph_file(path):
    """Graph artifacts stay with manager/researcher, including renamed JSON copies."""
    path = Path(path)
    if path.name in ('scene-graph.json', 'graph-review.json'):
        return True
    if path.suffix == '.json':
        try:
            value = json.loads(path.read_text())
        except (ValueError, UnicodeError):
            return False
        return engineer_view(value) != value
    return False
