#!/usr/bin/env bash
# checkpoint 三件套 — macOS 安装脚本
#
# 行为：
#   1. 把 commands/*.md 复制到 ~/.claude/commands/
#   2. 输出权限白名单片段，让用户手动 merge 到 ~/.claude/settings.json
#
# 不会自动改 ~/.claude/settings.json（避免覆盖现有配置）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMANDS_SRC="$TOOL_DIR/commands"
COMMANDS_DST="$HOME/.claude/commands"
SCRIPTS_SRC="$TOOL_DIR/scripts"
SCRIPTS_DST="$HOME/.claude/scripts"
PERM_FILE="$TOOL_DIR/permissions/mac.json"

echo "==> 安装 checkpoint 三件套到 $COMMANDS_DST"

mkdir -p "$COMMANDS_DST"
mkdir -p "$SCRIPTS_DST"
mkdir -p "$HOME/.claude/checkpoints"

# online 三件套：clone 云端 checkpoint 工作区（已存在则跳过）
ONLINE_DIR="$HOME/.claude/checkpoints-online"
ONLINE_REPO="<CHECKPOINT_REPO_URL>"
# 判据用 <...> 形态而不是占位符字面量：开源导出后用户整包替换占位符时，
# 这行判断不会被一起换掉。真实 Git 地址不会以 "<" 开头。
if [[ "$ONLINE_REPO" == "<"*">" ]]; then
  echo "    [skip] 云端仓库地址尚未配置：$ONLINE_REPO"
  echo "           请先把本包内的 $ONLINE_REPO 全部替换为你自己的 checkpoint Git 仓库地址，再重跑本脚本。"
  echo "           （只影响 online 三件套；本地三件套不受影响，继续安装）"
elif [[ -d "$ONLINE_DIR/.git" ]]; then
  echo "    [skip] 云端工作区已存在：$ONLINE_DIR"
else
  echo "==> clone 云端 checkpoint 工作区到 $ONLINE_DIR"
  if git clone "$ONLINE_REPO" "$ONLINE_DIR"; then
    echo "    [ok]   云端工作区就绪"
  else
    echo "    [warn] clone 失败（网络 / 仓库访问权限），稍后手动跑：git clone $ONLINE_REPO $ONLINE_DIR"
  fi
fi

for cmd in checkpoint.md checkpoint-load.md task-done.md \
           checkpoint-online.md checkpoint-load-online.md task-done-online.md; do
  if [[ -f "$COMMANDS_DST/$cmd" ]]; then
    echo "    [skip] $cmd 已存在（如需覆盖，先手动删除再跑）"
  else
    cp "$COMMANDS_SRC/$cmd" "$COMMANDS_DST/$cmd"
    echo "    [ok]   $cmd"
  fi
done

echo ""
echo "==> 安装扫描脚本到 $SCRIPTS_DST"
for sh in list-checkpoints.sh; do
  cp "$SCRIPTS_SRC/$sh" "$SCRIPTS_DST/$sh"
  chmod +x "$SCRIPTS_DST/$sh"
  echo "    [ok]   $sh"
done

echo ""
echo "==> 命令安装完成"
echo ""
echo "==> 接下来：手动合并权限白名单"
echo ""
echo "把下面这些条目加到 ~/.claude/settings.json 的 permissions.allow 数组里："
echo ""
echo "----------------------------------------"
cat "$PERM_FILE"
echo "----------------------------------------"
echo ""
echo "完成后，重启 Claude Code 让权限生效。"
echo ""
echo "==> 测试"
echo "在 Claude Code 里跑 /checkpoint 看看能不能用。"
