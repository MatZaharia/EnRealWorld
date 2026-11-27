# Local team configurations

Each template runs Manager, Engineer and Researcher in separate native CLI sessions on the included studio painting. From the repository root, activate the Python environment containing EnRealWorld and put Blender and the provider CLI on PATH.

| Template | Provider setup |
| --- | --- |
| [Codex](codex_local.json) | Install `codex`. Set the absolute paths to your native login and config files, and select a model your account can use. Each role receives its own Codex home. |
| [Claude Code](claude_local.json) | Install and sign in to `claude`. The template uses the CLI's default model and `acceptEdits` mode. |
| [Antigravity](antigravity_local.json) | Install and sign in to `agy`. The template uses its default model and local permission settings. |

Set `root` to a new output directory for each run. Set `public` to an existing input directory outside that output tree. Both paths resolve from the directory where you launch the runner. Edit `task` with the deliverable and input filenames, and `wall_seconds` with the budget for the whole run.

The adapter runs from each role's working directory. Use an absolute Python path in `agent.command[0]` if the active environment is unavailable on PATH. Configure the native CLI for unattended simulator commands and writes to the role output and session directories. Keep run directories private, as they can contain native session credentials.

```sh
enrealworld examples/configs/codex_local.json
```

Open `result.json` under `root` to inspect the delivery status and candidate path.
