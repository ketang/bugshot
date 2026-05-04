## Codex Execution Requirements

When running Bugshot from Codex, do not finish the assistant turn while the
Bugshot CLI is still running.

Run Bugshot with `--json`, immediately print the gallery URL, then wait for the
CLI process to exit. If needed, keep the shell session open and poll it until
the process exits. As soon as the CLI exits, parse the final JSON line from
stdout.

If `draft_count > 0`, inspect every `image_path` or `asset_paths` entry, group
related comments into coherent issues when they describe the same defect, check
the target repository's documented issue tracker for duplicates, and prefer
updating a matching open issue over creating a duplicate. Include the screenshot
filename or unit id and the user comment in any filed or updated issue.

Treat submitted Bugshot comments as the user's filing intent. Do not pause for
a second confirmation before tracker mutations unless duplicate matching is
genuinely ambiguous or the target tracker is unknown.

After tracker mutations, run the target tracker's documented sync or push step
when one exists, then report the filed or updated issue IDs. Do not stop after
saying "gallery is running."
