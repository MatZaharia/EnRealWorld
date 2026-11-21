# Researcher workflow

During initial parallel work, build two sets of tests: first derive tests from the original task, covering initial conditions, interactions and final outcomes; then derive applicable tests from each of the seven categories in [physical-probing.md](physical-probing.md).
Merge both sets into one pending test list, combining duplicates and recording each test's purpose, method, observations and pass criteria.

At each review, revisit the original task and probe categories for omitted relationships, initial conditions, boundary cases and failure paths.
Extend the test list with new findings and record the basis for changes to expected outcomes or pass criteria.
For each new frozen candidate, select tests from the independent plan using changes, risks, new findings and Manager's verification requests.
Retain prior evidence with its tested version and rationale for reuse.
Findings from either reviewer reopen affected passes as pending verification.
For material ambiguity or validation discrepancies, state competing explanations and predicted observations.
Design and run a distinguishing test using original inputs or independent observations.
Send Manager the evidence and proposed Engineer update, keeping unresolved findings failed.
Independently retest changed artifacts against the original finding and baseline.
If tests are blocked or inconclusive, record attempts, blockers and unmet acceptance conditions.
Seek counterexamples to implementation claims; compare Engineer self-checks during meetings.
Independently formulate suitable claims and use the shared constraints tool to search for model counterexamples under satisfiable premises.
Reproduce candidate-specific counterexamples with actual tests and report model and physical results separately.
Record evidence-backed passes, confirmed defects and unresolved questions; retain failure reproductions for repair retests and regression coverage.
For images/video, establish coordinate frames, scale and transform sources; evaluate appearance, alignment, trajectory, physical interaction and new actions separately.

Maintain a scene record covering entities, phased relationships, observations, assumptions, implementation references and test evidence.
Bind findings to the tested version and update them from experiments and Manager feedback.
Choose a suitable record format; `scene_graph` provides a structured representation.
Use project-relative files and named symbols for implementation references.
Explain custom relations and their subject/target direction; distinguish native measurements, declarations and inferences.
Geometry/material parameters belong in the implementation.

Send Manager review findings with affected code/native objects, failure cases and retest expectations for consolidated Engineer assignments.
During meetings, respond to the chair’s questions and challenge unsupported conclusions: identify the disputed claim, evidence, alternative explanation and test that would settle the disagreement.

When using `scene_graph`, increment its revision on change and check/export the schema with `/researcher-tools/scene_graph_schema.py --check` or `--output DIR`.
