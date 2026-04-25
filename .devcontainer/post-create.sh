#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Databricks CLI"
if command -v databricks >/dev/null 2>&1; then
  echo "  already installed: $(databricks --version)"
else
  curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sudo sh
fi

echo "==> Ensuring python3 is available"
if ! command -v python3 >/dev/null 2>&1 || ! command -v pip3 >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
else
  echo "  already installed: $(python3 --version)"
fi

echo "==> Installing Claude Code"
npm install -g @anthropic-ai/claude-code

echo "==> Installing Databricks agent skills"
npx -y skills add databricks/databricks-agent-skills --all || echo "(skipped — re-run manually if desired)"

echo "==> Verifying"
databricks --version
node --version
claude --version || true

echo "==> Done. Your isolated dev env is ready."
