---
name: task-done-online
description: Use when the user explicitly asks to "task done online"/"云端任务完成"/"云端收工". online 三件套之完成：把云端 checkpoint 标记 done、git mv 到云端 done/ 归档区并 push 同步。云端存档走 checkpoint-online，云端加载走 checkpoint-load-online。本地版走 task-done，共享版走 task-done-shared。不要主动触发，只有用户明确要求时才执行。
---

# Task-Done-Online（云端完成归档）

云端 checkpoint 三件套的完成入口：任务收尾时把云端 checkpoint 标记 done、归档并同步远端。

## 云端工作区（ZCode 专属）

- **本地工作区**：`~/.zcode/checkpoints-online/`
- **归档位置**：`done/zcode/<project_key>/<文件名>`

## 完成步骤（task-done-online）

1. 确保工作区就绪 + `git -C ~/.zcode/checkpoints-online pull --ff-only` 最新；pull 失败中止不强行覆盖
2. 找 checkpoint（优先级：参数路径 > 数字编号 > 当前记的路径 > 报错）
3. 读取和修改前展开路径、消解 `.` / `..` 与符号链接；源必须位于本 clone 的 `zcode/<project_key>/` 活动目录，目标必须位于 `done/zcode/<同一 project_key>/`，拒绝其它命名空间、越界和已存在的目标。
4. 打印准备归档信息（含 machine），直接执行（不插 y/n）
5. frontmatter `status`→`done`，用本次新执行 `date` 和 `hostname` 的结果写 `done_at` + `done_machine`。
6. 只提交本次源、目标路径，保留其它文件的暂存状态：

```bash
mkdir -p ~/.zcode/checkpoints-online/done/zcode/"<project_key>"
git -C ~/.zcode/checkpoints-online mv -- "zcode/<project_key>/<文件名>" "done/zcode/<project_key>/<文件名>"
git -C ~/.zcode/checkpoints-online commit --only -m "done(zcode/<project_key>): <title> @<done_machine>" -- "zcode/<project_key>/<文件名>" "done/zcode/<project_key>/<文件名>"
git -C ~/.zcode/checkpoints-online push
```

7. 忘掉路径，汇报
