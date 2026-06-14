# Beads Workflow

Use bd (Beads) for all task tracking. Do not use TodoWrite, TaskCreate, or
markdown TODO files. Use `bd remember "insight"` for persistent project
knowledge; do not create MEMORY.md files.

Core commands:

```bash
bd ready
bd show <id>
bd create --title="..." --description="..." --type=task
bd update <id> --claim
bd close <id>
bd dep add <issue> <depends-on>
```

Before ending work:

```bash
git status
git add <files>
git commit -m "..."
git push
```

Push Beads state when tracker data changes:

```bash
bd dolt push
```

For persistent memories, run `bd memories`.
Run `bd prime --full` for the complete reference.
