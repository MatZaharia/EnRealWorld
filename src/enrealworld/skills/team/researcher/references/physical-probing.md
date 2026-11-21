# Physical probing

Test a physical claim with a predicted response and a comparison experiment.
Select interventions from the task, scene relationships and observed failures.

| Claim | Intervention and observation |
|---|---|
| Gravity/free motion | Change gravity or release an object; measure trajectory changes. |
| Force response | Apply force, torque or impulse; measure motion and decay after removal. |
| Collision | Add/move a barrier and compare enabled/disabled collision; inspect deflection and penetration. |
| Support | Move, tilt or remove support; inspect falling, sliding and load-bearing contact. |
| Grasp | Move/disturb a held object, then release; inspect slip and separation. |
| Constraints | Load connected parts, exercise joint limits or release a connection. |
| Materials | Stretch, compress, bend, unload or pour; inspect recovery and containment. |

## Execute

Identify the project's engine, entry, controller and entity-to-native-object mappings.
Reuse its tools or add an experiment-local script using the engine API.
Ask Engineer for missing entry/mapping information.

Run on a diagnostic copy with matched initial conditions, configuration and seed.
Vary one factor where possible; explain combined interventions.
Rebuild if reset retains controller, random or material state.
Repeat trials when variation matters.
Record intervention timing and parameters: vector/frame, application point, duration, collision settings or released connection.
Inspect relevant controller writes, active constraints and simulation caches.

## Judge and report

Use matched cameras, scale and simulation times for visual comparisons.
Capture motion with clips/frame sequences and a frame-to-time mapping.
Use numerical checks for quantitative claims, recording units, frames, sampling and threshold sources.
Distinguish contact force from impulse and native readback from declarations.

Resolve competing explanations with targeted state inspection or another experiment: removing support distinguishes resting from fixed objects; known forces help estimate mass.
Mark missing observations and remaining reset/sampling limits explicitly.

Report the intervention, observation, supported conclusion, unresolved explanations and next check, with affected entities/code and baseline/intervention evidence.
Keep scripts, raw observations and configuration with the experiment round under workspace reporting conventions.
Extract helpers after repeated use.
