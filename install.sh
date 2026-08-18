#!/usr/bin/env bash
# WeWrite 安装脚本（v2.2 起）：wewrite CLI + skill 符号链接 + 旧状态迁移
#
# 1) 安装 `wewrite` CLI（确定性工具层，pip 包）：
#    优先 uv tool install，其次 pipx；都没有则回退仓库内 venv +
#    editable 安装并链接到 ~/.local/bin（绕过 macOS PEP 668）。
#    在 dist 拷贝（无 pyproject.toml）里运行时自动改为从 git 安装。
# 2) 把 skills/ 下的主入口与各 wewrite-* 模块符号链接到
#    ~/.claude/skills/ 和 ~/.agents/skills/（可用环境变量覆盖）；
#    检测到 OpenClaw / Codex 时（~/.openclaw、~/.codex 存在）同样链接——
#    三家均原生支持 folder-per-skill 的 Agent Skills 标准。
# 3) 检测到 v2.1 之前留在仓库根的用户状态（style.yaml 等）时，
#    执行 `wewrite migrate` 迁到 $WEWRITE_HOME（默认 ~/.wewrite，幂等）。
#
# 用法：  bash install.sh
# 幂等：  可重复运行。

set -euo pipefail

cd "$(dirname "$0")"
REPO="$(pwd)"

# 本地仓库（有 pyproject）从本地装最新代码；dist 拷贝等场景装 PyPI 发布版
PYPI_SRC="wewrite"
SRC="$REPO"
[ -f "$REPO/pyproject.toml" ] || SRC="$PYPI_SRC"

# ---- 1) wewrite CLI ----
echo "→ 安装 wewrite CLI（来源: $SRC）..."
if command -v uv >/dev/null 2>&1; then
  uv tool install --force "$SRC"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force "$SRC"
else
  echo "  （未找到 uv/pipx，回退 venv editable 安装）"
  PYTHON="${PYTHON:-python3}"
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "✗ 找不到 $PYTHON。请先安装 Python 3.11+（macOS: brew install python）。" >&2
    exit 1
  fi
  [ -d .venv ] || "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  if [ -f "$REPO/pyproject.toml" ]; then
    .venv/bin/python -m pip install -e "$REPO"
  else
    .venv/bin/python -m pip install "$PYPI_SRC"
  fi
  mkdir -p "$HOME/.local/bin"
  ln -sfn "$REPO/.venv/bin/wewrite" "$HOME/.local/bin/wewrite"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "⚠ 请把 ~/.local/bin 加入 PATH（wewrite 命令链接在那里）" >&2 ;;
  esac
fi
command -v wewrite >/dev/null 2>&1 && echo "✓ wewrite CLI 就绪：$(command -v wewrite)" \
  || echo "⚠ 当前 shell 尚未找到 wewrite，重开终端或检查 PATH" >&2

# ---- 2) skill 链接：Claude Code + Agent-Skills 标准目录；
#      装了 OpenClaw / Codex 的机器（其家目录已存在）也一并链接 ----
DESTS=("${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}" "${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}")
for OPT in "$HOME/.openclaw/skills" "$HOME/.codex/skills"; do
  [ -d "$(dirname "$OPT")" ] && DESTS+=("$OPT")
done
if [ -d skills ]; then
  for SKILLS_TARGET in "${DESTS[@]}"; do
    # 防呆：目标本身是指回本仓库的符号链接时，逐 skill 链接会写回仓库内，跳过
    if [ -L "$SKILLS_TARGET" ]; then
      resolved="$(cd "$SKILLS_TARGET" 2>/dev/null && pwd -P || true)"
      case "$resolved" in
        "$REPO"|"$REPO"/*)
          echo "⚠ 跳过 $SKILLS_TARGET：它是指回本仓库的符号链接，请先 rm 掉再重跑" >&2
          continue
          ;;
      esac
    fi
    mkdir -p "$SKILLS_TARGET"
    linked=0
    for d in skills/wewrite*; do
      [ -f "$d/SKILL.md" ] || continue
      name="$(basename "$d")"
      ln -sfn "$REPO/$d" "$SKILLS_TARGET/$name"
      linked=$((linked + 1))
    done
    echo "✓ 已链接 $linked 个 skill 到 $SKILLS_TARGET"
  done
  echo "  单独激活示例：/wewrite-topic 选题、/wewrite-review 自检、/wewrite-rewrite 多平台改写"
fi

# ---- 3) 旧状态迁移（v2.1 之前状态在仓库根）----
if command -v wewrite >/dev/null 2>&1; then
  if [ -f "$REPO/style.yaml" ] || [ -f "$REPO/history.yaml" ] || [ -f "$REPO/config.yaml" ]; then
    echo "→ 检测到仓库根有旧版用户状态，迁移到 $(wewrite home) ..."
    wewrite migrate --from "$REPO"
  fi
fi

echo ""
echo "✓ 完成。状态目录: $(command -v wewrite >/dev/null 2>&1 && wewrite home || echo '~/.wewrite')"
