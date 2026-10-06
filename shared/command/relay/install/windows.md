# Windows 自主安装参考

> 安装模型必须按当前环境适配，不得机械复制本页命令或路径。

## 1. 先探测，不照搬 Unix

确认 Windows 版本、当前 shell（PowerShell、Command Prompt 或 Git Bash）、当前客户端及原生扩展目录。探测 `py`、`python.exe` 与 `git.exe` 的真实位置和版本；Relay CLI 要求 Python 3.11+ 与 Git for Windows。

确认源码位置、完整 source commit、`pyproject.toml` 中的版本和最终 CLI 入口。源码有未提交改动、版本不一致或目标 `runtimes/<version>/` 已存在时停止。选择当前机器稳定的启动方式，正确处理空格、反斜杠与执行策略；不要把 Unix shebang、`command -v`、`chmod`、`umask` 或某台 macOS 的绝对路径直接翻译成看似相近的 Windows 命令。

先只读检查 Relay home 的 `current.json`、`install.json`、`runtimes/`、`config.json`、`store/` 和 `work/`。发现已有安装时转入 `shared/command/relay/UPGRADE.md`，不能按首次安装覆盖。

## 2. 解析运行目录

如果存在非空 `SILVERS_RELAY_HOME`，Relay 使用它；否则 Windows 默认使用 `%LOCALAPPDATA%\Silvers\Relay`。如果 `LOCALAPPDATA` 缺失，CLI 才回退到用户目录下的 `AppData\Local\Silvers\Relay`。若采用覆盖值，必须验证从桌面启动的当前客户端也能读取它，不能只在当前 PowerShell 进程临时设置。

代码与数据必须平级隔离：

```text
<relay-home>\
├── bin\
├── runtimes\<version>\venv
├── current.json
├── install.json
├── config.json
├── store\
└── work\
```

`config.json`、`store\` 和 `work\` 均由 CLI 管理，不能装进 runtime，也不能在更新代码时重建。客户端入口只消费 `relay draft create --operation <create|update|successor|done|withdraw>` 返回的路径；需要现有棒时再传 `--relay-id` 让 contextual draft 自动写入 target，不自行拼接目录或模拟 POSIX 权限命令。

## 3. 安装版本化 runtime 与稳定 launcher

从源码构建时须保留工具仓库根 `LICENSE` 与 `shared/tool/relay/setup.py`；只搬走工具子目录会缺少根许可证。构建临时带入同一份许可证，结束后不在工具目录留副本；独立安装 wheel 或从源码分发包重建时使用包内许可文件。

先以排他方式创建全新的 `runtimes/<version>\`，再直接在最终路径用已确认的 Python 3.11+ 创建 venv。venv launcher 可能保存绝对路径，禁止在其他目录构建后整体搬家。按下述构建条件把 Relay package 装入其中，直接执行最终 venv 的 console entrypoint，核对 `relay --version` 与源码版本一致。Windows entrypoint 通常是 `venv/Scripts/relay.exe`。

Relay 没有运行时第三方依赖，但 `pyproject.toml` 声明构建后端需要 `setuptools`。安装模型必须先核对构建条件；pip 的隔离构建可能从配置的包索引获取构建依赖，不能把“无运行时依赖”理解为保证离线安装。联网构建只能使用已确认的可信来源，并遵守依赖安装授权。离线或受限网络时，使用与目标 Python 匹配、来源及版本已核实的本地 wheel，或在构建依赖已齐备的环境中使用 `--no-build-isolation`；该参数本身不会补齐依赖。缺少这些条件时报告所缺材料，不猜下载地址、不临时改全局索引。

`runtime.json` 写成前，该目录只是未完成安装，不得写入 `current.json`。失败时停止并明确报告本次新建的半成品；只能按当前授权清理它。receipt 写成后目录才视为完成且不可原地覆盖。

把 `shared/tool/relay/launcher/relay_launcher.py` 安装到稳定 `bin\`，再按当前 shell 和客户端生成稳定包装入口，通常是 `.cmd` 或等价原生入口。包装入口只启动 launcher；launcher 只读 `current.json` 并执行 runtime。不要让它读取 remote、store 或版本规则。记录所有实际 launcher 文件的相对路径和 SHA-256。

`runtimes\<version>\runtime.json` 固定记录 `runtime_schema: 1`、Relay 版本、完整 source commit、相对 entrypoint、UTC 安装时间和实际 Python 版本。

原子写入 `current.json`。JSON 内仍使用 `/` 作为跨平台相对路径分隔符：

```json
{
  "current_schema": 1,
  "entrypoint": "runtimes/<version>/venv/Scripts/relay.exe"
}
```

原子写入 `install.json`，记录 Relay home 绝对路径、launcher 文件、当前 runtime、source commit、安装时间和已确认客户端入口。每个 `clients[]` 必须记录生成该客户端适配器所依据的完整 `source_commit`；首次人工确认前 `clients` 可以为空。

通过稳定入口执行 `relay --version` 和 `relay --repo "<TOOL_SOURCE_DIR>" status`；必须验证实际入口、版本、`installation.recorded=true`、文件哈希及源码版本状态。`<TOOL_SOURCE_DIR>` 是本次安装来源工具仓的本地 checkout，公开用户使用自己的 `silvers-tools-open`，不需要私仓；`--repo` 放在 `status` 前，路径按当前 shell 正确引用。该命令比较本地源码提交，不自动获取远端最新版。源码状态为 `unavailable` 时不能宣布版本已对齐，也不能用普通业务项目中的 `relay status` 代替来源仓验收。不能只验证源码目录下的命令。

## 4. 配置独立远端

取得用户明确提供或确认的独立 Relay Git remote。跨机器使用应选择各机器都能访问的网络远端，本地路径只用于临时验证。不得创建远端，不得复用业务项目 origin/fetch/push URL，不得从其他工具猜测地址，也不得把 token、密码、query 或 fragment 写进 remote。

通过当前 shell 下已验证的稳定 CLI 入口执行一次 `relay setup --remote <已确认 remote>`。路径或 URL 的引号规则要按当前 shell 生成；不要假设 PowerShell、Command Prompt 与 Git Bash 相同。

## 5. 适配当前客户端

只为当前客户端生成三个候选显式入口。安装模型必须同时阅读三份语义模板和 `shared/skill/relay*` 共享参考源，不得原样复制任一源文件。将其转换为客户端真正支持的命令或 Skill 格式，把 `<WRITER_IDENTITY>` 替换为用户确认的稳定助手身份，填入稳定 launcher、权限执行语义、本机增量和客户端元数据，并按客户端能力禁止隐式触发；不得用 `codex`、`claude-code` 等宿主名自动代替作者身份。保留零用户参数、候选编号、接棒确认门、完整快照替换和 finally 草稿清理。`relay history` 与 `relay recall` 是接棒入口内部能力，不另装需要用户输入参数的日常入口。

当前客户端是 Codex 时，必须再阅读 `install/codex-permissions.md`，把 `<RELAY_WORK_DIR>`、`<STABLE_RELAY_LAUNCHER>` 和规则语法适配成当前 Windows/Codex 真值。权限候选仍需逐文件 diff 和用户确认；不得照搬 POSIX 路径、自动覆盖全局配置或修改其他客户端。

如果当前客户端没有与 `/relay` 或 `$relay` 完全相同的展示语法，使用它的原生等价入口并在安装报告中说明，不要伪造一个客户端无法加载的文件。

候选文件先写入临时目录。逐文件检查现有目标和本机规则，逐文件 diff，列出共享变化、Windows 平台增量、本机自定义与建议处理。只有用户明确确认后才能手工叠加；禁止覆盖式写入、`Copy-Item -Force`、`copy /Y` 或等价强制覆盖。写入后重新读取，以最终绝对路径、SHA-256 和本次参考的完整 source commit 更新该 client 的 `install.json` 回执。

## 6. 临时验证

在临时目录创建临时 Relay home 与临时 bare remote，至少验证：

- 稳定 launcher 能解析临时 `current.json`，保留带空格参数和 runtime 退出码；
- `relay --version`、runtime receipt 和 `relay status` 的安装摘要一致；
- 未提供 remote 时 setup 失败；
- status 返回预期的 Windows home；
- 草稿创建唯一，清理拒绝目录逃逸与符号链接/重解析点；
- 两个临时 store 完成 canonical JSON/派生 Markdown 成对创建、加载、更新和归档；
- successor 能在一个 CAS 中归档旧阶段、从变化量创建新阶段，并在故障时完整回滚；
- load 返回阶段契约、逐条 `phase_completion`、结构化 delta、前阶段收尾摘要、全部活动决策全文、source relation 和有界响应；
- `modify=[]` 的只读棒能通过，缺失逐条完成声明或把旧版推定 `met` 当真值会被拒绝/降级；
- history 能在一个有界响应中列 done 阶段大纲，recall 能按 relay id、revision 与 decision id 或 criteria ordinal 读取一个决策或判据变更回执；
- 手工修改或删除派生 Markdown 时 load 仍从 canonical JSON 现渲染，并返回非阻断 `document_export` 诊断；手工破坏 canonical 时读取必须失败；
- 三个客户端入口有注释、无需用户参数且只能显式触发。

验证不得向真实 remote 写 fixture，不得修改业务项目。结束时只清理安装模型明确创建的临时文件；任何需要安装依赖或更改执行策略的动作仍需遵守用户授权边界。最终报告必须逐项列出 runtime、launcher、`current.json`、`install.json`、remote 配置、客户端入口和验证证据；未获用户确认的候选入口保持未安装。
