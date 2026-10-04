# checkpoint 三件套

> 长任务跨会话续命，省 token。`/checkpoint` + `/checkpoint-load` + `/task-done` 组合使用。

## 用途

- 长任务跑到 200k+ token 时，`/compact` 不省 token（compact 那一刀消耗 ≈ 全部历史 + 摘要）
- 真正省 token 的姿势：**主动归档成精简文档 → 开新会话 → 加载续命**
- 任务完成后归档到 `done/` 子目录，可追溯

完整原理见本 README 与本套件的命令模板正文。

## 三个命令

| 命令 | 作用 |
|---|---|
| `/checkpoint` | 把当前会话状态归档成 3-5k token 的精简文档 |
| `/checkpoint-load` | 在新会话里加载一份 checkpoint 继续 |
| `/task-done` | 任务完成，归档 checkpoint 到 `done/` 子目录 |

文档存放：`~/.claude/checkpoints/<项目目录名>/YYYYMMDD-HHMMSS-<中文slug>.md`

## 云端跨端版（`-online` 三件套）

> 纯本地版不够用、需要 **mac ↔ Windows 跨机器接力**时用。

| 命令 | 作用 |
|---|---|
| `/checkpoint-online` | 存到 github 云端工作区 + 自动 commit/push，frontmatter 多记「环境块」 |
| `/checkpoint-load-online` | 先 pull 最新，加载时**自动把别的机器的路径/命令折算成当前机** |
| `/task-done-online` | 归档到云端 `done/` 子目录并 push |

- **云端仓库**：`<CHECKPOINT_REPO_URL>`
- **本地工作区**：`~/.claude/checkpoints-online/`（仓库的 clone），按 `project_key` 分目录（git remote 仓库名 / 非 git 用目录名），让同一项目在不同机器落到同一目录
- **同步豁免**：工作区内 git 操作已加进 permissions 白名单，无感 push/pull（仅限该目录）
- **跨机原理**：环境块（machine/os/shell/project_root）+ 项目内相对路径 + cc 智能折算；机器相关绝对路径集中在正文「🖥️ 环境上下文」段
- 与本地版**平行独立**：两套命令、两个存储目录、互不干扰，按场景选

> ⚠️ 前提：本机能访问已配置的 `<CHECKPOINT_REPO_URL>`（用 `git ls-remote` 验证）。装的时候安装脚本会自动 clone 工作区，clone 失败会提示手动跑。

## 何时装 / 不装

| 场景 | 建议 |
|---|---|
| 本机经常跑 100k+ token 的长任务 | ✅ 装（神器） |
| 本机基本都是短任务 | ❌ 不装也行 |

## 安装步骤

### macOS

1. 拷贝三个命令文件：
   ```bash
   mkdir -p ~/.claude/commands
   cp commands/checkpoint.md      ~/.claude/commands/checkpoint.md
   cp commands/checkpoint-load.md ~/.claude/commands/checkpoint-load.md
   cp commands/task-done.md       ~/.claude/commands/task-done.md
   # 云端跨端版（-online 三件套）
   cp commands/checkpoint-online.md      ~/.claude/commands/checkpoint-online.md
   cp commands/checkpoint-load-online.md ~/.claude/commands/checkpoint-load-online.md
   cp commands/task-done-online.md       ~/.claude/commands/task-done-online.md
   # clone 云端工作区（首次）
   git clone <CHECKPOINT_REPO_URL> ~/.claude/checkpoints-online
   ```

2. 装扫描脚本（`checkpoint-load` 用它列 checkpoint，避免 cc 跑 `for ... head/stat ... done` 复合命令触发权限弹窗）：
   ```bash
   mkdir -p ~/.claude/scripts
   cp scripts/list-checkpoints.sh ~/.claude/scripts/list-checkpoints.sh
   chmod +x ~/.claude/scripts/list-checkpoints.sh
   ```

3. 把 `permissions/mac.json` 里的条目合并到 `~/.claude/settings.json` 的 `permissions.allow` 数组（手动粘贴或脚本 merge）。

4. 验证：新会话里打 `/checkpoint`，cc 应当开始扫描会话状态准备归档。

> 💡 懒人方案：还有现成的 `install/install-mac.sh` 可以跑（只做上面第 1、2 步 + 输出第 3 步的权限片段，**不会自动改 settings.json**，用户自己贴）。

### Windows

1. 拷贝三个命令文件：
   ```powershell
   $cmdDir = "$env:USERPROFILE\.claude\commands"
   New-Item -ItemType Directory -Force -Path $cmdDir | Out-Null
   Copy-Item commands\checkpoint.md      $cmdDir\checkpoint.md
   Copy-Item commands\checkpoint-load.md $cmdDir\checkpoint-load.md
   Copy-Item commands\task-done.md       $cmdDir\task-done.md
   # 云端跨端版（-online 三件套）
   Copy-Item commands\checkpoint-online.md      $cmdDir\checkpoint-online.md
   Copy-Item commands\checkpoint-load-online.md $cmdDir\checkpoint-load-online.md
   Copy-Item commands\task-done-online.md       $cmdDir\task-done-online.md
   # clone 云端工作区（首次）
   git clone <CHECKPOINT_REPO_URL> "$env:USERPROFILE\.claude\checkpoints-online"
   ```

2. 装扫描脚本（Windows 上用 git-bash 跑 .sh）：
   ```powershell
   $scriptsDir = "$env:USERPROFILE\.claude\scripts"
   New-Item -ItemType Directory -Force -Path $scriptsDir | Out-Null
   Copy-Item scripts\list-checkpoints.sh "$scriptsDir\list-checkpoints.sh" -Force
   ```

3. 把 `permissions/windows.json` 里的条目合并到 `%USERPROFILE%\.claude\settings.json` 的 `permissions.allow` 数组。

4. **⚠️ Windows 强制：装后给本机副本注入取时约束**

   PowerShell 的 `Get-Date` / `[DateTime]::Now` 在 Windows 上受 cold start + Defender 实时扫描影响，**单次取时可能拖到数十秒甚至挂死**——会让 `/checkpoint`、`/checkpoint-load`、`/task-done` 在写 frontmatter 时间或渲染相对时间时超时。

   cc 装完命令文件后，**在本机 `~/.claude/commands/` 下的 `checkpoint.md` / `checkpoint-load.md` / `task-done.md` 三个文件第一行 description 之后各追加一段约束块**（不要插到第一行，会顶掉 description 让命令列表显示错乱）：

   ```markdown
   <!-- WINDOWS RUNTIME CONSTRAINT (本机自动注入,不要 commit 回仓库) -->
   > ⚠️ **取系统时间方式（Windows 强制）**：用 Git Bash 自带 GNU date：
   > `date '+%Y-%m-%dT%H:%M:%S%z'`
   > **禁止**走 PowerShell `Get-Date` / `[DateTime]::Now` —— cold start + Defender 实时扫描会拖到超时(实测可达数十秒甚至挂死)。
   <!-- END WINDOWS RUNTIME CONSTRAINT -->
   ```

   设计原则：仓库里的 `commands/*.md` 保持跨平台中立，约束只存在于本机副本里。

5. 验证：新会话里打 `/checkpoint`。

> 💡 懒人方案：现成的 `install/install-windows.ps1` 帮你做第 1、2 步（拷贝命令文件 + 扫描脚本）。第 3 步（权限合并）和第 4 步（约束注入）目前脚本不自动做,需手动完成。

## 平台差异

| | macOS | Windows |
|---|---|---|
| Claude Code 配置目录 | `~/.claude/` | `~/.claude/`（同样在 `$env:USERPROFILE` 下） |
| 命令文件内容 | 跨平台一致 | 跨平台一致 |
| 权限白名单命令 | unix 命令（`head`/`find`/`grep`/`mv`） | PowerShell 命令（`Get-Content`/`Get-ChildItem`/`Move-Item`） |
| 取系统时间方式 | `date '+%Y-%m-%dT%H:%M:%S%z'`（GNU date） | **同样必须走 Git Bash GNU date**，禁用 PowerShell `Get-Date` / `[DateTime]::Now`（详见 Windows 安装第 4 步） |

命令文件里的路径全用 `~/` 开头，PowerShell 和 bash 都能展开，无需改命令文件本身。

## 卸载

```bash
rm ~/.claude/commands/checkpoint.md
rm ~/.claude/commands/checkpoint-load.md
rm ~/.claude/commands/task-done.md
# 云端跨端版（装过 -online 三件套才需要删）
rm ~/.claude/commands/checkpoint-online.md
rm ~/.claude/commands/checkpoint-load-online.md
rm ~/.claude/commands/task-done-online.md
rm ~/.claude/scripts/list-checkpoints.sh
```

权限白名单条目用户自己从 `~/.claude/settings.json` 里删。
