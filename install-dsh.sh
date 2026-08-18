#!/usr/bin/env bash
# Install WeWrite CLI and copy its skills into DeepSeek Harness.
set -euo pipefail

cd "$(dirname "$0")"
REPO="$(pwd)"
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "找不到 $PYTHON；WeWrite 需要 Python 3.11+。" >&2
  exit 1
fi

echo "→ 安装 WeWrite CLI"
if command -v uv >/dev/null 2>&1; then
  uv tool install --force "$REPO"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force "$REPO"
else
  "$PYTHON" -m pip install --user "$REPO"
fi

echo "→ 安装 DeepSeek Harness skills"
"$PYTHON" "$REPO/scripts/dsh_adapter.py" install "$@"
echo "✓ 完成。运行 '$PYTHON scripts/dsh_adapter.py doctor' 可检查安装。"
