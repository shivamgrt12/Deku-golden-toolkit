# Installing the golden toolkit

The toolkit is a git repo cloned **into** a `deku-task-kit` checkout as `golden/`. It adds files
and changes none of the kit's own.

## Needs

| What | Why |
|---|---|
| `deku-task-kit` at commit `69f5952` or later, harness submodule at `a280909` | golden imports the harness and builds its verifier image |
| `./scripts/setup.sh` already run (the harness `.venv` exists) | golden runs on the harness's Python 3.14 |
| Docker Desktop, running | every gauntlet stage runs in containers |
| The `claude` CLI logged in with a Claude Max account | the graders run through the OAuth bridge; no API key |
| Cursor, Claude Code, OpenCode or Kiro | the agent that builds the app |
| Optional: `ffmpeg` (`brew install ffmpeg`) | only for a brief that needs rendered video |
| Optional: `prd-generator` checked out beside `deku-task-kit` (or `DEKU_PRDGEN_DIR`) | only for `golden-init --site` |

## Install

```bash
cd /path/to/deku-task-kit
git clone https://github.com/shivamgrt12/Deku-golden-toolkit.git golden
golden/bin/golden-install            # editor commands, .gitignore entries, pinned skills
golden/bin/golden-bridge start       # graders on your Claude login
golden/bin/gauntlet --self-test      # must print "N passed"
```

`golden-install` puts the `/golden` command in place for all four editors:

- `.claude/commands/golden.md` (Claude Code)
- `.cursor/commands/golden.md` and `.cursor/rules/golden.mdc` (Cursor)
- `.opencode/command/golden.md` (OpenCode)
- `.kiro/prompts/golden.md` (Kiro)

It also adds `/golden/` and the synced skill copies to the kit's `.gitignore`, so the kit's own
git never picks up the toolkit.

## Update

```bash
cd /path/to/deku-task-kit/golden && git pull && bin/golden-install
```

## Use

Open the kit folder in your editor and run `/golden <absolute path to the bundle>`, or tell the
agent *"follow golden/RUN.md for `<bundle>`"*. Check where things stand at any time with
`golden/bin/golden-status <bundle>`. `golden/README.md` has the full flow and the two points
where you approve.

## When something goes wrong

- **"bridge is not running or not healthy":** run `golden/bin/golden-bridge start`. It restarts an
  unhealthy bridge, usually after your login token has rotated.
- **`git clone` says `golden` already exists:** an older zip copy is there. `mv golden golden-old`,
  clone again, then delete `golden-old`.
- **A stage fails on something that looks like a toolkit rule rather than an app defect:** stop
  and report it with the stage's output. Never patch `golden/` from inside a bundle run.
