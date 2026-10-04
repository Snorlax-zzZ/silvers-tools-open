加载一份 Grok checkpoint，继续之前的工作。

## 步骤

1. 若用户给了路径，读该文件
2. 否则列出 `~/.grok/checkpoints/<当前项目slug>/` 下未进 `done/` 的 md，让用户挑；只有一份就直接用
3. `read_file` 全文
4. 向用户复述：任务目标、当前进度、陷阱、下一步
5. 等用户确认后再动手，不要读完立刻改代码

不要去读 `~/.claude/checkpoints/`，除非用户明确说加载 cc 的档。
