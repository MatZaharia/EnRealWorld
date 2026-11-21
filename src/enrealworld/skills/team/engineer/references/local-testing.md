# Development self-tests and repair

Before implementation or changes, derive expected outcomes from the task and original inputs; write tests covering relevant normal, boundary and failure cases.
Run them to establish failures, implement until they pass, then refactor and rerun affected tests.
For repairs, add a failing reproduction first.
Keep expected values grounded in requirements and independent observations.
Deliver commands, version-bound evidence and remaining gaps for independent Researcher testing.
Keep self-test scripts and reports under /role; include execution instructions and dependencies in the deliverable.

For collision geometry, initial placement or motion changes, check initial overlap and clearance, collision/contact along the motion, and affected task behavior.
Choose Trimesh, Open3D or native engine tools to match the geometry and runtime.

## Diagnose failures

Record the problem reference and symptom.
Bind reproduction to the build/config, initial state, controller, backend version, actions and failure time.

Choose a small experiment that distinguishes plausible causes: wait to isolate support instability, apply force then coast to examine sliding, or apply joint effort to inspect axis and limits.
Preserve relevant contacts, constraints and actuation.
Use experimental results, including Researcher findings, to update the implicated component and rerun the original and affected checks.
Retain baseline and failed runs.
Hand off the changed artifact and before/after evidence for independent retesting.
Keep blocked or inconclusive findings unresolved.

## Python geometry tools

Prepare the agent's Python environment from the repository root with `python -m pip install -e '.[geometry]'`.
Use these libraries as needed:

- [Trimesh proximity](https://trimesh.org/trimesh.proximity.html): closest surface points and signed distances.
- [Open3D RaycastingScene](https://www.open3d.org/docs/latest/tutorial/geometry/ray_casting.html): ray hits, [distances and occupancy](https://www.open3d.org/docs/latest/tutorial/geometry/distance_queries.html).

Use collision geometry in a shared frame and scale; query bodies separately.
Inside/outside queries require closed, consistently oriented meshes; inside distances are positive in Trimesh and negative in Open3D.
Check surface intersections and containment, accounting for vertex-only and sampling gaps; verify with native contacts.

## Probe script

```bash
python /engineer-tools/probe_physics.py --build /workspace/output/BUILD --problem "R0001: object falls through support; inspect collision hypothesis" --actions /workspace/output/actions.json --output /role/probe-001
```

The script loads an existing build containing build.json, backend-config.json and native backend resources.
Use a fresh output directory for each run.
Actions use the existing Session API:

```json
[{"type":"wait","duration_s":0.2},
 {"type":"force","entity":"object","force_N":[1,0,0],"duration_s":0.1},
 {"type":"wait","duration_s":0.2}]
```

MuJoCo hinge/slider probes support `joint_effort` with `relation`, `effort` and `duration_s`; effort units are N m for hinges and N for sliders.
Durations must be integer multiples of the timestep.
Ending a probe force leaves constraints intact.
`joint_target` uses the selected adapter's native action format where supported.
For grasp/lift and other controller-dependent behavior, use the delivered controller's test entry.

Outputs include per-step native states, contacts and operations; session binding; and probe.json with problem context, input hashes, adapter identity and first/middle/last state snapshots.
Unsupported actions, missing engines and incompatible builds return a reason and nonzero exit code; partial output remains available for diagnosis.

## Capability discovery and development checks

`enrealworld.utils.backends.dispatch.discover(backend, config, build)` probes selected adapter actions and dependencies.
For supplied code, trace its documented entry and dispatch before choosing a backend.
See `examples/robot_adapter` for URDF-based construction and unreachable-target repair.

Transform targets and TCP offsets into the configured control frame.
Native tool poses use xyz + unit wxyz.
Select checks from the task: initial contacts, IK, closure and holding for grasping; appropriate relations for other interactions.

Pass `--checks task-interaction.json` to the physics probe for task-derived development checks.
Missing observations produce incomplete results.
Evidence binds the candidate and check specification; rerun after relevant changes.
Saved-state replay supplies visualization, not physical test evidence.

Additional development checks:
- `gravity_alignment`: `source_ref`, `session_to_observation_rotation`, `observed_up`, `maximum_angle_rad`; checks direction in the observation frame.
- `initial_contact_envelope`: `source_ref`, `links`, `maximum_penetration_m`.
- `relation_process`: the existing contact/support process schema.
