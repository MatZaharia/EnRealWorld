---
name: enrealworld
description: Run the EnRealWorld team to build, independently test and deliver interactive worlds from task inputs.
---

# EnRealWorld

The main session prepares and follows the run, then reports the delivery.
The runner manages three independent Native Agent Sessions and their handoffs:

- [Manager](../team/manager/SKILL.md): requirements, review and delivery decisions.
- [Engineer](../team/engineer/SKILL.md): implementation, development tests and repairs.
- [Researcher](../team/researcher/SKILL.md): independent tests, execution evidence and feedback.

## Prepare and launch

Read the original task and gather its inputs, assets, target backend and delivery requirements.
Put the task text and file references in `task`, input files in `public`, and an existing project in optional `seed_output`.

Prepare a JSON configuration using [runner.py](../../team/runner.py) for required fields and supported options.
Select local or Docker execution and configure the agent adapter, authentication and backend availability.
Before launching, the main session prepares the environment and assets independently of the generation team:

- Stage the task’s authorized inputs and required assets, downloading missing assets as needed. Provide the team with their locations and usage instructions.
- Install required tools and runtime dependencies, and configure the backend, asset paths and resource settings. Run the required backend in the generation environment to confirm it works and can access the required assets before launching the team.
- Handle environment and asset issues that arise during generation; the team remains responsible for implementation issues. Record setup details and unresolved blockers. Keep repairs within the authorized scope and any declared experiment conditions; report required changes to access or those conditions before proceeding.

Install the package from the repository with `python -m pip install .`, then run:

```sh
enrealworld /absolute/path/to/config.json
```

`python -m enrealworld.team` accepts the same configuration path.

The runner coordinates parallel work and checklist submission, then hands the accepted checklist to Engineer for self-testing after generation.
It freezes the resulting candidate for independent Researcher review, repair and retest, followed by Manager review and meetings.
Follow progress in `root/coordination/` while it runs.

## Report the result

Read `root/result.json` for status, candidate and session receipts.
Delivery status is `passed` when the delivered candidate has final acceptance, `incomplete` when a project is available with unresolved acceptance, and `failed` when no project is available.
Review reasons and individual test results separately.
Candidate projects are in `root/candidates/`; role reports and test evidence are in `root/<role>/output/`, with shared discussion under `root/coordination/`.
