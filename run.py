# -*- coding: utf-8 -*-
"""章鱼频谱查看器 · 入口。"""
import sys

from PySide6.QtWidgets import QApplication

from octopus.main import APP_NAME, MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    # 支持命令行直接传入音频文件
    if len(sys.argv) > 1:
        win.open_file(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
