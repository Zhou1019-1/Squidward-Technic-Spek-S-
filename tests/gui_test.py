# -*- coding: utf-8 -*-
"""离屏 GUI 测试：完整走一遍界面流程并截图。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from octopus.main import MainWindow

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT = os.path.join(BASE, "tests", "gui_shot.png")
LOG = open(os.path.join(BASE, "tests", "gui_log.txt"), "w", encoding="utf-8")


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


app = QApplication(sys.argv)
win = MainWindow()
win.resize(1100, 700)
win.show()

path = os.path.join(BASE, "test_media", "base.wav")
log("open:", path, os.path.exists(path))
win.open_file(path)
log("info_label:", win.info_label.text())
log("worker:", win.worker is not None)


def shot1():
    win.grab().save(SHOT)
    log("shot1 saved, status:", win.status_label.text())
    # 切换调色板再截一张，并模拟频率缩放
    win.spec.set_palette("SoX 经典")
    win.spec.f_lo, win.spec.f_hi = 0.5, 1.0
    win.spec.update()

    def shot2():
        win.grab().save(os.path.join(BASE, "tests", "gui_shot2.png"))
        log("shot2 saved")
        app.quit()

    QTimer.singleShot(500, shot2)


QTimer.singleShot(3000, shot1)
app.exec()
LOG.close()
