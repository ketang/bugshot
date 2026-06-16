---
name: wire-bugshot
description: Add Bugshot visual-review wiring to a target git worktree. Use when a project needs `.agent-plugins/bento/bugshot/viz/capture-command` so `bugshot:vizline` and `bugshot:vizdiff` can trigger, or when seeding an initial `.bugshot/baseline/` after explicit user approval.
---

# Wire Bugshot

Create the project-owned trigger files that make `bugshot:vizline` and
`bugshot:vizdiff` usable in a target repository.

## Workflow

1. Identify the target git worktree. Default to the current repository root
   unless the user names another worktree.
2. Find the deterministic screenshot command. Prefer existing commands in the
   target repo's agent docs, `Makefile`, `package.json`, demo scripts, or CI
   workflow. If there is no clear command, ask the user for it.
3. Form the command as a template. Use `{output_dir}` where Bugshot should pass
   the screenshot output directory. If the project command accepts the output
   directory as its final argument, the placeholder can be omitted.
4. Find this skill's installation directory, then run:

   ```bash
   python3 {{wire_bugshot_dir}}/wire_bugshot_cli.py --worktree <target-worktree> --capture-command '<command template>'
   ```

5. The CLI validates the command twice before writing anything. It refuses
   commands that produce no recognized files or produce different relative
   output paths between runs, which catches timestamped filenames and similar
   nondeterministic capture layouts.
6. After successful wiring, inspect the generated executable:
   `<target-worktree>/.agent-plugins/bento/bugshot/viz/capture-command`.
7. Document the new wiring in the target repo's agent instructions so future
   sessions know the vizline/vizdiff triggers are live.

## Optional Baseline

Seed `.bugshot/baseline/` only after explicit user approval. Then run:

```bash
python3 {{wire_bugshot_dir}}/wire_bugshot_cli.py \
  --worktree <target-worktree> \
  --capture-command '<command template>' \
  --seed-baseline
```

Use `--base-ref <ref>` when the default base ref should not be `origin/HEAD`,
`main`, or `master`. Use `--refresh-baseline` only when the user approves
replacing an existing baseline.

## Output

The required output is an executable:

```text
<target-worktree>/.agent-plugins/bento/bugshot/viz/capture-command
```

When `--seed-baseline` is used, the CLI also writes:

```text
<target-worktree>/.bugshot/baseline/manifest.json
<target-worktree>/.bugshot/baseline/images/...
```

The generated `capture-command` accepts exactly one argument, the output
directory. It runs from the target repo root and exposes the same path as
`BUGSHOT_CAPTURE_OUTPUT_DIR` for project commands that prefer environment
variables.
