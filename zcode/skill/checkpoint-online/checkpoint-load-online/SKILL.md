---
name: checkpoint-load-online
description: Use when the user explicitly asks to "checkpoint load online"/"云端加载"/"从云端加载"/"云端续命". online 三件套之加载：从云端列出/加载 checkpoint（可只读查看其它客户端命名空间），跨机器自动折算路径与命令。云端存档走 checkpoint-online，云端完成走 task-done-online。本地版走 checkpoint-load，共享版走 checkpoint-shared-load。不要主动触发，只有用户明确要求时才执行。
---

# Checkpoint-Load-Online（云端加载/跨机续命）

云端 checkpoint 三件套的加载入口：从 github 仓库的 zcode clone 拉最新，列出/加载 checkpoint（含跨机折算）。

## 云端工作区（ZCode 专属）

- **仓库**：`<CHECKPOINT_REPO_URL>`
- **本地工作区**：`~/.zcode/checkpoints-online/`（ZCode 专属 clone，与 cc 的分开）
- **命名空间**：zcode 的存档在 `zcode/<project_key>/`

## 加载步骤（checkpoint-load-online）

1. **确保工作区就绪 + pull 最新**：
   - 工作区不存在 → `git clone <CHECKPOINT_REPO_URL> ~/.zcode/checkpoints-online`
   - 已存在 → `git -C ~/.zcode/checkpoints-online pull --ff-only`；失败/冲突 → 告诉用户「云端拉取异常」，中止
2. **算当前 project_key**：git 仓库 → `git remote get-url origin` 仓库名去 `.git`；非 git → `pwd` 的 basename
3. **路径边界**：读取前解析绝对路径与符号链接，必须留在 `~/.zcode/checkpoints-online/` 内。其它命名空间只作只读参考，不记为可更新/归档的当前路径；继续写入应新建 `zcode/<project_key>/` 存档。
4. **参数**：空=列所有；`--here`=当前项目；数字 N=第 N 个；路径=直接读
5. **扫描**：默认 `bash ~/.zcode/scripts/list-checkpoints.sh --online`；`--here` 时追加 `--here <当前 project_key>`
   - 注意：online 列表会扫到 cc 的存档（`cc/<project_key>/`）和 zcode 的（`zcode/<project_key>/`）；用 FILE 完整路径区分客户端命名空间，PROJ 仍是项目目录名
6. **跨机器折算**（online 核心）：
   - 同机（machine 相同）→ 直接用
   - 不同机 → project_root 用当前 pwd 重算；环境上下文里的路径/命令折算成当前机等价；没把握的标「待确认」
7. 读取，按命名空间边界决定是否记为可维护路径，复述对齐（含折算结果 + 待确认项），等确认后执行

后续同会话的云端覆盖存档走 checkpoint-online，云端完成归档走 task-done-online（默认操作本次记住的路径）。
