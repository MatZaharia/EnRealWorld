# Update the role's experience library

Read this role's current artifacts and use records through `current/manifest.json`. If `previous/` exists, read its `experience.md` and relevant files alongside the current evidence.

Edit `output/`, initially copied from the previous library. Retain useful entries, add evidence, correct claims, merge duplicates and remove superseded files. Entry count is unrestricted, including zero.

- **Engineer → Construct Tools.** Keep reusable code, entry points, dependencies and parameters to replace.
- **Researcher → Runtime Cases.** Keep preconditions, interventions, expected outcomes, observations, counterexamples and available scripts.
- **Manager → Manage Memory.** Keep decision rules, applicability, supporting evidence and unresolved conditions.

Produce a complete `output/experience.md` with supporting files and `output/changes.md` explaining the updates or why no change was needed. Use library-relative links, include required local helpers, document external dependencies, and cite evidence by original run and artifact path. The next run receives only this published library.

Treat `current/` and `previous/` as read-only. Use internal task evidence; exclude external evaluation scores, official evaluation feedback and private labels.

## Commands

From the checkout:

```sh
PYTHONPATH=src python -m enrealworld.utils.evolve.experience extract RUN RAW
PYTHONPATH=src python -m enrealworld.utils.evolve.update prepare RAW WORK --previous LIBRARY_V1
# First round: omit --previous.
# Each role's agent reads WORK/ROLE/{current,previous} and edits WORK/ROLE/output.
PYTHONPATH=src python -m enrealworld.utils.evolve.update publish WORK LIBRARY_V2
PYTHONPATH=src python -m enrealworld.utils.evolve.experience read LIBRARY_V2 --role engineer
```

The caller invokes the agents, publishes to a fresh directory, then supplies only `LIBRARY_V2/ROLE` to each role in the next run.
