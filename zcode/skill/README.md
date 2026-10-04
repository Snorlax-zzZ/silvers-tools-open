# zcode — checkpoint Skill 安装说明

ZCode 是 AI 编程客户端，获取与安装方法见 [官方安装文档](https://zcode.z.ai/cn/docs/install)。
本目录适用于 **ZCode Agent** 的用户级 Skill 机制，技能目录为
`~/.zcode/skills/<name>/SKILL.md`，官方机制说明见 [Skills 文档](https://zcode.z.ai/cn/docs/skill)。
安装下方技能和依赖后，在 ZCode Agent 会话中明确要求存档、加载或完成归档，并确认对应技能被加载。

| Skill | 用途 |
|---|---|
| [`checkpoint/`](checkpoint/) | 本地存档三件套：保存 / 加载 / 完成归档，跨会话续命 |
| [`checkpoint-online/`](checkpoint-online/) | 云端三件套：存档落到你自己的 Git 仓库，跨机器接力 |
| [`checkpoint-shared/`](checkpoint-shared/README.md) | 公共接力三件套：不同客户端按顺序接棒 |

## 安装（macOS / Windows Git Bash）

使用云端或公共接力前，先阅读根目录的 [存档数据与可见范围](../../README.md#存档数据与可见范围)。

```bash
# 1. 装三个系列的九个独立技能（每个技能独立安装）
for suite in checkpoint checkpoint-online checkpoint-shared; do
  for skill_file in "zcode/skill/$suite/SKILL.md" "zcode/skill/$suite"/*/SKILL.md; do
    [ -f "$skill_file" ] || continue
    skill_name="$(basename "$(dirname "$skill_file")")"
    mkdir -p ~/.zcode/skills/"$skill_name"
    cp "$skill_file" ~/.zcode/skills/"$skill_name"/SKILL.md
  done
done

# 2. 装扫描脚本（本地、云端加载技能都依赖它列出已有存档）
mkdir -p ~/.zcode/scripts
cp zcode/skill/checkpoint/scripts/list-checkpoints.sh ~/.zcode/scripts/list-checkpoints.sh
chmod +x ~/.zcode/scripts/list-checkpoints.sh
cp zcode/skill/checkpoint-shared/scripts/list-shared-checkpoints.sh ~/.zcode/scripts/list-shared-checkpoints.sh
chmod +x ~/.zcode/scripts/list-shared-checkpoints.sh

# 3. 只有用 checkpoint-online 才需要：clone 你自己的云端存档仓库
git clone <CHECKPOINT_REPO_URL> ~/.zcode/checkpoints-online
```

安装使用 `zcode/skill/checkpoint/scripts/list-checkpoints.sh` 这份源脚本。
本地扫描 `~/.zcode/checkpoints`，云端扫描 `~/.zcode/checkpoints-online` 整个仓库，
同时列出 `cc/`、`zcode/` 等命名空间的存档，与云端加载技能的行为一致。
`zcode/scripts/list-checkpoints.sh` 保留为兼容入口；不要用硬编码 `~/.claude/` 的 cc 脚本替代。

第 3 步里的 `<CHECKPOINT_REPO_URL>` 是占位符，不是可用地址。先自己建一个 Git 仓库
用来存 checkpoint（私有仓即可），用 `git ls-remote <你的仓库地址> HEAD` 确认能读到再执行。
只用本地三件套的话跳过这步即可。公共接力需要另一个独立 clone，按 [公共接力安装说明](checkpoint-shared/README.md) 设置，不复用 checkpoints-online。

Windows 在 Git Bash 中执行同一组命令。

安装后应有 `checkpoint`、`checkpoint-load`、`task-done`、`checkpoint-online`、`checkpoint-load-online`、`task-done-online` 以及 `checkpoint-shared`、`checkpoint-shared-load`、`task-done-shared` 九个独立技能入口。只复制套组根目录的 `SKILL.md` 会漏掉加载和完成归档技能。

## 与其他客户端版本的差异

同一个云端仓库可以被多个客户端共用，靠顶层命名空间区分来源，互不干扰：

| | 存档路径 | 云端命名空间 | 触发方式 |
|---|---|---|---|
| zcode | `~/.zcode/` | `zcode/<project_key>/` | Skill，说出关键词才触发 |
| Claude Code | `~/.claude/` | `cc/<project_key>/` | slash command |
| Codex | `~/.codex/` | `codex/<project_key>/` | prompt |

Skill 的描述里写明了「不要主动触发」——它不会在你没要求的时候自己去写存档。

## 验证

先检查九个入口是否齐全：

```bash
for skill_name in checkpoint checkpoint-load task-done checkpoint-online checkpoint-load-online task-done-online checkpoint-shared checkpoint-shared-load task-done-shared; do
  test -f ~/.zcode/skills/"$skill_name"/SKILL.md || { echo "缺少技能：$skill_name"; exit 1; }
done
```

装完重启 zcode，分别触发存档、加载和完成归档，确认对应 Skill 能被加载；云端操作需要先配置自己的存档仓库。
Skill 没有显式的加载计数日志，触发一次是最直接的验证方式。
