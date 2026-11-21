---
name: enrealworld-manager
description: EnRealWorld requirements, verification and delivery management
---

Read the original inputs and maintain `/role/checklist.md` as ordinary Markdown.
Follow the [workflow](references/protocol.md) before submission and during review.

Submit from a Manager work phase:

```sh
python /manager-tools/checklist_tool.py --checklist /role/checklist.md submit
```

The runner snapshots the file at phase end.
Next phase, check the receipt with `python /manager-tools/checklist_tool.py receipt --request-id ID` and correct any rejection.
The stored snapshot is available at `/coordination/requirement-checklist.md`.
