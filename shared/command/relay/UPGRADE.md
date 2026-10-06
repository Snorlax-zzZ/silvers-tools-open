# Relay 更新与重装参考

> 本页给安装模型阅读和适配，不是一条可机械执行的更新脚本。

## 不变量

Relay home 中的代码层与数据层必须保持分离：

- 可替换代码：`bin/`、`runtimes/`、`current.json`、`install.json`；
- 持久数据：`config.json`、`store/`、`work/`。

普通更新不得删除、重建、搬移或覆盖 `config.json`、`store/`、`work/`。store schema 与 runtime 版本不是一回事；切换代码不能冒充数据迁移。

每个 `runtimes/<version>/` 在完成安装后不可原地覆盖。同一版本目录已存在但 receipt、source commit 或内容不一致时停止，报告冲突；不得把新文件复制到旧 venv 上。

## 更新流程

`<TOOL_SOURCE_DIR>` 指本次更新来源工具仓的本地 Git checkout 根目录；公开用户使用自己的 `silvers-tools-open`，不需要维护者私仓。先确认 checkout 已包含本次准备安装的版本；状态检查比较其中的本地提交，不自动获取远端最新版。

1. 只读检查 `relay --version`、`relay status`、`current.json`、`install.json`、当前 runtime receipt 和已有客户端入口。
2. 核实更新来源版本、完整 source commit、源码干净状态、Python 3.11+ 与 Git；不得猜测下载源或静默安装系统依赖。
3. 以排他方式创建新的 `runtimes/<version>/`，直接在最终路径构建 venv；venv 可能保存绝对路径，禁止在其他目录做好后整体搬家。目标目录存在时停止，不能原地覆盖。
4. 直接验证最终 runtime 的 `--version` 和临时 Relay home/临时 bare remote 流程，最后才写入 runtime receipt。receipt 写成前不得切换 current；失败时只报告或按授权清理本次新建的半成品。
5. 同时生成新的 `current.json` 与 `install.json` 候选，交叉核对 version、entrypoint 和 runtime source commit；只给本次实际更新并经用户确认的 client 写入新的 client 级 source commit 与文件 SHA-256，其他 client 回执原样保留。保留两份旧文件以便恢复。
6. 在同一个短临界步骤中先原子替换 `current.json`，紧接着原子替换 `install.json`；两次替换之间不得运行任何 Relay 命令。两个文件无法组成单次文件系统事务，若进程恰在中间崩溃，后续 `relay status` 必须以安装状态不一致停止。
7. 通过稳定 launcher 运行 `relay --version` 和 `relay --repo "<TOOL_SOURCE_DIR>" status`；`--repo` 是全局参数，必须放在 `status` 前。若 source status 为 `dirty_unverifiable`，先按用户授权处理 Relay 相关源码的未提交改动，不能据旧 commit 宣称安装已是 current。若为 `unavailable`，报告无法核对源码版本，不得宣布更新已与来源对齐；普通业务项目中的 `relay status` 不能替代来源仓验收。其他验证失败时连续恢复旧 current pointer 与旧 install receipt，不改持久数据，再验证旧版本。
8. 按下方人工门处理客户端入口。
9. 汇报旧/新版本、source commit、切换前后指针、回执、客户端对账、验证结果和仍保留的旧 runtime。

launcher 只读 current pointer 并执行目标。不要为了某个新版本修改 launcher 的业务逻辑；如果 launcher 模板本身确有安全修复，必须把它作为独立文件变更逐项校验和记录。

## 客户端入口是唯一强制人工确认步骤

runtime 和 launcher 属于 Relay 自身代码层；客户端命令、Skill 或规则文件可能含有本机长期增量，不能自动覆盖。

更新模型必须重新阅读当前版本的三份语义模板、`shared/skill/README.md` 和三份 Relay Skill 共享参考源。共享源不是安装成品，不得原样复制或用它覆盖本机入口。共享源中的 `<WRITER_IDENTITY>` 必须在候选中替换为用户确认的稳定作者身份；若旧安装已有作者身份，未经用户确认不得改名，也不得用宿主适配器名代替。

更新模型必须逐文件：

1. 读取现有目标和本机规则；
2. 在临时目录生成候选；
3. 做逐文件 diff；
4. 给出共享模板变化、本机平台增量、既有自定义与处理建议的对账矩阵；
5. 等待用户明确拍板；
6. 手工叠加并复读验证；
7. 将最终文件绝对路径和 SHA-256 写入 `install.json`。

禁止 `cp -f`、`--force`、`Copy-Item -Force`、`copy /Y` 及任何等价覆盖。用户未确认时保持现有客户端入口不动，把候选和待决定项交回用户。

当前客户端若有 Relay 专用权限规则或 writable root，也属于同一人工门。更新模型必须核对它们是否覆盖稳定 launcher 与实际 work 目录、是否排除 `setup`、是否仍与当前 Codex 语法兼容。不得保留逐条 Relay 命令形成的一次性 allow 规则；只能在新有界规则验证通过后，删除已被完整覆盖的 Relay 专属旧项，其他用户规则一律不动。

## 重装

重装默认只重建代码层，始终保留 `config.json`、`store/`、`work/`。先从现有 `install.json` 和 runtime receipt 取得当前事实，再按“更新流程”安装一个新的、未占用的版本目录并切换。

若用户要求重装同一版本，因版本目录不可原地覆盖，模型必须停止并说明：需要用户另行授权移走或删除旧代码目录后，才能把已在临时位置验证的新目录原子换入。不得把这种破坏性修复包含在普通更新授权里。

客户端入口仍走强制人工确认；“重装”不意味着可以恢复成共享模板并抹掉本机内容。

## 回退边界

当前没有自动 rollback 命令。新 runtime 在写入任何新数据前失败时，可以在一个短临界步骤内连续恢复旧 `current.json` 与旧 `install.json`，两次替换之间不运行 Relay，再验证旧 runtime。旧 runtime 目录在新版本完成实际使用验证前不得清理。

如果新 runtime 已写入旧 CLI 不支持的 schema，旧 CLI 会以 `schema_unsupported` 停止。此时不得手改 marker、canonical JSON 或伪造降级；应更新另一台机器或使用明确的数据迁移设计。

本版提供 `relay migrate`：用一笔 Git 事务原子迁移**当前项目**的全部 tip，写入失败时恢复迁移前文件。它只处理当前项目，不跨项目预扫或批量改写整个 store。命令幂等：无待迁移 tip 时返回 `idempotent: true` 且 `migrated_count: 0`。

`migrate` 是会改写存储记录并提交、同步的数据维护操作，需要用户明确授权本次迁移；普通 runtime 更新或日常三入口调用不自动包含这项授权。客户端不得将它加入日常免询问白名单。

幂等判定依据记录内是否已有 `decision_id_high_watermark` 这个结构标记，不看 `relay_schema` 版本号。同一 schema 号下可能混有已迁移与未迁移记录，按版本号判定会漏迁而判据仍显示通过。

v4 及更早版本没有逐条完成声明，其历史 `met` 在 load 中只按 `legacy_inferred/unknown` 暴露，不得当作真值继续传播。


其他兼容性检查并入后续 `doctor`，不新增独立 `compat` 命令。
