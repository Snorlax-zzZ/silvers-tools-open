#!/usr/bin/env bash
# list-checkpoints.sh
#
# 扫描 checkpoint 文件，输出DSH可一次性解析的「行格式」，
# 用来替代命令正文里原本的 `for ... do head/grep/stat ... done` 复合 shell 脚本。
#
# 在 DSH 侧它值得存在的理由**不是**「免审批白名单」——DSH 没有按命令的 allowlist。真正的理由：
#   1. 一次 bash 调用拿全量结果：少一轮来回、输出格式固定，不会漏文件或把时间算错
#   2. 跨平台差异（mac=BSD stat / Linux+git-bash=GNU stat）与 git commit time 取值集中在一处维护
#   3. 命令正文只负责 split 与展示，扫描逻辑要改只改这一份
#
# 用法：
#   list-checkpoints.sh                       # 默认：扫本地所有项目 ~/.dsh/checkpoints
#   list-checkpoints.sh --here <subdir>       # 仅扫某个项目子目录（subdir = 子目录名）
#   list-checkpoints.sh --online              # 扫云端 ~/.dsh/checkpoints-online/dsh/（DSH 命名空间下）
#   list-checkpoints.sh --online --here <sub> # 云端 DSH 命名空间 + 指定子目录
#
# 注：--online 模式下根目录锁定到仓库内 `dsh/` 子目录，避免扫到 cc/ 等其它客户端命名空间。
#     git log mtime 取值仍指向仓库根（git -C 自动溯源），跨子目录仍能拿到 commit time。
#
# 每命中一个进行中 checkpoint，输出一行（"|" 分隔，DSH直接 split 即可）：
#   FILE|<绝对路径>|PROJ|<项目目录名>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|MACHINE|<存档机>|TITLE|<标题>
#
# MACHINE 字段仅 online 版 frontmatter 有意义；本地版无此字段时输出空（"MACHINE||"）。
#
# - 过滤：仅 frontmatter status=in-progress
# - 排除：任何路径含 done/ 的（归档区）
# - mtime 取值（重要）：
#     本地模式 → 文件系统 mtime（写文件时同步刷新，是真值）
#     --online 模式 → git log 最后 commit 时间。原因：git pull 落地时会刷新 fs mtime
#                     但跟内容修改无关；commit time 跨机一致，是"谁最后动过这份 checkpoint"的真值
#     online 模式下 git log 取不到（还没 commit 的新文件）→ fallback 到 fs mtime
# - mtime 跨平台：mac=BSD stat，Linux / Windows git-bash=GNU stat
# - 没命中时空输出，不报错，不返回非零退出码

set -u

ROOT="$HOME/.dsh/checkpoints"
IS_ONLINE=0
HERE=""
HERE_SET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --online)  ROOT="$HOME/.dsh/checkpoints-online/dsh"; IS_ONLINE=1; shift ;;
    --here)
      # 缺值必须当场退出：`shift 2` 在 $#=1 时不移位且返回非零，而本脚本没开
      # set -e，循环会一直看到同一个 --here，表现为进程挂住不动（实测 SIGALRM 才杀得掉）
      if [ $# -lt 2 ]; then
        printf '错误：--here 后面要跟项目目录名\n' >&2
        exit 2
      fi
      HERE="$2"; HERE_SET=1; shift 2
      ;;
    --here=*)  HERE="${1#--here=}"; HERE_SET=1; shift ;;
    -h|--help)
      sed -n '2,34p' "$0"; exit 0 ;;
    *)         shift ;;
  esac
done

# --here 只接受单个项目目录名。用 HERE_SET 而不是 [ -n "$HERE" ] 判断，是要区分
# 「没传 --here」（合法，扫全部）和「传了但值是空」（算错了，应当报错）。
# 拒绝两类字符：
#   - 路径分隔符 / 和 \ 以及 . ..：防止跑出扫描根目录
#   - glob 元字符 * ? [ ]：它们会原样进到下面 find 的 -path "*/$HERE/*.md"，
#     而 -path 的 * 能跨 / 匹配，传个 * 就把「只扫一个项目」放大成扫全部
if [ "$HERE_SET" = "1" ]; then
  case "$HERE" in
    ""|"."|".."|*/*|*\\*|*'*'*|*'?'*|*'['*|*']'*)
      printf '错误：--here 的项目目录名不合法：%s\n' "$HERE" >&2
      exit 2
      ;;
  esac
fi

[ -d "$ROOT" ] || exit 0

SEARCH_DIR="$ROOT"
# --here 用 path 通配匹配，兼容本地版单层（ROOT/<HERE>/*.md）
# 和 online 版可能的多层（ROOT/<agent>/<HERE>/*.md）结构

# 检测 stat 风格（BSD vs GNU）
if stat -f '%Sm' / >/dev/null 2>&1; then
  STAT_FMT="bsd"
else
  STAT_FMT="gnu"
fi

# 取"有效修改时间"（详见文件头注释 mtime 取值小节）
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
