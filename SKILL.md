---
name: bugshot
description: Launch a screenshot gallery for visual bug review and issue filing
arguments:
  - name: directory
    description: Path to the directory containing screenshots
    required: true
---

# Bugshot — Screenshot Bug Filing Skill

Review screenshots in a browser gallery and file issues from user comments.

## Startup

1. Validate that `{{directory}}` exists and contains recognized files (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ansi`).
2. Find the bugshot installation directory (the directory containing this SKILL.md).
3. Launch the gallery server:

```bash
python3 {{bugshot_dir}}/gallery_server.py {{directory}}
```

4. Read the startup JSON from stdout. It will be a single line:

```json
{"port": N, "url": "http://127.0.0.1:N", "images": ["file1.png", ...]}
```

5. Attempt to open the URL in the user's browser:

```python
import webbrowser
webbrowser.open(url)
```

If this fails (headless environment, SSH), tell the user the URL:
> Gallery is running at `http://127.0.0.1:<port>` — open this URL to review screenshots.

6. Tell the user:
> Bugshot gallery is open. Review the screenshots, type comments on any issues you see, then click "Done Reviewing" when finished.

## Wait for User

Poll `GET http://127.0.0.1:<port>/api/status` every 3 seconds.

The response will be:
```json
{"done": true, "reason": "button"|"timeout"|"closed"}
```

- If `reason` is `"button"`: user clicked Done. Proceed to processing.
- If `reason` is `"timeout"` or `"closed"`: the browser was closed. Confirm with the user:
  > It looks like you closed the browser. Are you done reviewing, or would you like to reopen the gallery?
  - If done: proceed to processing.
  - If reopen: open the URL again and resume polling.
- The user may also say "done" or equivalent in the terminal. If so, proceed to processing.

## Process Comments

1. Fetch all comments: `GET http://127.0.0.1:<port>/api/comments`

Response:
```json
[
  {"id": 1, "image": "login-page.png", "body": "Submit button is clipped", "created_at": "..."},
  ...
]
```

2. If no comments, report "No comments were submitted." and proceed to shutdown.

3. For each comment:

   **a. Examine the screenshot.**
   Read the image file at `{{directory}}/<comment.image>` using your vision capability. Identify:
   - What screen/page/view is shown
   - What UI elements are relevant to the user's comment
   - What specifically appears wrong or unexpected

   **b. Compose the issue.**
   Combine the user's comment with your visual analysis. If the project has issue templates, follow them. Otherwise use this structure:

   ```
   ## Current Behavior
   [What is happening, based on your examination of the screenshot + user's comment]

   ## Expected Behavior
   [What should happen instead, inferred from context]

   ## Screenshot Description
   [Detailed description of what the screenshot shows, sufficient for someone without access to the image]

   ## Additional Context
   - Screenshot: <comment.image>
   - User comment: "<comment.body>"
   ```

   **c. Check for duplicates.**
   Search existing issues (open and closed) using keywords from the composed issue. Use the project's issue-flow skill search capability.

   If potential duplicates are found, present them:
   > Found potential duplicates:
   > - #42: "Login button overflow on mobile" (open)
   > - #31: "Submit button CSS issue" (closed)
   >
   > File anyway, or skip?

   If the user says skip, move to the next comment.

   **d. Confirm with the user.**
   Show the composed issue in the terminal:
   > **Filing issue for `login-page.png`:**
   > [composed issue text]
   >
   > File this issue?

   If the user says no, allow them to edit or skip.

   **e. File the issue.**
   Delegate to the project's issue-flow skill to create the issue.

   **f. Attempt image attachment.**
   If the issue-flow skill or tracker supports attachments, attach the screenshot file. If attachment fails, report concisely:
   > Note: Could not attach screenshot to #42 (attachment not supported by tracker).

   **g. Report.**
   > Filed: #42 — "Login submit button is clipped on right edge"

4. After all comments are processed, summarize:
   > Bugshot session complete. Filed N issues, skipped M.

## Shutdown

Terminate the gallery server process. The temporary database is cleaned up automatically.

## Error Handling

- If the server fails to start, report the error from stderr and exit.
- If the server dies during the session, report it and offer to restart.
- If an issue fails to file, report the error and continue with the remaining comments.
