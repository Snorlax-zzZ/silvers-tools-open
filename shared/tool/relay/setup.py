"""仅在构建期间把仓库根许可证带入独立安装包。"""

from pathlib import Path

from setuptools import setup


package = Path(__file__).resolve().parent
license_file = package / "LICENSE"
generated = False

if not license_file.is_file():
    repository = package.parents[2]
    # 源仓以导出资产维护公开根许可证；公开 checkout 直接使用根 LICENSE。
    sources = (repository / "LICENSE", repository / "export/oss-assets/LICENSE")
    source = next((path for path in sources if path.is_file()), None)
    if source is None:
        raise FileNotFoundError("缺少仓库根 LICENSE 或源码分发包内 LICENSE，停止构建。")
    license_file.write_bytes(source.read_bytes())
    generated = True

try:
    setup()
finally:
    if generated:
        license_file.unlink()
