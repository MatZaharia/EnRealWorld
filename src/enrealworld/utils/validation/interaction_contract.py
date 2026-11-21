"""Task-declared complete interaction checks over native per-step observations."""
import numpy as np


def evaluate(spec, rows, contacts, native, session):
    def unresolved(reason):
        return dict(outcome='not_calculated', reason=reason)
    required = ('robot_links', 'finger_links', 'hold_window_s', 'final_window_s',
                'minimum_lift_m', 'minimum_contact_impulse_N_s', 'maximum_penetration_m',
                'maximum_linear_speed_m_s', 'maximum_angular_speed_rad_s',
                'maximum_final_drift_m', 'allowed_contact_pairs', 'source_ref', 'entity')
    if any(k not in spec for k in required):
        return unresolved('complete interaction contract missing fields')
    try:
        links, fingers = set(spec['robot_links']), set(spec['finger_links'])
        if not links or len(fingers)<2 or not fingers<=links:
            return unresolved('full robot and finger inventory required')
        if not session.get('contact_recording_complete'):
            return unresolved('complete per-step contact recording required')
        hz=session['physics_hz']; t=np.array([r['time_s'] for r in rows])
        if len(t)<2 or not np.allclose(np.diff(t),1/hz,rtol=0,atol=1e-9):
            return unresolved('complete per-step states required')
        # Inventory must agree with actual native observations, not only selected fingers.
        if any(set(r.get('robot_links',{})) != links for r in rows):
            return unresolved('robot link observation inventory differs from contract')
        target=spec['entity']
        if native[target].get('motion_mode')!='dynamic':
            return unresolved('independent dynamic target required')
        obj=[next(o for o in r['objects'] if o['name']==target) for r in rows]
        p=np.array([o['pose'][:3] for o in obj]); v=np.array([o['linear_velocity_m_s'] for o in obj]); w=np.array([o['angular_velocity_rad_s'] for o in obj])
        if not all(np.isfinite(x).all() for x in (p,v,w,t)):
            return unresolved('nonfinite state')
        masks=[]
        for key in ('hold_window_s','final_window_s'):
            start,end=spec[key]
            if not np.isfinite([start,end]).all() or end<=start or start<t[0] or end>t[-1]:
                return unresolved('requested observation window not covered')
            mask=(t>=start)&(t<=end)
            if mask.sum()<2:return unresolved('window has insufficient samples')
            masks.append(mask)
        thresholds=required[4:10]
        if any(not np.isfinite(spec[k]) or spec[k]<0 for k in thresholds):
            return unresolved('finite nonnegative task thresholds required')
        allowed={frozenset(pair) for pair in spec['allowed_contact_pairs']}
        by_step={}; bad=[]; depth=0.
        for c in contacts:
            pair={c['body0'],c['body1']}
            if pair & links:
                d=max(0.,-c['separation_m']);depth=max(depth,d)
                if frozenset(pair) not in allowed:bad.append(c)
            if target in pair and np.linalg.norm(c['impulse_N_s'])>=spec['minimum_contact_impulse_N_s']:
                by_step.setdefault(round(c['time_s']*hz),set()).update(pair & fingers)
        hold,final=masks
        held=all(fingers<=by_step.get(round(tm*hz),set()) for tm in t[hold])
        # Native positions and gravity are in the same declared session frame.
        gravity=np.asarray(session.get('environment',{}).get('gravity_m_s2'),dtype=float)
        if gravity.shape!=(3,) or not np.isfinite(gravity).all() or np.linalg.norm(gravity)<1e-12:
            return unresolved('nonzero declared session gravity required for lift')
        up=-gravity/np.linalg.norm(gravity)
        lifted=bool(np.all((p[hold]-p[0])@up>=spec['minimum_lift_m']))
        stable=bool(np.max(np.linalg.norm(v[final],axis=1))<=spec['maximum_linear_speed_m_s'] and
                    np.max(np.linalg.norm(w[final],axis=1))<=spec['maximum_angular_speed_rad_s'] and
                    np.max(np.linalg.norm(p[final]-p[final][0],axis=1))<=spec['maximum_final_drift_m'])
        values=dict(full_body_contact_envelope=depth<=spec['maximum_penetration_m'],
                    allowed_contacts_only=not bad,sustained_hold=held,sustained_lift=lifted,final_stability=stable)
        return dict(outcome='pass' if all(values.values()) else 'fail',value=values,
                    limits='sampled native contacts and states; no continuous surface intersection or target-environment equivalence claim')
    except (KeyError,ValueError,TypeError,StopIteration):
        return unresolved('missing or malformed contract/native observation')
