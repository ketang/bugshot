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
