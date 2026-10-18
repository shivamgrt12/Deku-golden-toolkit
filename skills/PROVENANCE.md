# Vendored skills — provenance

Third-party skills are prompts our agents obey, so they are pinned like code: copied at a
recorded commit, read before vendoring, and changed only by a deliberate re-vendor that updates
this file. All four upstreams are MIT; their notices are in `LICENSES/`.

| Upstream | Commit | Vendored as | Left out, and why |
|---|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | `bb92a77741419a4ab5f06e711a283343f1ada0c3` | brainstorming, writing-plans, executing-plans, test-driven-development, systematic-debugging, verification-before-completion, requesting-code-review, receiving-code-review, subagent-driven-development | `brainstorming/scripts/` (a local visual-companion server that pulls a remote logo); `using-superpowers` (competes with RUN.md as the spine); git-worktree and branch-finishing skills (git operations are the member's) |
| [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | `56ea9cf174ed86786187daa9de0e6247cb0747e4` | ui-ux-pro-max (SKILL.md, references, data, scripts) | `scripts/tests/`; the `design-system` skill (hotlinks stock photos, generates slides) and the brand / banner / slides skills (not web-app work) |
| [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | `f624f37a8c650b9cc550253104925efe4c8de246` | design-taste-frontend, minimalist-ui, industrial-brutalist-ui, high-end-visual-design | `evals/`; image-generation, redesign, stitch and output skills (out of scope) |
| [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | `16352ac229eb08a9598dcae48fe9f2b342567d86` | ponytail, ponytail-review, ponytail-audit | hooks, plugin and extension code (the skills work without them) |

## What was checked before vendoring

- every vendored `SKILL.md` was scanned for network fetches, installs, git operations,
  destructive commands and telemetry; the conflicts found are overruled in `OVERRIDES.md` /
  `ROUTING.yaml` (git commits per step; GSAP presets for graded motion);
- the scripts that ship were scanned for network and process calls: ui-ux-pro-max's search and
  generator are offline (CSV / JSON); design-taste-frontend's asset scripts fetch licensed images
  over the network (allowed at authoring time, vendored with a licence, never hotlinked).

Directories are named for each skill's frontmatter `name`, which is how skill loaders find them.

## Re-vendoring

Clone the upstream at the new commit into an empty scratch directory, re-run the same scans,
copy the same subtrees into `vendor/`, update the commit here, then
`golden/bin/golden-sync-skills`.
