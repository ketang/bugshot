---
name: bugshot
description: Launch a review gallery on a directory of screenshots or grouped review units; emit issue drafts from user comments. For visual diffs against a baseline, prefer vizdiff.
arguments:
  - name: directory
    description: Path to the review root containing screenshots or grouped review units
    required: true
---

# Bugshot — Review Unit Bug Filing Skill

Review screenshots or grouped review units in a browser gallery and file issues
from user comments.

Bugshot refuses to launch on directories inside a `.bugshot/` working area
(e.g. `.bugshot/baseline/`, `.bugshot/baseline/images/`, `.bugshot/head/`).
Those are vizline/vizdiff state, not review roots — use `vizdiff` to diff HEAD
against the baseline instead.

## Startup

1. Validate that `{{directory}}` exists and contains either:
   - at least one recognized top-level file, or
   - at least one child directory containing recognized files

   Recognized extensions are defined in `gallery_server.py:IMAGE_EXTENSIONS` and
   `ANSI_EXTENSION` (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`, `.ansi`).

   The canonical producer-facing input format is documented in
   `docs/specs/2026-04-24-review-units.md`.

   Grouped units may include `bugshot-unit.json` to set the display label,
   explicit asset/metadata ordering, and optional per-asset tooltips through
   `asset_tooltips`.
2. Find the bugshot installation directory (the directory containing this `SKILL.md`).
3. Select the bind address by running the skill helper script. Capture stdout
   as the bind address and preserve stderr for the explanatory message:

```bash
bind_address="$({{bugshot_dir}}/select-bind-address)"
```

   The helper prints the selected address on stdout and an explanatory message
   on stderr. In an interactive agent session, immediately print the explanatory
   message in the visible conversation. The helper treats `SSH_CONNECTION`,
   `SSH_CLIENT`, or `SSH_TTY` as remote-login signals; it captures those signals
   in a separate variable before testing them. If a remote-login signal is
   present, it selects `0.0.0.0`; otherwise it selects `127.0.0.1`.

4. Run the CLI in the foreground with `--json --bind "$bind_address"`. This is
   a blocking call — **do not use background mode**:

```bash
python3 {{bugshot_dir}}/bugshot_cli.py --json --bind "$bind_address" {{directory}}
```

   The CLI blocks until the user finishes reviewing and the session ends. In
   Claude Code the Bash tool streams stderr in real time, so the gallery URL
   appears in the tool output while the command is still running.

5. The first line of the CLI's stderr is `Gallery is running at <url>`. Once
   the tool call returns (after the user has finished reviewing), print the URL
   in the visible conversation and tell the user what happened:

   > Bugshot gallery is running at `<url>`. Open that URL, review the units, type comments on any issues you see, then click "Done Reviewing".

   The skill selects the bind address before launching the CLI. In SSH-like
   sessions, it binds to `0.0.0.0` so the URL can be reachable from other hosts
   on the network. Otherwise it binds to `127.0.0.1`. If the user explicitly
   requests a bind mode, honor that request instead of using the helper.

6. The CLI exits on its own when the user clicks "Done Reviewing" (or when the
   heartbeat times out). The foreground Bash call returns at that point. The
   CLI handles all polling and browser lifecycle internally — do not poll any
   HTTP endpoints yourself.

## Process Comments

The CLI's stdout ends with a single JSON line. Flat screenshot mode preserves
the legacy per-image draft shape, while grouped-unit mode emits unit context:

```json
{"draft_count": 2, "drafts": [
  {"image_name": "login-page.png", "image_path": "/abs/path/login-page.png",
   "user_comment": "Submit button is clipped",
   "region": null},
  {"image_name": "login-page.png", "image_path": "/abs/path/login-page.png",
   "user_comment": "Color regression on the highlighted region",
   "region": {"type": "rect", "x": 0.12, "y": 0.55, "w": 0.34, "h": 0.08}},
  {"unit_id": "login-flow", "unit_label": "login-flow",
   "unit_path": "/abs/path/login-flow",
   "asset_names": ["reference.png", "candidate.png"],
   "asset_paths": ["/abs/path/login-flow/reference.png", "/abs/path/login-flow/candidate.png"],
   "metadata_names": ["report.json"],
   "metadata_paths": ["/abs/path/login-flow/report.json"],
   "user_comment": "The candidate misses the right edge"}
  ...
]}
```

`region` is `null` for image-level comments; otherwise it is an object describing a user-drawn rectangle (`{type: "rect", x, y, w, h}`), ellipse (`{type: "ellipse", cx, cy, rx, ry}`), or freehand path (`{type: "path", points}`) with all coordinates normalized to `[0, 1]`. The field appears on single-image drafts only (those with `image_name`/`image_path`); grouped-unit drafts do not currently include it. If the issue tracker supports image annotations (e.g., draw-on-screenshot), the agent should render the region payload onto the image before attaching.

If `draft_count` is `0`, report "No comments were submitted." and stop.

For each draft:

**a. Examine the review target.**

- If the draft has `image_path`, read that image using your vision capability.
- If the draft has `asset_paths`, inspect the asset set holistically. Use
  `metadata_paths` as additional context when present.

Identify:
- What screen/page/view or artifact group is shown
- What elements are relevant to the user's comment
- What specifically appears wrong or unexpected

**b. Compose the issue.** Combine the user's comment with your visual analysis. If the project has issue templates, follow them. Otherwise use this structure:

```
## Current Behavior
[What is happening, based on the screenshot + user's comment]

## Expected Behavior
[What should happen instead, inferred from context]

## Screenshot Description
[Detailed description of the screenshot or grouped review unit, sufficient without the image files]

## Additional Context
- Screenshot or unit: <image_name or unit_id>
- User comment: "<user_comment>"
```

**c. Check for duplicates.** If the project has an issue-flow skill, use its search capability with keywords from the composed issue. Present any potential duplicates before filing:

> Found potential duplicates:
> - #42: "Login button overflow on mobile" (open)
> - #31: "Submit button CSS issue" (closed)
>
> File anyway, or skip?

If there is no issue-flow skill available, skip duplicate checking.

**d. Confirm with the user.** Show the composed issue:

> **Filing issue for `login-page.png` or `login-flow`:**
> [composed issue text]
>
> File this issue?

If the user says no, allow them to edit or skip.

**e. File the issue.** Delegate to the project's issue-flow skill. If no such skill is available, tell the user the issue is ready and ask where to file it (or write it to a file).

**f. Attach the evidence.** If the tracker supports attachments, attach the
relevant files:

- for single-image drafts, attach `image_path`
- for grouped-unit drafts, attach the most relevant asset files from
  `asset_paths`, and attach metadata files when they materially clarify the issue

If attachment fails, report concisely:

> Note: Could not attach screenshot to #42 (attachment not supported by tracker).

**g. Report.**

> Filed: #42 — "Login submit button is clipped on right edge"

After all drafts are processed:

> Bugshot session complete. Filed N issues, skipped M.

## Error Handling

- If the CLI exits non-zero, report the contents of its stderr and stop.
- If the stdout doesn't end with a parseable JSON line, report the CLI output verbatim and stop.
- If an issue fails to file, report the error and continue with the remaining drafts.

## Claude Code Notes

This Claude skill is generated from the shared Bugshot contract plus this
overlay. Follow the shared lifecycle: launch the gallery, wait for the CLI to
exit, then process the emitted drafts through the target project's issue
workflow.

**Always run the CLI as a blocking foreground Bash call.** Never use
`run_in_background`. The Bash tool streams stderr in real time, so the gallery
URL is visible to the user in the tool output while the command blocks. The
JSON output is only available after the process exits normally; background
execution breaks output capture.

There are no Claude-specific tracker requirements in this overlay.
