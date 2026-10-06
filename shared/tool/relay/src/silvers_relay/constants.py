# 硬上限用于拒绝异常输入，不是写作目标。
MAX_REQUEST_BYTES = 96 * 1024
MAX_LOAD_BYTES = 128 * 1024

# 安装诊断独立于接力棒内容预算。诊断过长时由 installation 模块截断，
# 不允许一根已经成功写入的棒因为安装状态变化而突然无法 load。
MAX_INSTALLATION_WARNING_BYTES = 8 * 1024

# 软预算只提示、不拒绝。它必须严格低于唯一的 load 硬上限，
# 否则提示会在硬门之后才出现，失去提前精炼的意义。
SOFT_LOAD_BYTES = 48 * 1024
if not 0 < SOFT_LOAD_BYTES < MAX_LOAD_BYTES:
    raise AssertionError(
        "Relay 预算配置不自洽：SOFT_LOAD_BYTES 必须低于 MAX_LOAD_BYTES；"
        f" 当前 {SOFT_LOAD_BYTES} vs {MAX_LOAD_BYTES}"
    )

# 开启下一阶段的用户授权原话。放宽到 1 KiB 是为了容得下用户连续说的一段话，
# 交棒方不必截断转述；它随 lineage 落盘并渲染在接棒入口。
MAX_AUTHORIZATION_BYTES = 1024

# 存量档案里判据冷索引的 label 由历史版本按这个字节上限截断（超出部分补 …）。
# 当前协议不再写 criteria_registry，本常量只在读存量时按同一规则重算 label
# 做全等比对。改动它等于宣布已归档的棒打不开，不是可调参数。
MAX_CRITERIA_LABEL_BYTES = 96

REQUIRED_TOP_LEVEL_FIELDS = {
    "title",
    "summary",
    "phase",
    "design",
    "decisions",
    "decision_transitions",
    "criteria_transitions",
    "authority",
    "state",
    "next_step",
    "remaining",
    "deviations",
    "references",
}
