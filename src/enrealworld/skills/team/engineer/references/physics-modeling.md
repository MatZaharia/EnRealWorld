# Physical diagnosis

Use the failure evidence to select relevant checks below.
Track affected entities through native body/joint/geom mappings and distinguish measured parameters, estimates and unknowns.

## Model and coordinates

Choose a model that expresses the behavior: rigid contact for hard objects, articulated links for hinges/sliders, deformable models for folding or stretching, and fluid or granular solvers for flow.
Confirm the backend supports the required behavior and converts the relevant parameters.

Use SI units: m, kg, s, N, N m, rad.
Specify world up/handedness, quaternion order, mesh scale and frame transforms.
Convert at input boundaries.
Metric scale and mass need measurement or explicit assumptions when inferred from images.

## Geometry and mass

Inspect native collision shapes, local transforms, gaps and initial penetration.
Check that mesh cooking preserves openings and handles; moving concave bodies may need convex decomposition.
Resolve thin supports with suitable geometry and timesteps.
Verify fixed/free state, center of mass and positive inertia in the correct frame.
Estimate mass from measurement or density × volume, with uncertainty.
At fixed density, scaling lengths by s scales mass by s³ and inertia by s⁵.

## Contact and joints

Read back friction, contact filtering, pair identity, normals, penetration and impulses.
Free sliding under Coulomb assumptions gives approximate deceleration μg.
Use the backend's native compliance/restitution mapping and identify unavailable values.

For joints, inspect parent/child frames, anchor, axis, limits (rad or m), damping, effort limits and initial state.
Distinguish fixed attachments, motor holding and frictional grasp.
Diagnose grasp failures through actual gripper closure, contact, lift and hold using the robot controller.

## Numerical sensitivity

Check geometry, units and constraints before tuning solver iterations.
Choose step size against speed, collider size, stiffness and joint stability.
If numerical error is suspected, compare dt and dt/2 on the same case.
Test plausible parameter ranges tied to observations and report sensitivity across runs.
