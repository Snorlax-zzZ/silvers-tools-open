# checkpoint-shared — 公共接力三件套（ZCode适配版）

> 给多个模型 / 客户端 / 机器**顺序接力同一个任务**：一棒保存 → 另一棒接棒 → 最后一棒归档。与本地 [checkpoint](../checkpoint/)、[checkpoint-online](../checkpoint-online/) 完全并行，只复用同一个 git 远端。

## 来源与适配

来源：[shared/command/checkpoint/](../../../shared/command/checkpoint/)（自主安装模板，2026-07-10 入库）。该目录的 README + design.md + 三份命令模板是协议 SSOT；本目录是按「自主安装模板」流程转换的 zcode 原生格式（skill 而非 slash command）。

| 维度 | 模板原文 | zcode 适配 |
|---|---|---|
| 载体 | `/checkpoint-shared` 等 slash command | skill（用户说关键词触发，description 写明不主动） |
| `<client_name>` | 安装时硬编码 | **`zcode`** |
| 扫描脚本 | `<installed-script-path>` 占位 | `~/.zcode/scripts/list-shared-checkpoints.sh` |
| 工具名 | Read / Write / Bash | ZCode原生 Read / Write / Edit / Bash |
| 三个操作 | 三条命令 | 三个独立技能入口（checkpoint-shared / checkpoint-shared-load / task-done-shared） |

**协议规则零改动**：公共路径（`~/.silvers/checkpoint-shared/`）、远端、schema v1、revision 校验、7k token 上限、九个必备章节、`git pull --ff-only`、安全脱敏等全部保留（SKILL.md 内有「红线速查」）。

## 与另两个 checkpoint 套件的关系

| 套组 | 工作区 | 用途 |
|---|---|---|
| checkpoint | `~/.zcode/checkpoints/` | 本机跨会话续命 |
| checkpoint-online | `~/.zcode/checkpoints-online/`（`zcode/` 命名空间） | 跨机器云端接力（zcode 自己的命名空间） |
| **checkpoint-shared** | `~/.silvers/checkpoint-shared/`（`shared/` 命名空间，全客户端共用） | **跨客户端 / 跨模型**公共接力 |

## 扫描脚本

`scripts/list-shared-checkpoints.sh` 与 `shared/command/checkpoint/scripts/` 上游**字节一致**（脚本本身客户端中立：扫描路径 `~/.silvers/checkpoint-shared/shared/` 写死，无需适配）。上游改了脚本时同步拷贝过来，不单独改本副本。

## 安装（macOS / Windows Git Bash 通用）

```bash
# 1. 扫描脚本
mkdir -p ~/.zcode/scripts
cp zcode/skill/checkpoint-shared/scripts/list-shared-checkpoints.sh ~/.zcode/scripts/
chmod +x ~/.zcode/scripts/list-shared-checkpoints.sh   # Windows 省略，用 bash <path> 调
bash -n ~/.zcode/scripts/list-shared-checkpoints.sh

# 2. 三个技能（存棒=根 SKILL.md，接棒/收棒=子目录，各自独立技能入口）
mkdir -p ~/.zcode/skills/checkpoint-shared ~/.zcode/skills/checkpoint-shared-load ~/.zcode/skills/task-done-shared
cp zcode/skill/checkpoint-shared/SKILL.md ~/.zcode/skills/checkpoint-shared/SKILL.md
cp zcode/skill/checkpoint-shared/checkpoint-shared-load/SKILL.md ~/.zcode/skills/checkpoint-shared-load/SKILL.md
cp zcode/skill/checkpoint-shared/task-done-shared/SKILL.md ~/.zcode/skills/task-done-shared/SKILL.md

# 3. 公共工作区（已存在则跳过；不得复用任何 checkpoints-online clone）
ls ~/.silvers/checkpoint-shared/.git 2>/dev/null || \
  git clone <CHECKPOINT_REPO_URL> ~/.silvers/checkpoint-shared
```

与 checkpoint / checkpoint-online 不同，本 skill 的运行时块是**双平台判断式**（darwin/linux 走 Bash 语义，MINGW* 走 Git Bash 约束），仓库副本即跨平台中立，**不需要**再往本机副本注入 Windows 约束块。

## 验证

```bash
bash ~/.zcode/scripts/list-shared-checkpoints.sh --help        # 用法输出
# 在临时存档目录验证扫描行为；本包不附带来源仓库测试脚本
bash ~/.zcode/scripts/list-shared-checkpoints.sh               # 只读扫真实公共工作区
```

重启 ZCode 后新会话可触发（skill 随会话启动加载，当前会话不热加载）。
