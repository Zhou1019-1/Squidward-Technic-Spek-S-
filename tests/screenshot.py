# -*- coding: utf-8 -*-
"""真实 Windows 平台下截图（窗口移到屏幕外避免打扰用户）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from octopus.main import MainWindow

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(BASE, "docs")
os.makedirs(DOCS, exist_ok=True)

app = QApplication(sys.argv)
win = MainWindow()
win.resize(1100, 700)
win.move(-3000, -3000)  # 移到屏幕外
win.show()

win.open_file(os.path.join(BASE, "test_media", "base.wav"))


def shot1():
    win.grab().save(os.path.join(DOCS, "screenshot-main.png"))
    # 第二张：SoX 调色板 + 频率缩放到 11k~22k
    win.spec.set_palette("SoX 经典")
    win.spec.f_lo, win.spec.f_hi = 0.5, 1.0
    win.spec.update()
    QTimer.singleShot(600, shot2)


def shot2():
    win.grab().save(os.path.join(DOCS, "screenshot-sox-zoom.png"))
    with open(os.path.join(BASE, "tests", "shot_log.txt"), "w") as f:
        f.write("done")
    app.quit()


QTimer.singleShot(3000, shot1)
app.exec()
