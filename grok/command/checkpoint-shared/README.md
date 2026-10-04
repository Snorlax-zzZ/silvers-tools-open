# Grok × checkpoint-shared

协议正文：`<CHECKPOINT_TOOLS>/shared/command/checkpoint/`。安装时把三份语义模板转成 Grok 命令。

硬编码：

- `<client_name>` = `grok`
- 工作区 = `~/.silvers/checkpoint-shared/`
- 只操作 `shared/`
- 本机命令文件：`~/.grok/commands/checkpoint-shared.md` 等

不要安装到 `~/.claude/commands/`。

## 安装

先阅读 `<CHECKPOINT_TOOLS>/shared/command/checkpoint/README.md`、`design.md` 和当前平台安装说明，保留完整协议。将本目录三份 `commands/*.md` 放到 `~/.grok/commands/`，把其中工具根路径替换成本机仓库绝对路径；远端替换为自己的存储仓库，已存在 clone 核对 origin。

```bash
mkdir -p ~/.grok/commands ~/.grok/scripts
cp grok/command/checkpoint-shared/commands/*.md ~/.grok/commands/
cp shared/command/checkpoint/scripts/list-shared-checkpoints.sh ~/.grok/scripts/
chmod +x ~/.grok/scripts/list-shared-checkpoints.sh
bash ~/.grok/scripts/list-shared-checkpoints.sh --help
```

这些薄入口每次读取完整共享协议，工具仓库必须保留在配置的路径。刷新客户端后确认三个命令可发现，再按共享安装手册用临时存档验证；不把测试数据推送到真实远端。
