# 共享 Skill 源

这里存放跨客户端安装时供模型阅读的**共享参考源，不是可直接复制的安装成品**。安装必须由用户明确要求当前安装模型完成；安装模型完整阅读 Relay 安装手册、本目录参考源、当前客户端官方扩展格式、本机规则和已有文件后，只为当前客户端生成候选，不修改其他客户端。

禁止把本目录或其中的 `SKILL.md`、`agents/` 原样复制到客户端目录。安装模型必须把触发方式、稳定 launcher 调用、本机增量和所有占位符转换为当前客户端的本机真值，在临时目录生成候选，逐文件 diff，并经用户明确确认后安装。

`<WRITER_IDENTITY>` 是交棒作者占位符。安装模型必须取得用户确认的稳定助手身份并在候选中全部替换；不得保留字面占位符，也不得用宿主适配器名 `codex`、`claude-code` 等自动代替。`install.json.clients[].client` 只记录宿主适配器，两者语义不同。

三个 Relay Skill 都把一次显式入口调用视为该入口完整 CLI、独立 store 与请求草稿流程的一次授权，不得按子命令或草稿文件逐步询问。Codex 安装模型还必须阅读 [`../command/relay/install/codex-permissions.md`](../command/relay/install/codex-permissions.md)，把共享语义适配成当前版本的 writable root 与有界 execpolicy 候选。

## 当前 Skill

- [`relay/`](relay/)：交棒行为参考源；当前客户端安装模型将其适配为原生显式入口，创建或整份更新阶段快照与决策生命周期。
- [`relay-load/`](relay-load/)：接棒行为参考源；当前客户端安装模型将其适配为原生显式入口，按需使用 delta/history/recall 并完成理解确认门。
- [`relay-done/`](relay-done/)：收棒行为参考源；当前客户端安装模型将其适配为原生显式入口，核验阶段证据并成对归档 JSON/Markdown。

`agents/openai.yaml` 仅是支持 OpenAI Skill 元数据的客户端适配参考，不会把同目录的 Relay 行为源变成 Codex 专用品；其他客户端按自己的原生格式生成等价入口。

Skill 是模型侧调用说明，不是对应 CLI 的运行时依赖。CLI 不发现、不读取、也不安装这些 Skill。
