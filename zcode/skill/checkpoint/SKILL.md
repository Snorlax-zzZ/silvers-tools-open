---
name: checkpoint
description: Use when the user explicitly asks to "checkpoint"/"checkpoint save"/"做个 checkpoint"/"存档"/"归档当前会话状态". 本地 checkpoint 三件套之存档：把当前会话状态归档成精简 checkpoint 文档到 ~/.zcode/checkpoints/。加载/续命走 checkpoint-load，完成归档走 task-done。不要主动触发，只有用户明确要求时才执行。
---

# Checkpoint（本地存档）

长任务跨会话续命机制。把当前会话状态归档成精简 checkpoint 文档，新会话加载后 5 分钟内知道"做到哪+下一步干啥"。本 skill 只管**存档**；加载走 checkpoint-load，完成走 task-done（同套组独立技能）。

## 路径（ZCode 专属）

- **checkpoint 根目录**：`~/.zcode/checkpoints/`
- **项目目录名**：当前工作目录绝对路径，把 `/` 替换为 `-`。例：`/Users/x/Documents/foo` → `-Users-x-Documents-foo`
- **归档目录**：`~/.zcode/checkpoints/done/<项目目录名>/`（task-done 用）

## 存档步骤（checkpoint）

### 1. 计算路径
- 项目目录名 = pwd 绝对路径 `/`→`-`
- 存档目录：`~/.zcode/checkpoints/<项目目录名>/`，不存在 `mkdir -p`

### 2. 决定写哪个文件（优先级）
1. 用户传了路径参数 → 用这个（覆盖）
2. 本次对话记得"当前维护的 checkpoint 路径"（之前 load/创建过）→ 覆盖更新
3. 都没有 → 新建 `YYYYMMDD-HHMMSS-<slug>.md`

**slug 规则**：从任务标题提炼 8-15 个中文字核心描述，去标点空格。首次创建定死不改。

### 3. 写入文档

**前置（强制）**：写入前必须先 `date '+%Y-%m-%dT%H:%M:%S%z'` 拿真实时间。`updated_at` 必须用这次结果，**禁止复用上下文里的旧时间戳**（长会话时间戳漂移过 2h+）。

**Frontmatter**：
```yaml
---
project_root: <当前工作目录绝对路径>
created_at: <首次创建填，后续不变>
updated_at: <每次刷新为当前 ISO8601>
title: "<一句话任务标题 10-25 字>"
status: in-progress
---
```

**正文结构**（按需增减，不是死模板）：
- ## 任务目标（1-2 句最终结果）
- ## 当前进度（做到哪+下一步，3-5 行）
- ## 🚨 已踩过的认知陷阱（强制段，避免新会话重走弯路；每条三段式：陷阱/真相/来源；没有写"无"）
- ## 关键决策（强制段，三段式：决策/理由/来源）
- ## 关键发现（可选，技术事实/位置）
- ## Follow-up 清单（强制段，按 P0/P1/P2/longterm 分层，每条标触发条件+实施位置）
- ## 引用（只列路径不复述）
- ## 下一步建议

### 4. 记住路径
写入后记住"当前维护的 checkpoint 路径是 `<路径>`"，后续 checkpoint/task-done 默认操作它。

### 5. 汇报
```
✅ 已保存到 `<路径>`（约 X.X k token，覆盖/新建）
```

## 写作铁律

- ❌ 不粘贴文件内容、diff、commit、PR 描述
- ❌ 不抄已在 plan/ADR 里的决策
- ✅ 只记结论不记过程
- ✅ 死路也记（避免重走）
- ✅ 用项目术语

## 体积约束

目标 **3-5k token**（约 1500-2500 中文字），超 5k 必须砍。
