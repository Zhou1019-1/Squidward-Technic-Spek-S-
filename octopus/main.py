# -*- coding: utf-8 -*-
"""章鱼频谱查看器 · 主窗口。

- 无边框窗口 + 自定义标题栏（章鱼出品，必属精品）
- 工具栏：打开 / 调色板 / 窗函数 / FFT 大小 / 声道 / 导出 PNG
- 文件信息面板：编码、码率、采样率、位深、声道、时长
- 拖放打开文件，窗口宽度变化自动重算（像素即数据）
"""
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from .decoder import probe
from .palette import PALETTES
from .spectrogram import SpectrogramWidget
from .worker import WINDOW_FUNCTIONS, SpectrogramWorker

# 打包后资源在 sys._MEIPASS 下；源码运行时取项目根目录
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICON_PATH = os.path.join(_BASE_DIR, "icon", "HMSicon.png")
APP_NAME = "章鱼频谱查看器"
APP_SLOGAN = "章鱼出品，必属精品"

AUDIO_FILTER = (
    "音频文件 (*.wav *.flac *.mp3 *.m4a *.aac *.ogg *.opus *.wma *.ape *.wv *.aif *.aiff);;"
    "所有文件 (*)"
)

FFT_BITS_OPTIONS = [8, 9, 10, 11, 12, 13, 14]


class TitleBar(QWidget):
    """自定义标题栏：图标 + 标题 + 标语 + 窗口按钮。"""

    HEIGHT = 44

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self._window = window
        self._drag_pos = None
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("TitleBar")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(8)

        icon = QLabel()
        if os.path.exists(ICON_PATH):
            pix = QPixmap(ICON_PATH).scaled(
                26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon.setPixmap(pix)
        lay.addWidget(icon)

        title = QLabel(f"{APP_NAME}")
        title.setObjectName("TitleText")
        lay.addWidget(title)

        slogan = QLabel(f"—— {APP_SLOGAN}")
        slogan.setObjectName("SloganText")
        lay.addWidget(slogan)
        lay.addStretch(1)

        for text, slot, obj in (
            ("—", self._on_min, "WinBtn"),
            ("▢", self._on_max, "WinBtn"),
            ("✕", self._on_close, "WinBtnClose"),
        ):
            btn = QPushButton(text)
            btn.setObjectName(obj)
            btn.setFixedSize(40, 30)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

    def _on_min(self):
        self._window.showMinimized()

    def _on_max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def _on_close(self):
        self._window.close()

    # 拖动窗口 / 双击最大化
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            if self._window.isMaximized():
                return
            delta = e.globalPosition().toPoint() - self._drag_pos
            self._window.move(self._window.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e):
        self._on_max()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} —— {APP_SLOGAN}")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1100, 700)
        self.setAcceptDrops(True)

        self.path = None
        self.info = None
        self.stream = 0
        self.worker = None

        # ---- 界面 ----
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(self)
        root.addWidget(self.titlebar)

        # 工具栏
        toolbar = QWidget()
        toolbar.setObjectName("ToolBar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 8, 12, 8)
        tb.setSpacing(8)

        self.btn_open = QPushButton("🐙 打开文件")
        self.btn_open.setObjectName("AccentBtn")
        self.btn_open.clicked.connect(self.open_dialog)
        tb.addWidget(self.btn_open)

        tb.addWidget(self._mk_label("调色板"))
        self.combo_palette = QComboBox()
        self.combo_palette.addItems(list(PALETTES.keys()))
        self.combo_palette.currentTextChanged.connect(self.on_palette)
        tb.addWidget(self.combo_palette)

        tb.addWidget(self._mk_label("窗函数"))
        self.combo_window = QComboBox()
        self.combo_window.addItems(WINDOW_FUNCTIONS)
        self.combo_window.currentTextChanged.connect(self.on_param_changed)
        tb.addWidget(self.combo_window)

        tb.addWidget(self._mk_label("FFT"))
        self.combo_fft = QComboBox()
        self.combo_fft.addItems([f"2^{b} ({1 << b})" for b in FFT_BITS_OPTIONS])
        self.combo_fft.setCurrentIndex(FFT_BITS_OPTIONS.index(11))
        self.combo_fft.currentIndexChanged.connect(self.on_param_changed)
        tb.addWidget(self.combo_fft)

        tb.addWidget(self._mk_label("声道"))
        self.combo_channel = QComboBox()
        self.combo_channel.currentIndexChanged.connect(self.on_param_changed)
        tb.addWidget(self.combo_channel)

        self.btn_save = QPushButton("导出 PNG")
        self.btn_save.clicked.connect(self.save_png)
        tb.addWidget(self.btn_save)

        tb.addStretch(1)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusLabel")
        tb.addWidget(self.status_label)
        root.addWidget(toolbar)

        # 信息面板
        self.info_label = QLabel("未加载文件")
        self.info_label.setObjectName("InfoPanel")
        self.info_label.setContentsMargins(14, 6, 14, 6)
        root.addWidget(self.info_label)

        # 频谱控件
        self.spec = SpectrogramWidget()
        root.addWidget(self.spec, 1)

        # 底部状态条（悬停读数 + 尺寸抓手）
        bottom = QWidget()
        bottom.setObjectName("BottomBar")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(12, 4, 6, 4)
        self.hover_label = QLabel("时间 - ｜ 频率 - ｜ 电平 -")
        self.hover_label.setObjectName("HoverLabel")
        bl.addWidget(self.hover_label)
        bl.addStretch(1)
        self.zoom_label = QLabel("频率范围: 全频段（滚轮缩放 / 双击复位）")
        self.zoom_label.setObjectName("HoverLabel")
        bl.addWidget(self.zoom_label)
        bl.addWidget(QSizeGrip(bottom))
        root.addWidget(bottom)

        self.setCentralWidget(central)

        # 信号
        self.spec.hover_changed.connect(self.on_hover)
        self.spec.freq_zoom_changed.connect(self.on_freq_zoom)

        # 窗口尺寸变化 → 防抖重算
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(300)
        self._resize_timer.timeout.connect(self.restart_worker)

        self._apply_style()

    # ---- 样式 ----

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #101018; color: #d5d5e0;
                font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; }
            #TitleBar { background: #17172a; border-bottom: 1px solid #2a2a40; }
            #TitleText { color: #c4b5fd; font-size: 15px; font-weight: bold; }
            #SloganText { color: #8b7ec8; font-size: 12px; }
            #WinBtn { background: transparent; border: none; color: #9a9ab0;
                font-size: 14px; }
            #WinBtn:hover { background: #2a2a45; border-radius: 4px; }
            #WinBtnClose { background: transparent; border: none; color: #9a9ab0;
                font-size: 14px; }
            #WinBtnClose:hover { background: #c0392b; color: white; border-radius: 4px; }
            #ToolBar { background: #14141f; border-bottom: 1px solid #23233a; }
            QPushButton { background: #23233a; border: 1px solid #34345a;
                border-radius: 6px; padding: 6px 14px; color: #d5d5e0; }
            QPushButton:hover { background: #2e2e4d; border-color: #7c6bd6; }
            QPushButton:pressed { background: #1c1c30; }
            #AccentBtn { background: #5b3fa8; border: 1px solid #7c6bd6;
                font-weight: bold; color: #ffffff; }
            #AccentBtn:hover { background: #6d4fc4; }
            QComboBox { background: #23233a; border: 1px solid #34345a;
                border-radius: 6px; padding: 5px 10px; min-width: 90px; }
            QComboBox:hover { border-color: #7c6bd6; }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView { background: #1c1c30; color: #d5d5e0;
                selection-background-color: #5b3fa8; border: 1px solid #34345a; }
            #InfoPanel { background: #131320; color: #a9a9c0;
                border-bottom: 1px solid #23233a; }
            #BottomBar { background: #14141f; border-top: 1px solid #23233a; }
            #HoverLabel { color: #8f8fa8; font-size: 12px; }
            #StatusLabel { color: #8f8fa8; }
            """
        )

    @staticmethod
    def _mk_label(text):
        lb = QLabel(text)
        lb.setStyleSheet("color: #8f8fa8;")
        return lb

    # ---- 文件打开 ----

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开音频文件", "", AUDIO_FILTER)
        if path:
            self.open_file(path)

    def open_file(self, path: str):
        try:
            info = probe(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"无法打开文件：\n{e}")
            return
        self.path = path
        self.info = info
        self.stream = 0

        # 声道选项
        self.combo_channel.blockSignals(True)
        self.combo_channel.clear()
        self.combo_channel.addItem("混合", -1)
        for i in range(info.channels):
            self.combo_channel.addItem(f"声道 {i + 1} / {info.channels}", i)
        self.combo_channel.blockSignals(False)

        # 信息面板
        parts = [os.path.basename(path)]
        if info.codec_name:
            parts.append(info.codec_name)
        if info.bit_rate:
            parts.append(f"{(info.bit_rate + 500) // 1000} kbps")
        if info.sample_rate:
            parts.append(f"{info.sample_rate} Hz")
        if info.bits_per_sample:
            parts.append(f"{info.bits_per_sample} bit")
        ch_txt = {1: "单声道", 2: "立体声"}.get(info.channels, f"{info.channels} 声道")
        parts.append(ch_txt)
        if info.duration:
            m, s = divmod(int(info.duration), 60)
            parts.append(f"时长 {m}:{s:02d}")
        if info.streams > 1:
            parts.append(f"含 {info.streams} 条音频流")
        self.info_label.setText("　·　".join(parts))

        self.restart_worker()

    # ---- 流水线控制 ----

    def fft_bits(self) -> int:
        return FFT_BITS_OPTIONS[self.combo_fft.currentIndex()]

    def restart_worker(self):
        if not self.path or not self.info:
            return
        self.stop_worker()
        ncols = self.spec.plot_width()
        if ncols <= 0:
            return
        self.spec.configure(
            ncols=ncols,
            bands=(1 << (self.fft_bits() - 1)) + 1,
            duration=self.info.duration,
            sample_rate=self.info.sample_rate,
        )
        self.worker = SpectrogramWorker(
            path=self.path,
            stream=self.stream,
            channel=self.combo_channel.currentData(),
            fft_bits=self.fft_bits(),
            window_name=self.combo_window.currentText(),
            ncols=ncols,
            total_frames=self.info.total_frames,
        )
        self.worker.column_ready.connect(self.spec.add_column)
        self.worker.finished_all.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.status_label.setText("分析中…")
        self.worker.start()

    def stop_worker(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None

    def on_finished(self):
        self.status_label.setText("分析完成")

    def on_failed(self, msg: str):
        self.status_label.setText("分析失败")
        QMessageBox.warning(self, APP_NAME, f"分析失败：\n{msg}")

    # ---- 工具栏回调 ----

    def on_palette(self, name: str):
        self.spec.set_palette(name)

    def on_param_changed(self, *_):
        self.restart_worker()

    def save_png(self):
        if self.spec._db is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出频谱图", "spectrogram.png", "PNG 图片 (*.png)"
        )
        if path:
            self.spec.render_to_image().save(path, "PNG")
            self.status_label.setText(f"已导出：{os.path.basename(path)}")

    # ---- 悬停 / 缩放 ----

    def on_hover(self, data):
        if data is None:
            self.hover_label.setText("时间 - ｜ 频率 - ｜ 电平 -")
        else:
            t, f, db = data
            m, s = divmod(int(t), 60)
            f_txt = f"{f / 1000:.2f} kHz" if f >= 1000 else f"{f:.0f} Hz"
            self.hover_label.setText(
                f"时间 {m}:{s:02d} ｜ 频率 {f_txt} ｜ 电平 {db:.1f} dB"
            )

    def on_freq_zoom(self, lo: float, hi: float):
        if self.info and self.info.sample_rate:
            nyq = self.info.sample_rate / 2
            self.zoom_label.setText(
                f"频率范围: {lo * nyq / 1000:.2f} ~ {hi * nyq / 1000:.2f} kHz（双击复位）"
            )

    # ---- 拖放 / 尺寸 ----

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.open_file(path)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.path:
            self._resize_timer.start()

    def closeEvent(self, e):
        self.stop_worker()
        super().closeEvent(e)
