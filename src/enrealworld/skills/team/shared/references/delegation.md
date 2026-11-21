# Delegation

Delegate independent work in parallel when supported.
Choose the number of subagents to fit the task and resources; otherwise complete the work yourself.

Specify each subtask's goal, inputs, constraints, interfaces and expected checks.
Use separate output directories under `/role/subtasks/<task>` and include the candidate digest when applicable.
Subagents inherit the parent's access boundaries and must not modify the frozen candidate, Manager's checklist, other roles' files or `/role/result.json`.

The parent verifies and integrates results, records outputs and unresolved issues, and stops unfinished subagents before returning.
Report any unconfirmed results or cleanup.
