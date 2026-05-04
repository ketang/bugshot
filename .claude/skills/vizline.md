---
name: vizline
description: Capture baseline screenshots so users can examine visual changes, whether intended or accidental
arguments:
  - name: feature_worktree
    description: Path to the feature worktree where the baseline should be written
    required: true
---

# Vizline — Bugshot Baseline Capture Skill

Run a project's `capture-command` against a base ref and store the result inside
the feature worktree at `.bugshot/baseline/`. The baseline is what `vizdiff`
later compares HEAD against.

## When to use

Before HEAD has diverged from the base ref in a way that affects rendered
output. Vizline is not primarily a regression detector; it prepares a baseline
for user examination of later visual changes, including changes that are
intended, accidental, or still undecided. Typically called once at the start of
feature work; refresh on rebase.

## Project contract

The target project must ship `.agent-plugins/bento/bugshot/viz/capture-command`
(executable). Optional companions: `should-baseline` (policy gate) and
`ephemeral-root` (worktree placement).

The full contract is documented in
`docs/specs/2026-04-25-vizdiff-vizline-design.md`.

## Startup

1. Validate `{{feature_worktree}}` is a git worktree.
2. Find the vizline installation directory (the directory containing this `SKILL.md`).
3. Run the CLI:

   ```bash
   python3 {{vizline_dir}}/vizline_cli.py --feature-worktree {{feature_worktree}}
   ```

4. The CLI either prints `Baseline written: <N> images, base=<sha>, dir=<path>`
   or, when `should-baseline` returned 1, prints the skip reason.

## Output

Successful run: `.bugshot/baseline/manifest.json` plus
`.bugshot/baseline/images/...` inside the feature worktree.

Refusal: non-zero exit and a stderr message. No partial baseline is left on
disk — vizline atomically promotes a fully-written `.bugshot/baseline.tmp/` to
the final location.

## CLI flags

- `--feature-worktree <path>` — required.
- `--base-ref <ref>` — default: `origin/HEAD`, falling back to `main`/`master`.
- `--ephemeral-root <path>` — override the placement of the throwaway base-ref
  worktree.
- `--task-title`, `--task-description`, `--task-id` — forwarded to
  `should-baseline` as env vars.
- `--force` — ignore `should-baseline`.
- `--refresh` — overwrite an existing baseline (e.g. after a rebase).

## Notes

- Trigger model: vizline ships with no enforced trigger. The launching skill or
  the agent decides when to invoke it.
- `should-baseline` returning exit 1 cleanly skips with a reason on stdout.
- vizline holds `.bugshot/baseline.lock` via `fcntl.flock` for the entire run;
  the kernel releases it on any process exit.
