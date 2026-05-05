# Frontend Code Quality Changes

## What was added

### Prettier formatting (analogous to Black for Python)

- **`package.json`** — defines the project as a Node package and exposes two npm scripts:
  - `npm run format` — auto-formats all files under `frontend/`
  - `npm run format:check` — exits non-zero if any file is out of format (suitable for CI)

- **`.prettierrc`** — Prettier configuration:
  - 100-char print width
  - 2-space indentation, no tabs
  - Semicolons on, double quotes, ES5 trailing commas
  - `htmlWhitespaceSensitivity: "css"` so HTML formatting follows CSS display rules
  - LF line endings

- **`scripts/check-frontend.sh`** — shell script that runs the Prettier check and prints a clear pass/fail message. Run with `./scripts/check-frontend.sh`.

### Formatting applied to existing files

All three frontend files were reformatted with Prettier:
- `frontend/index.html`
- `frontend/script.js`
- `frontend/style.css`

No logic or behaviour was changed — only whitespace and quote consistency were normalised.

## How to use

```bash
# Auto-format (fix in place)
npm run format

# Check only (CI-safe, no writes)
npm run format:check

# Or use the convenience script
./scripts/check-frontend.sh
```
