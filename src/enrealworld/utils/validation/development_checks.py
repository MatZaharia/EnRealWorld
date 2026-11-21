"""Public, task-declared development checks; no benchmark constants or GT."""
import numpy as np


def evaluate(spec, rows, contacts, native, session):
    kind = spec.get('type', 'complete_interaction')
    if kind == 'complete_interaction':
        from .interaction_contract import evaluate as interaction
        return interaction(spec, rows, contacts, native, session)
    if kind == 'relation_process':
        from .process_checks import evaluate_relation
        return evaluate_relation(spec, rows, contacts, native, session)
    try:
        if not spec.get('source_ref'):
            raise ValueError('public source_ref required')
        if kind == 'gravity_alignment':
            # observed_up is expressed in the declared observation frame.
            # Rotation maps session vectors to that frame; translation is irrelevant.
            rotation = np.asarray(spec['session_to_observation_rotation'], float)
            up = np.asarray(spec['observed_up'], float)
            gravity = np.asarray(session['environment']['gravity_m_s2'], float)
            tolerance = float(spec['maximum_angle_rad'])
            if (rotation.shape != (3,3) or up.shape != (3,) or gravity.shape != (3,)
                or not np.isfinite(rotation).all() or not np.isfinite(up).all() or not np.isfinite(gravity).all()
                or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-6)
                or not np.isclose(np.linalg.det(rotation),1) or np.linalg.norm(up)==0
                or np.linalg.norm(gravity)==0 or not 0 <= tolerance < np.pi):
                raise ValueError('finite proper rotation, nonzero vectors and angle tolerance required')
            predicted = -rotation@gravity/np.linalg.norm(gravity)
            angle = float(np.arccos(np.clip(predicted@up/np.linalg.norm(up),-1,1)))
            return dict(outcome='pass' if angle<=tolerance else 'fail', angle_rad=angle)
        if kind == 'initial_contact_envelope':
            if not session.get('contact_recording_complete') or not rows:
                raise ValueError('native initial state and complete contacts required')
            links = set(spec['links']); limit = float(spec['maximum_penetration_m'])
            if not links or not np.isfinite(limit) or limit < 0:
                raise ValueError('links and finite nonnegative penetration limit required')
            observed = set(rows[0].get('robot_links', {})) | {o['name'] for o in rows[0]['objects']}
            if not links <= observed: raise ValueError('declared links absent from initial observations')
            depth = max([0.] + [-float(c['separation_m']) for c in contacts
                         if c['time_s']==rows[0]['time_s'] and {c['body0'],c['body1']} & links])
            return dict(outcome='pass' if depth<=limit else 'fail', penetration_m=depth,
                        limits='sampled initial native contacts, not continuous geometry certification')
        raise ValueError('unsupported development check: '+str(kind))
    except (KeyError, ValueError, TypeError) as exc:
        return dict(outcome='not_calculated', reason=str(exc))
