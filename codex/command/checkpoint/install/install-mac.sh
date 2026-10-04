#!/usr/bin/env bash
# checkpoint 六件套 — macOS 安装脚本
#
# 行为：
#   1. 把 prompts/*.md 复制到 ~/.codex/prompts/
#   2. 输出迁移来源的权限参考片段（当前 Codex 桌面环境通常无需手工合并）
#
# 不会自动改任何 Codex 全局配置（避免覆盖现有配置）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROMPTS_SRC="$TOOL_DIR/prompts"
PROMPTS_DST="$HOME/.codex/prompts"
SCRIPTS_SRC="$TOOL_DIR/scripts"
SCRIPTS_DST="$HOME/.codex/scripts"
PERM_FILE="$TOOL_DIR/permissions/mac.json"

echo "==> 安装 checkpoint 六件套到 $PROMPTS_DST"

mkdir -p "$PROMPTS_DST"
mkdir -p "$SCRIPTS_DST"
mkdir -p "$HOME/.codex/checkpoints"

# online 三件套：clone 云端 checkpoint 工作区（已存在则跳过）
ONLINE_DIR="$HOME/.codex/checkpoints-online"
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
  cp "$PROMPTS_SRC/$cmd" "$PROMPTS_DST/$cmd"
  echo "    [ok]   ${cmd}（已同步最新版本）"
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
echo "==> 权限参考（通常不用手工合并）"
echo ""
echo "下面是从 Claude Code checkpoint 包迁移过来的权限参考。"
echo "当前 Codex 桌面环境通常不需要手工合并；如果你的 Codex 表面支持类似 permissions.allow，再按需参考："
echo ""
echo "----------------------------------------"
cat "$PERM_FILE"
echo "----------------------------------------"
echo ""
echo "==> 测试"
echo "在 Codex 里跑 /checkpoint 看看能不能用。"
