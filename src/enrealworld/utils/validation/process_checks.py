"""Offline process criteria over native samples; no synchronized relation graph."""
from typing import Literal
import numpy as np
import math
from pydantic import Field
from enrealworld.validation_model import Model, Positive, NonNegative


class RelationProcess(Model):
    type: Literal['relation_process'] = 'relation_process'
    entity: str
    target: str
    relation_kind: Literal['contact','support']
    expected: Literal['present','absent'] = 'present'
    phase: str | None = None
    min_duration_s: Positive
    max_dropout_s: NonNegative = 0
    separation_m: NonNegative = .001
    max_penetration_m: NonNegative = .003
    min_weight_fraction: Positive = .1
    max_relative_speed_m_s: NonNegative = .03
    max_relative_angular_speed_rad_s: NonNegative = .3
    contact_height_tolerance_m: NonNegative = .002
    source_ref: str = Field(min_length=1)
    id: str | None = None


def evaluate_relation(spec, rows, contacts, native, session):
    c=RelationProcess.model_validate(spec);dt=1/session['physics_hz']
    if c.entity==c.target:raise ValueError('distinct relation endpoints required')
    if not session.get('contact_recording_complete'):return dict(outcome='not_calculated',reason='contact completeness unavailable')
    g=np.asarray(session.get('environment',{}).get('gravity_m_s2',[]),float)
    support=c.relation_kind=='support'
    capabilities=session.get('observation_capabilities',{})
    if capabilities.get('contacts') is False or support and any(capabilities.get(k) is False for k in ('forces','velocities')):
        return dict(outcome='not_calculated',reason='required native observation channel unavailable')
    if support and (g.shape!=(3,) or not np.isfinite(g).all() or np.linalg.norm(g)==0):
        return dict(outcome='not_calculated',reason='support criterion requires nonzero observed gravity')
    up=-g/np.linalg.norm(g) if support else None
    by_time={}
    for index,contact in enumerate(contacts):
        by_time.setdefault(contact['time_s'],[]).append((index,contact))
    samples=[]
    for index,row in enumerate(rows):
        if c.phase is not None and row.get('phase')!=c.phase:continue
        objects={o['name']:o for o in row['objects']};a,b=objects.get(c.entity),objects.get(c.target)
        selected=[(i,v) for i,v in by_time.get(row['time_s'],[]) if {v['body0'],v['body1']}=={c.entity,c.target}]
        measured=None;reason=None
        if a is None or b is None:reason='missing entity observation'
        else:
            matching=[(i,v) for i,v in selected if -c.max_penetration_m<=v['separation_m']<=c.separation_m]
            if any(not math.isfinite(v['separation_m']) for _,v in selected):reason='nonfinite contact separation'
            elif not support:measured=any(v['separation_m']<=c.separation_m for _,v in selected)
            elif c.entity not in native or not math.isfinite(native[c.entity].get('mass_kg',0)) or native[c.entity].get('mass_kg',0)<=0:reason='native mass unavailable'
            elif not matching:measured=False
            elif any('force_on_body1_world_N' not in v for _,v in matching) or 'center_of_mass_world_m' not in a:
                reason='support force/COM observations unavailable'
            else:
                load=0.
                center=np.asarray(a['center_of_mass_world_m'],float)
                if center.shape!=(3,) or not np.isfinite(center).all():reason='nonfinite COM observation'
                for _,v in matching:
                    force=np.asarray(v['force_on_body1_world_N'],float)*(1 if v['body1']==c.entity else -1)
                    point=np.asarray(v['position_m'],float)
                    if force.shape!=(3,) or point.shape!=(3,) or not np.isfinite(force).all() or not np.isfinite(point).all():
                        reason='nonfinite contact observation';break
                    if np.dot(point-np.asarray(a['center_of_mass_world_m']),up)<=c.contact_height_tolerance_m:
                        load+=max(0.,float(np.dot(force,up)))
                if reason is None:
                    try:
                        vectors=[np.asarray(o[k],float) for o in (a,b) for k in ('linear_velocity_m_s','angular_velocity_rad_s')]
                        if any(v.shape!=(3,) or not np.isfinite(v).all() for v in vectors):raise ValueError('nonfinite or malformed velocity')
                        speed=float(np.linalg.norm(vectors[0]-vectors[2]))
                        spin=float(np.linalg.norm(vectors[1]-vectors[3]))
                        measured=bool(load>=native[c.entity]['mass_kg']*np.linalg.norm(g)*c.min_weight_fraction and speed<=c.max_relative_speed_m_s and spin<=c.max_relative_angular_speed_rad_s)
                    except (KeyError,ValueError):reason='velocity observation unavailable or invalid'
        desired=None if measured is None else measured if c.expected=='present' else not measured
        samples.append(dict(sample_index=index,time_s=row['time_s'],matches=desired,reason=reason,contact_indices=[i for i,_ in selected]))
    # Unknown observations and sampling gaps always break a confirmation window.
    # Short *observed negative* dropouts may be tolerated; they are not counted
    # as confirmed support duration and cannot bridge missing evidence.
    longest=0.;duration=0.;dropout=0.;previous=None;unknown=False;had_positive=False
    for sample in samples:
        t=sample['time_s'];interval=0. if previous is None else t-previous
        if previous is not None and (interval<=0 or interval>dt*1.5):duration=0.;dropout=0.;had_positive=False;unknown=True
        if sample['matches'] is None:
            duration=0.;dropout=0.;had_positive=False;unknown=True
        elif sample['matches']:
            if had_positive:duration+=max(0.,interval-dropout)
            else:duration=0.
            had_positive=True;dropout=0.;longest=max(longest,duration)
        else:
            dropout+=interval
            if dropout>c.max_dropout_s+1e-12:duration=0.;had_positive=False;dropout=0.
        previous=t
    passed=longest+1e-12>=c.min_duration_s
    outcome='pass' if passed else 'not_calculated' if unknown or not samples else 'fail'
    return dict(outcome=outcome,reason=None if passed else 'insufficient confirmed duration' if outcome=='fail' else 'missing or incomplete observations',
                value=dict(longest_confirmed_s=longest,required_s=c.min_duration_s,sample_interval_s=dt,samples=samples),
                limits='sampled evidence only; tolerated observed dropouts do not count as confirmed duration; contact alone does not prove support')
