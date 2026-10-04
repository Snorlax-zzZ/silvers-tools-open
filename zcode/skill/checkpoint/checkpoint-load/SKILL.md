---
name: checkpoint-load
description: Use when the user explicitly asks to "checkpoint load"/"checkpoint-load"/"加载 checkpoint"/"列出 checkpoint"/"续命". 本地 checkpoint 三件套之加载：列出/加载 ~/.zcode/checkpoints/ 下进行中的 checkpoint，新会话续命。存档走 checkpoint，完成走 task-done。云端版走 checkpoint-load-online，共享版走 checkpoint-shared-load。不要主动触发，只有用户明确要求时才执行。
---

# Checkpoint-Load（本地加载/续命）

本地 checkpoint 三件套的加载入口：列出/加载 `~/.zcode/checkpoints/` 下进行中的 checkpoint，新会话加载后 5 分钟内知道"做到哪+下一步干啥"。

## 路径（ZCode 专属）

- **checkpoint 根目录**：`~/.zcode/checkpoints/`
- **项目目录名**：当前工作目录绝对路径，把 `/` 替换为 `-`。例：`/Users/x/Documents/foo` → `-Users-x-Documents-foo`

## 加载步骤（checkpoint-load）

1. **参数**：空=列所有项目 in-progress；`--here`=当前项目；数字 N=列表第 N 个；文件路径=直接读
2. **扫描**：跑 `bash ~/.zcode/scripts/list-checkpoints.sh`（或 `--here <项目目录名>`）
   - 输出格式：`FILE|<路径>|PROJ|<项目>|CREATED|<iso>|UPDATED|<iso>|MTIME|<iso>|MACHINE|<空>|TITLE|<标题>`
3. **双时间校验**：UPDATED（frontmatter）vs MTIME（文件系统），偏差>5min 用 max 排序+⚠️标注
4. **显示**：最多 8 个，两个时间都显示，当前项目 ⭐ 高亮
5. **读取选中文件**，记住路径，复述对齐（任务/进度/下一步），等确认后执行

后续同会话的覆盖存档走 checkpoint，完成归档走 task-done（默认操作本次记住的路径）。
