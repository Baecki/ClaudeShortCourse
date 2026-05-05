#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Checking frontend formatting with Prettier..."
npx prettier --check frontend/
echo "    All files are formatted correctly."
