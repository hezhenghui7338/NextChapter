"""`python -m nextchapter_core` 的入口。

PyInstaller 打包时用这个文件作为入口，避免相对 import 问题。
"""
from nextchapter_core.api.server import run


if __name__ == "__main__":
    run()
