---
name: task-done
description: Use when the user explicitly asks to "task done"/"任务完成"/"本地收工". 本地 checkpoint 三件套之完成：把本地 checkpoint 标记 done 并归档到 done/ 目录。云端版走 task-done-online，共享版走 task-done-shared。不要主动触发，只有用户明确要求时才执行。
---

# Task-Done（本地完成归档）

本地 checkpoint 三件套的完成入口：任务收尾时把 checkpoint 标记 done 并归档。

## 路径（ZCode 专属）

- **checkpoint 根目录**：`~/.zcode/checkpoints/`
- **项目目录名**：当前工作目录绝对路径，把 `/` 替换为 `-`
- **归档目录**：`~/.zcode/checkpoints/done/<项目目录名>/`

## 完成步骤（task-done）

1. 找 checkpoint（优先级：参数路径 > 数字编号 > 当前记的路径 > 报错）
2. 打印准备归档信息，直接执行（不插 y/n，用户主动喊即确认）
3. frontmatter `status`→`done`，加 `done_at`
4. `mv` 到 `~/.zcode/checkpoints/done/<项目目录名>/`
5. 忘掉当前 checkpoint 路径
