---
name: vizline
description: TRIGGER at branch start before any rendered-output edit when `.agent-plugins/bento/bugshot/viz/capture-command` exists in the worktree and edits may affect UI, templates, or design system. Captures the pre-edit baseline. Required upstream of vizdiff.
arguments:
  - name: feature_worktree
    description: Path to the feature worktree where the baseline should be written
    required: true
---

# Vizline — Bugshot Baseline Capture Skill

Run a project's `capture-command` at branch start and store the result inside
the feature worktree at `.bugshot/baseline/`. The default path captures directly
in the supplied feature worktree. The baseline is what `vizdiff` later compares
HEAD against.

## When to use

Run at branch start, before any edit that might change rendered output. Vizline
is not primarily a regression detector; it prepares a baseline for later user
examination of visual changes, intended or accidental. Typically called once at
the start of feature work; refresh on rebase.

If work has already begun and no baseline exists, run vizline with
`--from-base-ref`. That explicit mode creates a temporary detached worktree at
the resolved base ref, captures there, copies the completed baseline into the
feature worktree, and removes the temporary worktree.

Skip when:

- The repo doesn't ship `.agent-plugins/bento/bugshot/viz/capture-command`.
- The task is backend-only (API, schema, migrations, infra) with no rendered
  impact.
- A current baseline already exists at `.bugshot/baseline/manifest.json` matching
  the current base ref. Pass `--refresh` only after a rebase or when the prior
  baseline is known stale.

## Project contract

The target project must ship `.agent-plugins/bento/bugshot/viz/capture-command`
(executable). Optional companions: `should-baseline` (policy gate) and
`ephemeral-root` (temporary worktree placement for `--from-base-ref`).

The full contract is documented in
`docs/specs/2026-04-25-vizdiff-vizline-design.md`.

## Startup

1. Validate `{{feature_worktree}}` is a git worktree.
2. Find the vizline installation directory (the directory containing this `SKILL.md`).
3. Run the default branch-start CLI:

   ```bash
   python3 {{vizline_dir}}/vizline_cli.py --feature-worktree {{feature_worktree}}
   ```

4. If a baseline is needed after work has already begun, run:

   ```bash
   python3 {{vizline_dir}}/vizline_cli.py --feature-worktree {{feature_worktree}} --from-base-ref
   ```

5. The CLI either prints `Baseline written: <N> images, base=<sha>, dir=<path>`
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
- `--from-base-ref` — capture from a temporary detached base-ref worktree. Use
  this only when a baseline must be created after work has begun.
- `--ephemeral-root <path>` — override the placement of the throwaway base-ref
  worktree. Requires `--from-base-ref`.
- `--task-title`, `--task-description`, `--task-id` — forwarded to
  `should-baseline` as env vars.
- `--force` — ignore `should-baseline`.
- `--refresh` — overwrite an existing baseline (e.g. after a rebase).

## Notes

- Trigger model: vizline ships with no enforced trigger. The launching skill or
  the agent decides when to invoke it.
- Default branch-start capture requires the feature worktree to be clean and
  `HEAD` to match the resolved base ref. If that is no longer true, use
  `--from-base-ref`.
- `should-baseline` returning exit 1 cleanly skips with a reason on stdout.
- vizline holds `.bugshot/baseline.lock` via `fcntl.flock` for the entire run;
  the kernel releases it on any process exit.
