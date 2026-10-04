# checkpoint 六件套

> 长任务跨会话续命，省 token。本地三件套与云端跨机三件套按场景组合使用。

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

文档存放：`~/.codex/checkpoints/<项目目录名>/YYYYMMDD-HHMMSS-<中文slug>.md`

## 云端跨端版（`-online` 三件套）

> 纯本地版不够用、需要 **mac ↔ Windows 跨机器接力**时用。

| 命令 | 作用 |
|---|---|
| `/checkpoint-online` | 存到 github 云端工作区 + 自动 commit/push，frontmatter 多记「环境块」 |
| `/checkpoint-load-online` | 先 pull 最新，加载时**自动把别的机器的路径/命令折算成当前机** |
| `/task-done-online` | 归档到云端 Codex 命名空间的 `done/` 子目录并 push |

- **云端仓库**：`<CHECKPOINT_REPO_URL>`
- **本地工作区**：`~/.codex/checkpoints-online/`（仓库的 clone）
- **Codex 活跃目录**：`codex/<project_key>/`；完成后归档到 `codex/done/<project_key>/`。`project_key` 取 git remote 仓库名，非 git 项目用目录名
- **多客户端隔离**：Codex 只读写 `codex/`，不会扫描或改动同仓库中 cc、zcode 等客户端的命名空间
- **同步豁免**：工作区内 git 操作已加进 permissions 白名单，无感 push/pull（仅限该目录）
- **跨机原理**：环境块（machine/os/shell/project_root）+ 项目内相对路径 + Codex 智能折算；机器相关绝对路径集中在正文「🖥️ 环境上下文」段
- 与本地版**平行独立**：两套命令、两个存储目录、互不干扰，按场景选

> ⚠️ 前提：本机能访问已配置的 `<CHECKPOINT_REPO_URL>`（用 `git ls-remote` 验证）。装的时候安装脚本会自动 clone 工作区，clone 失败会提示手动跑。

## 何时装 / 不装

| 场景 | 建议 |
|---|---|
| 本机经常跑 100k+ token 的长任务 | ✅ 装（神器） |
| 本机基本都是短任务 | ❌ 不装也行 |

## 安装步骤

### macOS

1. 拷贝 6 个 prompt 文件：
   ```bash
   mkdir -p ~/.codex/prompts
   cp prompts/checkpoint.md      ~/.codex/prompts/checkpoint.md
   cp prompts/checkpoint-load.md ~/.codex/prompts/checkpoint-load.md
   cp prompts/task-done.md       ~/.codex/prompts/task-done.md
   # 云端跨端版（-online 三件套）
   cp prompts/checkpoint-online.md      ~/.codex/prompts/checkpoint-online.md
   cp prompts/checkpoint-load-online.md ~/.codex/prompts/checkpoint-load-online.md
   cp prompts/task-done-online.md       ~/.codex/prompts/task-done-online.md
   # clone 云端工作区（首次）
   git clone <CHECKPOINT_REPO_URL> ~/.codex/checkpoints-online
   ```

2. 装扫描脚本（`checkpoint-load` 用它列 checkpoint，避免 Codex 跑 `for ... head/stat ... done` 复合命令触发权限弹窗）：
   ```bash
   mkdir -p ~/.codex/scripts
   cp scripts/list-checkpoints.sh ~/.codex/scripts/list-checkpoints.sh
   chmod +x ~/.codex/scripts/list-checkpoints.sh
   ```

3. 可选：`permissions/mac.json` 保留为 Claude Code 迁移来源的权限参考。当前 Codex 桌面环境通常不需要手工合并这个 JSON；如果你使用的 Codex 表面支持类似 `permissions.allow`，再按需参考。

4. 验证：新会话里打 `/checkpoint`，Codex 应当开始扫描会话状态准备归档。

> 懒人方案：还有现成的 `install/install-mac.sh` 可以跑（只做上面第 1、2 步 + 输出权限参考，**不会自动改全局配置**）。

### Windows

1. 拷贝 6 个 prompt 文件：
   ```powershell
   $cmdDir = "$env:USERPROFILE\.codex\prompts"
   New-Item -ItemType Directory -Force -Path $cmdDir | Out-Null
   Copy-Item prompts\checkpoint.md      $cmdDir\checkpoint.md
   Copy-Item prompts\checkpoint-load.md $cmdDir\checkpoint-load.md
   Copy-Item prompts\task-done.md       $cmdDir\task-done.md
   # 云端跨端版（-online 三件套）
   Copy-Item prompts\checkpoint-online.md      $cmdDir\checkpoint-online.md
   Copy-Item prompts\checkpoint-load-online.md $cmdDir\checkpoint-load-online.md
   Copy-Item prompts\task-done-online.md       $cmdDir\task-done-online.md
   # clone 云端工作区（首次）
   git clone <CHECKPOINT_REPO_URL> "$env:USERPROFILE\.codex\checkpoints-online"
   ```

2. 装扫描脚本（Windows 上用 git-bash 跑 .sh）：
   ```powershell
   $scriptsDir = "$env:USERPROFILE\.codex\scripts"
   New-Item -ItemType Directory -Force -Path $scriptsDir | Out-Null
   Copy-Item scripts\list-checkpoints.sh "$scriptsDir\list-checkpoints.sh" -Force
   ```

3. 可选：`permissions/windows.json` 保留为 Claude Code 迁移来源的权限参考。当前 Codex 桌面环境通常不需要手工合并这个 JSON；如果你使用的 Codex 表面支持类似 `permissions.allow`，再按需参考。

4. **⚠️ Windows 强制：给本机副本注入取时约束**

   PowerShell 的 `Get-Date` / `[DateTime]::Now` 在 Windows 上受 cold start + Defender 实时扫描影响，**单次取时可能拖到数十秒甚至挂死**——会让 `/checkpoint`、`/checkpoint-load`、`/task-done` 在写 frontmatter 时间或渲染相对时间时超时。

   Windows 安装脚本会在覆盖六个 Prompt 后自动注入一次下面的约束块；重复安装时会先用仓库源码覆盖再注入，因此 marker 不会累积。手工复制安装时，也要在本机 `~/.codex/prompts/` 下六个 Prompt 的 frontmatter 之后各追加一段（不要放进 frontmatter，避免影响命令元数据）：

   ```markdown
   <!-- WINDOWS RUNTIME CONSTRAINT (locally injected; do not commit) -->
   > **Windows time command (REQUIRED)**: use GNU date from Git Bash:
   > `date '+%Y-%m-%dT%H:%M:%S%z'`
   > **DO NOT use PowerShell Get-Date or [DateTime]::Now**: cold starts and Defender scanning can cause incompatible output, long delays, or timeouts.
   <!-- END WINDOWS RUNTIME CONSTRAINT -->
   ```

   设计原则：仓库里的 `prompts/*.md` 保持跨平台中立，约束只存在于本机副本里。注入块刻意使用纯 ASCII，兼容会把 UTF-8 无 BOM 脚本按系统 ANSI 解码的 Windows PowerShell 5.1。

5. 验证：新会话里打 `/checkpoint`。

> 懒人方案：直接运行 `install/install-windows.ps1`，它会完成 Prompt 覆盖升级、Windows 约束注入和扫描脚本安装。

## 平台差异

| | macOS | Windows |
|---|---|---|
| Codex 配置目录 | `~/.codex/` | `~/.codex/`（同样在 `$env:USERPROFILE` 下） |
| prompt 文件内容 | 跨平台一致 | 跨平台一致 |
| 权限白名单命令 | unix 命令（`head`/`find`/`grep`/`mv`） | PowerShell 命令（`Get-Content`/`Get-ChildItem`/`Move-Item`） |
| 取系统时间方式 | `date '+%Y-%m-%dT%H:%M:%S%z'`（GNU date） | **同样必须走 Git Bash GNU date**，禁用 PowerShell `Get-Date` / `[DateTime]::Now`（详见 Windows 安装第 4 步） |

prompt 文件里的路径全用 `~/` 开头，PowerShell 和 bash 都能展开，无需改prompt 文件本身。

## 卸载

```bash
rm ~/.codex/prompts/checkpoint.md
rm ~/.codex/prompts/checkpoint-load.md
rm ~/.codex/prompts/task-done.md
rm ~/.codex/prompts/checkpoint-online.md
rm ~/.codex/prompts/checkpoint-load-online.md
rm ~/.codex/prompts/task-done-online.md
rm ~/.codex/scripts/list-checkpoints.sh
```

如你额外合并过权限白名单，卸载时也把对应条目删掉。
