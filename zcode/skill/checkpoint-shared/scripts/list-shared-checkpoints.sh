#!/usr/bin/env bash
# 列出共享接力工作区中的进行中 checkpoint。
#
# 用法：
#   bash list-shared-checkpoints.sh
#   bash list-shared-checkpoints.sh --here <project_key>
#
# 固定扫描：~/.silvers/checkpoint-shared/shared/
# 固定排除：~/.silvers/checkpoint-shared/shared/done/
#
# 每个 checkpoint 输出一行，以 `|` 分隔：
#   FILE|...|PROJ|...|CHECKPOINT_ID|...|REVISION|...|CREATED|...|UPDATED|...
#   |COMMIT_TIME|...|LAST_CLIENT|...|LAST_MODEL|...|LAST_MACHINE|...|LAST_OS|...
#   |LAST_SHELL|...|PATH_STYLE|...|TITLE|...

set -uo pipefail

WORKTREE="$HOME/.silvers/checkpoint-shared"
ROOT="$WORKTREE/shared"
HERE=""
HERE_SUPPLIED=0
OUTPUT_FILE=""
OUTPUT_BUFFER_ACTIVE=0

usage() {
  sed -n '2,8p' "$0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --here)
      [ "$#" -ge 2 ] || {
        printf '错误：--here 需要 project_key\n' >&2
        exit 2
      }
      HERE_SUPPLIED=1
      HERE="$2"
      shift 2
      ;;
    --here=*)
      HERE_SUPPLIED=1
      HERE="${1#--here=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '错误：未知参数 %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

if [ "$HERE_SUPPLIED" -eq 1 ]; then
  [ -n "$HERE" ] || {
    printf '错误：--here 需要非空 project_key\n' >&2
    exit 2
  }
  case "$HERE" in
    .|..|*/*|*\\*)
      printf '错误：非法 project_key %s\n' "$HERE" >&2
      exit 2
      ;;
  esac
fi

scanner_error() {
  printf '错误：%s\n' "$1" >&2
}

cleanup_output_buffer() {
  if [ "$OUTPUT_BUFFER_ACTIVE" -eq 1 ]; then
    exec 1>&3
    exec 3>&-
    OUTPUT_BUFFER_ACTIVE=0
  fi
  if [ -n "$OUTPUT_FILE" ]; then
    rm -f -- "$OUTPUT_FILE" 2>/dev/null || :
  fi
}

begin_output_buffer() {
  local template="${TMPDIR:-/tmp}/list-shared-checkpoints.XXXXXX"

  if ! OUTPUT_FILE="$(mktemp "$template")"; then
    scanner_error '无法创建 checkpoint 扫描结果临时文件'
    return 1
  fi
  if ! exec 3>&1; then
    scanner_error '无法保存 checkpoint 扫描结果输出句柄'
    return 1
  fi
  if ! exec >"$OUTPUT_FILE"; then
    exec 3>&-
    scanner_error '无法打开 checkpoint 扫描结果临时文件'
    return 1
  fi
  OUTPUT_BUFFER_ACTIVE=1
}

publish_output_buffer() {
  if ! cat "$OUTPUT_FILE" >&3; then
    scanner_error '无法写出 checkpoint 扫描结果'
    return 1
  fi
}

trap cleanup_output_buffer EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

require_readable_directory() {
  local directory="$1"

  [ -d "$directory" ] || {
    scanner_error "扫描路径不是目录：$directory"
    return 1
  }
  [ -r "$directory" ] && [ -x "$directory" ] || {
    scanner_error "扫描目录不可读：$directory"
    return 1
  }
}

frontmatter_value() {
  local file="$1"
  local key="$2"

  awk -v key="$key" '
    NR == 1 {
      line = $0
      sub(/\r$/, "", line)
      if (line != "---") {
        exit 0
      }
      opened = 1
      next
    }

    opened {
      line = $0
      sub(/\r$/, "", line)
      if (line == "---") {
        if (found) {
          print value
        }
        exit 0
      }

      prefix = key ":"
      if (!found && index(line, prefix) == 1) {
        value = substr(line, length(prefix) + 1)
        sub(/^[[:space:]]*/, "", value)
        found = 1
      }
    }
  ' "$file"
}

strip_quotes() {
  local value="$1"
  case "$value" in
    \"*\") value="${value#\"}"; value="${value%\"}" ;;
    \'*\') value="${value#\'}"; value="${value%\'}" ;;
  esac
  printf '%s' "$value"
}

sanitize_display() {
  local value="$1"
  value="${value//$'\r'/ }"
  value="${value//$'\n'/ }"
  value="${value//|/ }"
  printf '%s' "$value"
}

filesystem_mtime() {
  local file="$1"
  local value

  if stat -f '%Sm' / >/dev/null 2>&1; then
    if ! value="$(stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%S%z' "$file" 2>/dev/null)"; then
      scanner_error "无法读取 checkpoint mtime：$file"
      return 1
    fi
  else
    if ! value="$(stat -c '%y' "$file" 2>/dev/null)"; then
      scanner_error "无法读取 checkpoint mtime：$file"
      return 1
    fi
    if ! value="$(printf '%s' "$value" | sed 's/ /T/; s/ //g')"; then
      scanner_error "无法格式化 checkpoint mtime：$file"
      return 1
    fi
  fi

  [ -n "$value" ] || {
    scanner_error "checkpoint mtime 为空：$file"
    return 1
  }
  printf '%s' "$value"
}

effective_commit_time() {
  local file="$1"
  local relative_path="${file#"$WORKTREE"/}"
  local commit_time

  if ! commit_time="$(git -C "$WORKTREE" log -1 --pretty=format:'%cI' -- "$relative_path" 2>/dev/null)"; then
    scanner_error "无法读取 checkpoint git commit time：$file"
    return 1
  fi
  if [ -n "$commit_time" ]; then
    printf '%s' "$commit_time"
  else
    filesystem_mtime "$file"
  fi
}

scan_checkpoint() {
  local file="$1"
  local status project checkpoint_id revision created updated commit_time
  local last_client last_model last_machine last_os last_shell path_style title

  case "$file" in
    *'|'*|*$'\r'*|*$'\n'*)
      scanner_error 'checkpoint FILE 路径包含非法的管道符、CR 或 LF'
      return 1
      ;;
  esac

  [ -r "$file" ] || {
    scanner_error "checkpoint 文件不可读：$file"
    return 1
  }

  if ! status="$(frontmatter_value "$file" status)"; then
    scanner_error "无法读取 checkpoint frontmatter：$file"
    return 1
  fi
  [ "$status" = 'in-progress' ] || return 0

  if ! project="$(frontmatter_value "$file" project_key)"; then
    scanner_error "无法读取 checkpoint frontmatter：$file"
    return 1
  fi
  [ -n "$project" ] || project="$(basename "$(dirname "$file")")"

  if ! checkpoint_id="$(frontmatter_value "$file" checkpoint_id)" ||
    ! revision="$(frontmatter_value "$file" revision)" ||
    ! created="$(frontmatter_value "$file" created_at)" ||
    ! updated="$(frontmatter_value "$file" updated_at)" ||
    ! last_client="$(frontmatter_value "$file" last_client)" ||
    ! last_model="$(frontmatter_value "$file" last_model)" ||
    ! last_machine="$(frontmatter_value "$file" last_machine)" ||
    ! last_os="$(frontmatter_value "$file" last_os)" ||
    ! last_shell="$(frontmatter_value "$file" last_shell)" ||
    ! path_style="$(frontmatter_value "$file" path_style)" ||
    ! title="$(frontmatter_value "$file" title)"; then
    scanner_error "无法读取 checkpoint frontmatter：$file"
    return 1
  fi
  title="$(strip_quotes "$title")"
  if ! commit_time="$(effective_commit_time "$file")"; then
    return 1
  fi

  if ! printf 'FILE|%s|PROJ|%s|CHECKPOINT_ID|%s|REVISION|%s|CREATED|%s|UPDATED|%s|COMMIT_TIME|%s|LAST_CLIENT|%s|LAST_MODEL|%s|LAST_MACHINE|%s|LAST_OS|%s|LAST_SHELL|%s|PATH_STYLE|%s|TITLE|%s\n' \
    "$file" \
    "$(sanitize_display "$project")" \
    "$(sanitize_display "$checkpoint_id")" \
    "$(sanitize_display "$revision")" \
    "$(sanitize_display "$created")" \
    "$(sanitize_display "$updated")" \
    "$(sanitize_display "$commit_time")" \
    "$(sanitize_display "$last_client")" \
    "$(sanitize_display "$last_model")" \
    "$(sanitize_display "$last_machine")" \
    "$(sanitize_display "$last_os")" \
    "$(sanitize_display "$last_shell")" \
    "$(sanitize_display "$path_style")" \
    "$(sanitize_display "$title")"; then
    scanner_error '无法写出 checkpoint 扫描结果'
    return 1
  fi
}

scan_project_directory() {
  local project_directory="$1"
  local file

  require_readable_directory "$project_directory" || return 1

  for file in "$project_directory"/*.md; do
    [ -L "$file" ] && continue
    if ! path_exists "$file"; then
      scanner_error "枚举到的 checkpoint 已不存在：$file"
      return 1
    fi
    [ -f "$file" ] || continue
    scan_checkpoint "$file" || return 1
  done

  require_readable_directory "$project_directory"
}

shopt -s nullglob dotglob

if ! path_exists "$ROOT"; then
  exit 0
fi
[ ! -L "$ROOT" ] || {
  scanner_error "shared 根目录不能是符号链接：$ROOT"
  exit 1
}
require_readable_directory "$ROOT" || exit 1

if [ "$HERE_SUPPLIED" -eq 1 ]; then
  SEARCH_ROOT="$ROOT/$HERE"
  if ! path_exists "$SEARCH_ROOT"; then
    exit 0
  fi
  [ ! -L "$SEARCH_ROOT" ] || {
    scanner_error "project 目录不能是符号链接：$SEARCH_ROOT"
    exit 1
  }
fi

begin_output_buffer || exit 1

if [ "$HERE_SUPPLIED" -eq 1 ]; then
  scan_project_directory "$SEARCH_ROOT" || exit 1
else
  for SEARCH_ROOT in "$ROOT"/*; do
    [ "${SEARCH_ROOT##*/}" = 'done' ] && continue
    [ -L "$SEARCH_ROOT" ] && continue
    [ -d "$SEARCH_ROOT" ] || continue
    scan_project_directory "$SEARCH_ROOT" || exit 1
  done

  require_readable_directory "$ROOT" || exit 1
fi

publish_output_buffer || exit 1
