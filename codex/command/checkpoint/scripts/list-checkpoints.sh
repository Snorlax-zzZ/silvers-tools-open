#!/usr/bin/env bash
# list-checkpoints.sh
#
# 扫描 checkpoint 文件，输出 Codex 可一次性解析的"行格式"，
# 用来替代 checkpoint-load(-online) skill 里原本的 `for ... do head/grep/stat ... done`
# 复合 shell 脚本——后者会触发 Bash 工具的 compound command 确认弹窗，
# allowlist 单条命令通配符救不了，只能把整段脚本落到磁盘 + allowlist 整条 sh 路径。
#
# 用法：
#   list-checkpoints.sh                       # 默认：扫本地所有项目 ~/.codex/checkpoints
#   list-checkpoints.sh --here <subdir>       # 仅扫某个项目子目录（subdir = 子目录名）
#   list-checkpoints.sh --online              # 扫云端 ~/.codex/checkpoints-online/codex/
#   list-checkpoints.sh --online --here <sub> # 云端 Codex 命名空间 + 指定项目
#
# --online 根目录锁定 `codex/`，避免扫到 cc、zcode、shared 等其他客户端。
# online 的 MTIME 使用 git commit time；git pull 会刷新 fs mtime，不能拿它判断跨机更新。
#
# 每命中一个进行中 checkpoint，输出一行（"|" 分隔，Codex 直接 split 即可）：
#   FILE|<绝对路径>|PROJ|<项目目录名>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|MACHINE|<存档机>|TITLE|<标题>
#
# MACHINE 字段仅 online 版 frontmatter 有意义；本地版无此字段时输出空（"MACHINE||"）。
#
# - 过滤：仅 frontmatter status=in-progress
# - 排除：任何路径含 done/ 的（归档区）
# - mtime：本地用 fs mtime；online 用 git commit time，未提交文件才回退 fs mtime
# - fs mtime 跨平台：mac=BSD stat，Linux / Windows git-bash=GNU stat
# - 没命中时空输出，不报错，不返回非零退出码

set -u

ROOT="$HOME/.codex/checkpoints"
IS_ONLINE=0
HERE=""
HERE_SET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --online)  ROOT="$HOME/.codex/checkpoints-online/codex"; IS_ONLINE=1; shift ;;
    --here)
      if [ $# -lt 2 ]; then
        echo "--here requires a project subdir" >&2
        exit 2
      fi
      HERE="$2"; HERE_SET=1; shift 2
      ;;
    --here=*)  HERE="${1#--here=}"; HERE_SET=1; shift ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
    *)         shift ;;
  esac
done

# `--here` 只能接受单个项目目录名。除了不能通过 ../ 或路径分隔符逃出扫描根目录，
# 还要挡住 glob 元字符 * ? [ ]：它们会原样进到下面 find 的 -path "*/$HERE/*.md"，
# 而 -path 的 * 能跨 / 匹配，传个 * 就把「只扫一个项目」放大成扫全部。
if [ "$HERE_SET" = "1" ]; then
  case "$HERE" in
    ""|"."|".."|*/*|*\\*|*'*'*|*'?'*|*'['*|*']'*)
      echo "invalid --here project subdir: $HERE" >&2
      exit 2
      ;;
  esac
fi

[ -d "$ROOT" ] || exit 0

SEARCH_DIR="$ROOT"
# --here 只接受一个项目目录名，并在选定 ROOT 内匹配该目录。

# 检测 stat 风格（BSD vs GNU）
if stat -f '%Sm' / >/dev/null 2>&1; then
  STAT_FMT="bsd"
else
  STAT_FMT="gnu"
fi

get_effective_mtime() {
  local f="$1"
  if [ "$IS_ONLINE" = "1" ]; then
    local gtime
    gtime=$(git -C "$ROOT" log -1 --pretty=format:'%cI' -- "$f" 2>/dev/null)
    if [ -n "$gtime" ]; then
      printf '%s' "$gtime"
      return
    fi
  fi
  if [ "$STAT_FMT" = "bsd" ]; then
    stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%S%z' "$f" 2>/dev/null
  else
    stat -c '%y' "$f" 2>/dev/null | awk '{gsub(/ /,"T"); print}'
  fi
}

if [ -n "$HERE" ]; then
  FIND_FILTER=( -path "*/$HERE/*.md" )
else
  FIND_FILTER=( -name '*.md' )
fi

find "$SEARCH_DIR" -type f "${FIND_FILTER[@]}" -not -path '*/done/*' 2>/dev/null | while IFS= read -r f; do
  head_text=$(head -n 20 "$f" 2>/dev/null) || continue

  status=$( printf '%s\n' "$head_text" | sed -n 's/^status:[[:space:]]*//p'     | head -1)
  [ "$status" = "in-progress" ] || continue

  created=$(printf '%s\n' "$head_text" | sed -n 's/^created_at:[[:space:]]*//p' | head -1)
  updated=$(printf '%s\n' "$head_text" | sed -n 's/^updated_at:[[:space:]]*//p' | head -1)
  title=$(  printf '%s\n' "$head_text" | sed -n 's/^title:[[:space:]]*//p'      | head -1)
  machine=$(printf '%s\n' "$head_text" | sed -n 's/^machine:[[:space:]]*//p'    | head -1)

  mtime=$(get_effective_mtime "$f")

  proj=$(basename "$(dirname "$f")")
  printf 'FILE|%s|PROJ|%s|CREATED|%s|UPDATED|%s|MTIME|%s|MACHINE|%s|TITLE|%s\n' \
    "$f" "$proj" "$created" "$updated" "$mtime" "$machine" "$title"
done
