# macOS / Linux 自主安装参考

> 安装模型必须按当前环境适配，不得机械复制本页命令或路径。

## 1. 先探测，不先写入

确认实际系统、shell、当前客户端、客户端原生扩展目录、`python3` 版本和 `git` 可用性。Relay CLI 要求 Python 3.11+；如果当前解释器不满足，报告缺项并按用户授权决定安装方式，不得静默安装运行时或改系统 Python。

确认源码位置、源码 commit、`pyproject.toml` 中的 Relay 版本和最终 CLI 入口。安装来源必须能对应到一个完整 commit；源码有未提交改动、版本号互相不一致或目标 `runtimes/<version>/` 已存在时停止，不把不同内容装进同一版本目录。

先只读检查 Relay home 是否已有 `current.json`、`install.json`、`runtimes/`、`config.json`、`store/` 和 `work/`。若已存在安装状态，改读 `shared/command/relay/UPGRADE.md`，不得按首次安装流程覆盖。

## 2. 解析运行目录

如果存在非空 `SILVERS_RELAY_HOME`，Relay 使用它；否则 macOS/Linux 默认使用 `~/.silvers/relay`。若采用覆盖值，必须验证从 GUI 或桌面启动的当前客户端也能继承它，不能只在安装 shell 中临时 export。由 CLI 解析和创建 `config.json`、`store/`、`work/`，客户端模板不得自行拼接这些路径，也不得自行管理草稿权限。

代码和数据必须按下列语义平级隔离：

```text
<relay-home>/
├── bin/
├── runtimes/<version>/venv
├── current.json
├── install.json
├── config.json
├── store/
└── work/
```

安装 runtime 不得先创建、搬移或清空 `config.json`、`store/`、`work/`。

## 3. 安装版本化 runtime 与稳定 launcher

从源码构建时须保留工具仓库根 `LICENSE` 与 `shared/tool/relay/setup.py`；只搬走工具子目录会缺少根许可证。构建临时带入同一份许可证，结束后不在工具目录留副本；独立安装 wheel 或从源码分发包重建时使用包内许可文件。

先以排他方式创建一个全新的 `runtimes/<version>/`，再直接在最终路径创建 `venv`。Python venv 和 console script 可能保存绝对路径，禁止先在其他位置创建后整体搬家。按下述构建条件把当前 Relay package 装入该 venv，直接执行最终 venv 的 entrypoint，核对 `relay --version` 与源码版本一致。

Relay 没有运行时第三方依赖，但 `pyproject.toml` 声明构建后端需要 `setuptools`。安装模型必须先核对构建条件；pip 的隔离构建可能从配置的包索引获取构建依赖，不能把“无运行时依赖”理解为保证离线安装。联网构建只能使用已确认的可信来源，并遵守依赖安装授权。离线或受限网络时，使用与目标 Python 匹配、来源及版本已核实的本地 wheel，或在构建依赖已齐备的环境中使用 `--no-build-isolation`；该参数本身不会补齐依赖。缺少这些条件时报告所缺材料，不猜下载地址、不临时改全局索引。

在 runtime receipt 写成前，该目录只是未完成安装，绝不能写入 `current.json`。任何步骤失败都要停止并报告这个明确的新建目录；只能按当前授权清理本次创建的半成品。`runtime.json` 写入后版本目录才标记为完成并不可原地覆盖。

把 `shared/tool/relay/launcher/relay_launcher.py` 安装到稳定的 `bin/`。再按当前 shell 生成一个稳定调用入口；它只负责用已确认的 Python 启动 launcher，不能依赖源码仓库当前目录。记录所有实际 launcher 文件的相对路径与 SHA-256。

在 `runtimes/<version>/runtime.json` 写入固定字段：

- `runtime_schema: 1`；
- `relay_version`；
- 完整 `source_commit`；
- 相对 runtime 根的 `entrypoint`，通常是 `venv/bin/relay`；
- UTC `installed_at`；
- 实际 `python_version`。

原子写入 `current.json`：

```json
{
  "current_schema": 1,
  "entrypoint": "runtimes/<version>/venv/bin/relay"
}
```

再原子写入 `install.json`，记录 Relay home 绝对路径、所有 launcher 文件与 SHA-256、当前 runtime、source commit、安装时间和已确认客户端入口。每个 `clients[]` 必须记录生成该客户端适配器所依据的完整 `source_commit`；首次写入客户端入口前，`clients` 可以为空。

通过稳定入口执行 `relay --version`，然后执行 `relay --repo "<TOOL_SOURCE_DIR>" status`；必须看到预期版本和 `installation.recorded=true`，并核对文件哈希及源码版本状态。`<TOOL_SOURCE_DIR>` 是本次安装来源工具仓的本地 checkout，公开用户使用自己的 `silvers-tools-open`，不需要私仓；`--repo` 放在 `status` 前。该命令比较本地源码提交，不自动获取远端最新版。源码状态为 `unavailable` 时不能宣布版本已对齐，也不能用普通业务项目中的 `relay status` 代替来源仓验收。不能把“直接运行源码成功”当成稳定 launcher 已生效。

## 4. 配置独立远端

取得用户明确提供或确认的独立 Relay Git remote。跨机器使用应选择各机器都能访问的网络远端，本地路径只用于临时验证。不得创建远端，不得复用当前业务项目的 fetch/push URL，不得从其他工具配置中猜 remote，也不得把凭据嵌入 URL。

使用已选定的稳定 CLI 入口执行一次 `relay setup --remote <已确认 remote>`。setup 会验证与业务项目的边界，并可初始化一座真正为空的专用仓库；不要在 remote 非空、标记不匹配或默认分支异常时强行接管。

## 5. 适配当前客户端

只为当前客户端生成三个候选原生显式入口。安装模型必须同时阅读三份语义模板和 `shared/skill/relay*` 共享参考源，不得原样复制任一源文件。把 `<WRITER_IDENTITY>` 替换为用户确认的稳定助手身份，并把命令展示方式、显式触发限制、客户端元数据、稳定 launcher 入口、权限执行语义和本机增量转换为本机真值；不得用 `codex`、`claude-code` 等宿主名自动代替作者身份。保留零用户参数、编号选择、接棒确认门和 finally 草稿清理。`relay history` 与 `relay recall` 只由接棒入口内部调用，不新增需要用户记参数的入口。

当前客户端是 Codex 时，必须再阅读 `install/codex-permissions.md`：为实际 `<relay-home>/work` 与稳定 launcher 生成权限候选，使一次显式 Relay 入口不会按子命令或草稿文件反复询问。权限配置同样先做逐文件 diff 并等待确认；不得自动覆盖 Codex 全局配置或顺带修改其他客户端。

Claude Code、Codex Desktop/CLI/IDE 或其他客户端的文件格式不相同。当前客户端需要 YAML、Skill 元数据或命令目录时，按该客户端规则生成，不要把某一客户端的 frontmatter 写回模型无关模板。

候选文件必须先写在临时目录。逐文件读取现有目标、逐文件 diff，并向用户展示共享模板变化、本机平台增量和已有本机自定义的对账矩阵。用户明确确认后才能手工叠加；禁止覆盖式写入、`cp -f` 或 `--force`。写入后重新读取，按最终绝对路径、SHA-256 和本次参考的完整 source commit 更新该 client 的 `install.json` 回执。

## 6. 临时验证

另建临时 Relay home 和临时 bare remote，至少验证：

- 稳定 launcher 解析临时 `current.json`，透传参数和退出码；
- `relay --version` 与 runtime receipt 一致，`relay status` 能交叉验证安装回执；
- setup 缺 remote 会失败；
- status 能报告解析后的 home 和已配置 remote；
- `relay draft create --operation create` 返回唯一普通 JSON；其他 operation 使用相应的 `--operation`，需要现有棒时由 `--relay-id` 让 contextual draft 自动写入 target；`relay draft cleanup --path ...` 只清理该草稿；
- 创建后同名 canonical JSON/派生 Markdown 成对存在，另一 store 加载、更新和完成的真实 Git 往返；
- `relay successor` 能在一个 CAS 中归档旧阶段、从变化量创建新阶段，并在故障时完整回滚；
- `relay load` 返回阶段契约、逐条 `phase_completion`、结构化 delta、前阶段收尾摘要、全部活动决策全文、source relation 和有界响应；
- `modify=[]` 的只读棒能通过，缺失逐条完成声明或把旧版推定 `met` 当真值会被拒绝/降级；
- `relay history` 能列 done 阶段大纲，`relay recall` 能按 relay id、revision 与 decision id 或 criteria ordinal 读取一个决策或一条判据变更回执；
- 手工修改或删除派生 Markdown 时 load 仍从 canonical JSON 现渲染，并返回非阻断 `document_export` 诊断；手工破坏 canonical 时读取必须失败；
- 三个客户端入口可见、注释正确、无需用户参数且不会隐式触发。

验证结束只清理明确创建的临时 fixture。不要向真实 remote 写测试任务，也不要借验证修改或提交业务项目。最终报告应列出 runtime、launcher、`current.json`、`install.json`、remote 配置、客户端入口及其验证结果；未获确认的客户端候选必须明确列为待处理。
