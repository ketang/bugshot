# Installing Bugshot For Codex

Bugshot ships as a Codex plugin through `.codex-plugin/plugin.json` and the
`skills/` directory. The installer creates a local Codex marketplace, copies
the built plugin payload into it, and registers that marketplace with Codex.

## Requirements

- Codex CLI with plugin marketplace support
- Python 3
- A Bugshot checkout

## Install

From the repository root:

```bash
scripts/install-codex-plugin
```

By default this:

1. Runs `scripts/build-plugin`.
2. Writes a local marketplace at `${CODEX_HOME:-~/.codex}/marketplaces/bugshot`.
3. Copies the Codex plugin payload to `plugins/bugshot` inside that marketplace.
4. Registers the marketplace with:

   ```bash
   codex plugin marketplace add ${CODEX_HOME:-~/.codex}/marketplaces/bugshot
   ```

Restart any running Codex session after installation.

## Options

```bash
scripts/install-codex-plugin --help
```

Useful options:

- `--codex-home <path>`: register against a non-default Codex home.
- `--marketplace-root <path>`: write the marketplace somewhere else.
- `--skip-build`: copy the current plugin files without rebuilding.
- `--skip-register`: write the marketplace but do not call the Codex CLI.
- `--dry-run`: show the planned install without writing files.
- `-v, --verbose`: print each major step.

## Update

Pull the latest Bugshot checkout and rerun:

```bash
git pull
scripts/install-codex-plugin
```

The installer replaces only the Bugshot plugin directory inside the local
marketplace and rewrites Bugshot's marketplace entry.
