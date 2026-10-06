# Relay 自主安装模板

本目录给安装模型阅读和适配。这里保存的是**语义模板，不是可以机械复制的成品命令**；`shared/skill/relay*` 同样是共享行为参考源，不是可直接安装的文件包。不同操作系统、shell、CLI 安装位置和客户端扩展机制可能完全不同。

安装完成后，当前客户端应提供三个带注释、无需用户参数的原生显式入口：

| 语义入口 | 菜单注释 | 目标体验 |
|---|---|---|
| `relay` | 交棒：保存或更新当前任务，交给下一模型 | Claude Code 通常显示为 `/relay`，Codex 通常显示为 `$relay` |
| `relay-load` | 接棒：加载当前项目的接力任务并完成理解回执 | 多个候选时只让用户回复编号；内部按需 history/recall |
| `relay-done` | 收棒：验证阶段完成证据并归档当前接力任务 | 缺少阶段完成证据或可靠 revision 时拒绝归档 |

“通常”不是安装指令。安装模型必须识别当前客户端真实支持的命令、Skill 或其他扩展机制，只安装当前客户端，不顺带修改其他客户端。

## 安装模型必须阅读

按顺序完整阅读：

1. `shared/tool/relay/README.md`
2. `shared/tool/relay/design.md`
3. 本目录下 `commands/relay.md`、`commands/relay-load.md`、`commands/relay-done.md`
4. `shared/skill/README.md` 及 `shared/skill/relay/`、`relay-load/`、`relay-done/` 中的共享参考源
5. 当前平台对应的 `install/macos.md` 或 `install/windows.md`
6. 当前客户端是 Codex 时再完整阅读 [`install/codex-permissions.md`](install/codex-permissions.md)
7. 更新或重装时再完整阅读 [`UPGRADE.md`](UPGRADE.md)
8. 当前客户端的本机规则、官方扩展格式和现有安装布局

不要只读一份模板就开始复制；安装不是文件复制流程。

## 安装后的代码与数据布局

安装模型必须把可替换代码与持久数据分开：

```text
<relay-home>/
├── bin/                         # 稳定 launcher 入口
├── runtimes/<version>/          # 不原地覆盖的版本化 runtime
├── current.json                 # 原子切换的活动 runtime 指针
├── install.json                 # 本机安装回执
├── config.json                  # 独立 remote 配置
├── store/                       # Relay Git 数据
└── work/                        # 临时请求
```

`config.json`、`store/`、`work/` 与 `runtimes/` 平级。首次安装、更新和重装都不得把持久数据塞进版本目录，也不得因为替换 runtime 而重建持久数据。

`shared/tool/relay/launcher/relay_launcher.py` 是冻结的 launcher 模板。安装模型可为本机 shell 生成稳定包装入口，但 launcher 自身只读固定 pointer schema 的 `current.json`、执行它指向的 runtime、透传参数和退出码；不得往 launcher 中加入 Relay runtime 版本、remote、业务/存储 schema、store 或更新逻辑。

同一台机器、同一个 Relay home 只安装一套 runtime 和 store；Claude Code、Codex 等客户端复用同一个稳定 launcher。不同客户端只各自安装三个原生入口，并分别走人工确认和回执记录，不复制 runtime。

`pass/done --client` 是交棒作者标识，用来说明哪一个稳定的助手身份写入了 revision，可以是符合 CLI 约束的本地化名称；共享源一律写作 `<WRITER_IDENTITY>`。`install.json.clients[].client` 是宿主适配器标识，用来说明哪一种客户端入口已经安装。两者语义不同：安装模型必须取得用户确认的稳定作者身份并替换全部占位符，不得把 `codex`、`claude-code` 等宿主名自动填成作者，也不得让字面占位符进入最终文件。

`pass`、`successor`、`done` 的写入标识必须满足：

| 参数 | 首字符 | 后续字符 | 长度 |
|---|---|---|---|
| `--client` | Unicode 字母或数字 | Unicode 字母、数字及 `.`、`_`、`-` | 1–64 个 UTF-8 字节；中文名称可用，空格不可用 |
| `--model` | ASCII 字母或数字 | ASCII 字母、数字及 `.`、`_`、`:`、`/`、`+`、`@`、`-` | 1–128 个 ASCII 字符；空格、中文不可用 |

模板中的 `<当前模型>` / `<current-model>` 必须取自当前客户端实际模型的稳定 ID，不能填模型显示名、字面占位符或猜测值；无法核实该 ID 时报告缺少的输入。安装时核验作者身份满足约束，并让生成的入口在每次写入时取得当前模型 ID，不把安装时的型号永久写死。两个值都必须按当前 shell 的参数规则传递，不能把它们直接当作命令片段拼接。

## 安装输入与边界

日常交棒、接棒和收棒所在的业务项目必须已有至少一次 Git 提交，能够解析 `HEAD`。只有 `git init` 的空历史项目暂不支持生成项目快照；安装模型或入口应报告这一前提，不自动替用户创建业务提交。`relay --version` 和只读 `relay status` 可独立用于检查工具。

安装需要用户明确提供或确认一座**独立 Relay remote**。安装模型不得猜测或复用业务项目 remote，不得复用其他工具的数据仓库，不得自行创建远端，也不得改 SSH、credential helper 或全局 Git 配置。

如果用户尚未给出 remote，停在询问这一个输入；不要把 `remote: null` 当作可工作的本地模式。remote 是一次性安装输入，日常三个入口仍然零参数。

跨机器使用时还须核对**业务项目**的 `origin` 规范化身份一致：HTTPS 与 SSH 不会自动合并，URL 中的项目路径大小写也不折叠；没有 `origin` 时身份取本机绝对路径。不同身份会使用不同的项目目录，即使 Relay 数据 remote 相同，也不能据此声称两台机器能接到同一根棒。发现不一致时报告原因，不擅自修改业务项目 remote。

安装授权只覆盖当前客户端所需的 Relay CLI、三个原生入口和 Relay 自己的运行目录。删除文件、安装依赖、改系统配置、创建远端、提交或推送业务项目仍遵守当前环境的用户授权规则。

显式调用一个 Relay 入口后，该入口所需的 Relay CLI、独立 store 与请求草稿操作是一套授权流程；客户端适配器不得按 Relay 子命令或草稿文件逐步询问。客户端权限配置与三个入口一起走人工 diff 和确认：在 full access/no-approval 下不主动申请升级权限；受限模式真实拒绝时只申请一次有界的 Relay 权限，不循环制造一次性 allow 规则。

## 自主安装流程

下文 `<TOOL_SOURCE_DIR>` 是本次安装来源工具仓的本地 Git checkout 根目录，应包含 `shared/tool/relay/`、`shared/command/relay/` 和 `shared/skill/relay*`。公开用户使用自己 clone 的 `silvers-tools-open` 即可，不需要访问维护者私仓。验收前先确认这份 checkout 已是本次准备安装的版本；版本比较只读取本地提交，不会自动获取远端最新版。

安装模型应当：

1. 识别 OS、shell、Python 3.11+、Git、当前客户端和它的原生扩展机制。
2. 解析 Relay home，检查是否已有 `current.json`、`install.json`、`runtimes/` 和客户端入口；已有安装必须转入 `UPGRADE.md`，不得按首次安装覆盖。
3. 根据平台手册排他创建全新的 `runtimes/<version>/`，直接在最终路径构建 venv；runtime receipt 写成前不得切换。目标版本目录已存在时停止，不能原地覆盖。
4. 安装稳定 launcher，生成 runtime receipt、`current.json` 和 `install.json`；每个 client 回执记录自己的 source commit 与文件 SHA-256，JSON 必须使用 UTF-8 与原子替换。通过稳定入口执行 `relay --version` 和 `relay --repo "<TOOL_SOURCE_DIR>" status`，核对三份状态、client 文件哈希与安装来源 checkout 中 Relay 相关路径的最新 commit。`--repo` 是全局参数，必须放在 `status` 前。若 source status 为 `dirty_unverifiable`，先按用户授权处理 Relay 相关源码的未提交改动；不得把基于旧 commit 的 `current` 当作安装已覆盖未提交规则。若为 `unavailable`，报告无法核对源码版本，不得宣布版本已对齐；普通业务项目通常不含工具源码，不能拿其中的 `relay status` 代替这一步。
5. 取得用户确认的独立 remote，再执行一次 `relay setup --remote <已确认 remote>`；不得把参数转嫁给日常命令。
6. 使用临时 Relay home 与临时 bare remote 验证 CLI，不向真实 remote 写测试 fixture。
7. 同时参考三份语义模板与三份共享 Skill 行为源，将其转换成当前客户端的候选原生入口。必须适配触发语法、客户端元数据、稳定 launcher、用户确认的 `<WRITER_IDENTITY>`、权限执行语义和本机既有增量；不得原样复制 `shared/command/relay/commands/**`、`shared/skill/relay*/**`，也不要直接覆盖本机文件。
8. 当前客户端是 Codex 时，按 `install/codex-permissions.md` 生成 writable root 与独立 execpolicy 候选，禁止为每个子命令或动态参数沉淀一次性规则。
9. 执行下方“客户端入口强制人工确认”，确认后才写入入口与权限候选，并把 Relay 独占文件的最终 SHA-256 记录进 `install.json`。
10. 保持模型负责提炼、CLI 负责当前 schema、阶段继承、完整活动决策、每 revision 判据回执、canonical 权威与 Markdown 派生诊断、96/128 KiB 硬上限和 48 KiB 软预算、CAS、安全扫描、Git 同步和草稿权限的边界。
11. 汇报实际安装文件、CLI 入口、runtime/launcher 版本、运行目录解析结果、remote 的脱敏规范化身份、客户端适配差异、权限增量、待人工项和验证证据。

安装模型不得把本目录三份 Markdown 或 `shared/skill/relay*/**` 原样复制后就声称安装完成。

用户仍然只记三个入口。`relay history` 和 `relay recall` 是接棒入口内部使用的有界 CLI 能力，不另做需要用户记参数的日常命令。

## 客户端入口强制人工确认

客户端入口和客户端权限增量不是普通 runtime 文件。无论首次安装还是更新，安装模型都必须：

1. 逐文件只读检查目标目录、本机规则和已有入口；
2. 在临时目录生成候选文件；
3. 对每个目标做逐文件 diff；
4. 给出“共享模板变化 / 本机平台增量 / 既有本机自定义 / 建议处理”的对账矩阵；
5. 等待用户明确拍板；
6. 以手工叠加或新文件方式写入，再重新读取验证；
7. 记录最终文件绝对路径和 SHA-256。

对 `~/.claude/commands/**`、`~/.claude/skills/**/SKILL.md` 以及其他客户端的同类扩展目录，禁止覆盖式写入，禁止 `cp -f`、`--force` 及等价操作。用户未确认时不得改入口；应把 runtime 安装结果和待确认候选清楚汇报出来。
