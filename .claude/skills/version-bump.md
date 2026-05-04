---
name: version-bump
description: |
  Evaluate whether the plugin version should be bumped based on accumulated
  canonical changes since the last version commit. Only bumps for behavioral changes.
---

# Version Bump

## When to Use

Invoke at natural completion points: feature complete, plan tasks done, or ending a
session with unbumped behavioral changes in canonical files.

## Workflow

### Step 1 — Find the baseline

```
git log -n1 --format=%H -- plugin-version.json
```

If no commit exists, stop — the version file needs manual bootstrapping.

### Step 2 — Check for canonical changes

```
git diff --name-only <baseline> -- skills/*/SKILL.md skills/*/overlays/ gallery_server.py ansi_render.py static/ templates/ scripts/build-plugin
```

If nothing changed, stop. No bump needed.

### Step 3 — Read the diffs

```
git diff <baseline>..HEAD -- skills/*/SKILL.md skills/*/overlays/ gallery_server.py ansi_render.py static/ templates/ scripts/build-plugin
```

### Step 4 — Classify the changes

**Behavioral (bump):**
- New, removed, or renamed files in `static/` or `templates/`
- Changed logic in `gallery_server.py` or `ansi_render.py`
- Changed canonical SKILL.md content (frontmatter or instructions)
- Changed agent-specific overlay content
- New or modified test assertions
- Changed metadata constants or asset generation in `scripts/build-plugin`

**Cosmetic (skip):**
- Whitespace-only changes
- Comment rewording or typo fixes
- Changes to `docs/`, specs, plans, or `CLAUDE.md`

Mixed diffs count as behavioral — err on the side of bumping.

### Step 5 — Act

**If behavioral or mixed:**

```
scripts/build-plugin --bump
git add plugin-version.json .claude-plugin/ .codex-plugin/ assets/
git commit -m "chore: bump plugin version for <brief description>"
```

**If cosmetic only:** skip.

## Idempotency

Running `scripts/build-plugin` (without `--bump`) at any time is safe — it regenerates
deterministically at the current version.
