# -*- coding: utf-8 -*-
"""频谱渲染控件：对标 Spek 的 spek-spectrogram.cc / spek-ruler.cc。

功能：
- 逐列渐进渲染（内部维护 QImage 与 dB 矩阵）
- 自适应刻度尺：时间轴 / 频率轴 / dB 密度轴（因子表算法移植自 SpekRuler）
- 鼠标悬停十字线读数（时间 / 频率 / 电平）
- 滚轮缩放频率轴，双击复位
"""
import numpy as np
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .palette import DEFAULT_PALETTE, get_lut

# 布局常量（对应 Spek 的 LPAD/TPAD/RPAD/BPAD/GAP/RULER）
LPAD = 64
TPAD = 20
RPAD = 88
BPAD = 40
GAP = 10
RULER_W = 10

TIME_FACTORS = [1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800]
FREQ_FACTORS = [1000, 2000, 5000, 10000, 20000]
DB_FACTORS = [1, 2, 5, 10, 20, 50]


def format_time(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def format_freq(hz: float) -> str:
    if hz >= 1000:
        v = hz / 1000.0
        return f"{v:g} kHz"
    return f"{int(hz)} Hz"


def format_db(db: float) -> str:
    return f"{int(round(db))} dB"


def choose_step(min_v, max_v, px_len, factors, label_px, spacing=1.5):
    """移植 SpekRuler 的步长选择：保证相邻刻度间距 ≥ 标签宽度 × spacing。"""
    span = max_v - min_v
    if span <= 0 or px_len <= 0:
        return None
    step = factors[-1]
    for f in factors:
        step = f
        if px_len / (span / f) >= label_px * spacing:
            return f
    # 放大最后一个因子直到满足
    while px_len / (span / step) < label_px * spacing:
        step *= 10
    return step


class SpectrogramWidget(QWidget):
    """频谱图控件。"""

    hover_changed = Signal(object)  # None 或 (time, freq, db)
    freq_zoom_changed = Signal(float, float)  # (f_lo, f_hi) 0..1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 320)

        self.palette_name = DEFAULT_PALETTE
        self.urange = 0.0
        self.lrange = -120.0

        self.duration = 0.0
        self.sample_rate = 0

        self.ncols = 0
        self.bands = 0
        self._db = None        # (bands, ncols) float32，行 0 = 最低频
        self._rgb = None       # (bands, ncols, 3) uint8，行 0 = 最高频（图像坐标）
        self._qimg = None

        # 频率视图缩放（0..1，占奈奎斯特比例）
        self.f_lo = 0.0
        self.f_hi = 1.0

        self._hover = None  # (x, y) 控件坐标

    # ---- 数据接口 ----

    def configure(self, ncols: int, bands: int, duration: float, sample_rate: int):
        """开始一次新的分析前调用，分配内部缓冲。"""
        self.ncols = max(1, ncols)
        self.bands = max(1, bands)
        self.duration = duration
        self.sample_rate = sample_rate
        self._db = np.full((self.bands, self.ncols), -120.0, dtype=np.float32)
        self._rgb = np.zeros((self.bands, self.ncols, 3), dtype=np.uint8)
        self.f_lo, self.f_hi = 0.0, 1.0
        self.update()

    def clear(self):
        self.ncols = 0
        self._db = None
        self._rgb = None
        self._qimg = None
        self.update()

    def add_column(self, col: int, db_values: np.ndarray):
        """接收一列 dB 数据（行 0 = 最低频），立即着色。"""
        if self._db is None or col < 0 or col >= self.ncols:
            return
        if len(db_values) != self.bands:
            return
        self._db[:, col] = db_values
        self._colorize_column(col)
        self.update()

    def set_palette(self, name: str):
        self.palette_name = name
        self._recolor_all()

    def set_db_range(self, urange: float, lrange: float):
        self.urange, self.lrange = urange, lrange
        self._recolor_all()

    # ---- 着色 ----

    def _colorize_column(self, col: int):
        lut = get_lut(self.palette_name)
        rng = self.urange - self.lrange
        level = np.clip((self._db[:, col] - self.lrange) / rng, 0.0, 1.0)
        idx = (level * 255.0 + 0.5).astype(np.uint8)
        # 行 0 = 最低频 → 图像底部，需垂直翻转
        self._rgb[::-1, col] = lut[idx]

    def _recolor_all(self):
        if self._db is None:
            return
        lut = get_lut(self.palette_name)
        rng = self.urange - self.lrange
        level = np.clip((self._db - self.lrange) / rng, 0.0, 1.0)
        idx = (level * 255.0 + 0.5).astype(np.uint8)
        self._rgb[:] = lut[idx][::-1]  # 垂直翻转：行 0 = 最高频
        self.update()

    # ---- 坐标换算 ----

    def plot_rect(self):
        w, h = self.width(), self.height()
        return LPAD, TPAD, max(1, w - LPAD - RPAD), max(1, h - TPAD - BPAD)

    def plot_width(self) -> int:
        return self.plot_rect()[2]

    def _xy_to_tf(self, x: float, y: float):
        """控件坐标 → (时间, 频率)，不在绘图区返回 None。"""
        px, py, pw, ph = self.plot_rect()
        if not (px <= x < px + pw and py <= y < py + ph) or self.duration <= 0:
            return None
        nyquist = self.sample_rate / 2.0
        t = (x - px) / pw * self.duration
        f_frac = self.f_lo + (1.0 - (y - py) / ph) * (self.f_hi - self.f_lo)
        return t, f_frac * nyquist

    # ---- 事件 ----

    def mouseMoveEvent(self, e):
        self._hover = (e.position().x(), e.position().y())
        tf = self._xy_to_tf(*self._hover)
        if tf is not None and self._db is not None:
            t, f = tf
            nyquist = self.sample_rate / 2.0
            col = min(int(t / self.duration * self.ncols), self.ncols - 1)
            band = min(int(f / nyquist * (self.bands - 1)), self.bands - 1)
            db = float(self._db[band, col])
            self.hover_changed.emit((t, f, db))
        else:
            self.hover_changed.emit(None)
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.hover_changed.emit(None)
        self.update()

    def wheelEvent(self, e):
        """滚轮缩放频率轴（围绕光标位置），双击复位。"""
        if self._db is None:
            return
        px, py, pw, ph = self.plot_rect()
        y = e.position().y()
        frac = min(max((y - py) / ph, 0.0), 1.0)  # 0=顶(高频) 1=底
        cursor_f = self.f_hi - frac * (self.f_hi - self.f_lo)

        factor = 0.8 if e.angleDelta().y() > 0 else 1.25
        new_lo = cursor_f - (cursor_f - self.f_lo) * factor
        new_hi = cursor_f + (self.f_hi - cursor_f) * factor
        if new_hi - new_lo >= 0.98:  # 基本还原时直接复位
            new_lo, new_hi = 0.0, 1.0
        new_lo = max(0.0, new_lo)
        new_hi = min(1.0, new_hi)
        if new_hi - new_lo < 0.01:  # 最小缩放范围
            return
        self.f_lo, self.f_hi = new_lo, new_hi
        self.freq_zoom_changed.emit(self.f_lo, self.f_hi)
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.f_lo, self.f_hi = 0.0, 1.0
        self.freq_zoom_changed.emit(0.0, 1.0)
        self.update()

    # ---- 绘制 ----

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()

        # 背景
        p.fillRect(0, 0, w, h, QColor("#0b0b12"))

        px, py, pw, ph = self.plot_rect()

        # 频谱图（QImage 直接包装 numpy 缓冲，零拷贝；缓冲生命周期由 self._rgb 保证）
        if self._rgb is not None:
            qimg = QImage(
                self._rgb.data, self.ncols, self.bands,
                self.ncols * 3, QImage.Format_RGB888,
            )
            # 根据频率缩放裁剪源行（图像行 0 = 最高频）
            src_top = int(round((1.0 - self.f_hi) * (self.bands - 1)))
            src_bottom = int(round((1.0 - self.f_lo) * (self.bands - 1)))
            src_h = max(1, src_bottom - src_top + 1)
            p.drawImage(
                QRectF(px, py, pw, ph),
                qimg,
                QRectF(0, src_top, self.ncols, src_h),
            )
        else:
            # 空状态提示
            p.setPen(QColor("#3f3f52"))
            f = QFont()
            f.setPointSize(14)
            p.setFont(f)
            p.drawText(
                QRectF(px, py, pw, ph),
                Qt.AlignCenter,
                "拖入音频文件，或点击「打开文件」开始分析",
            )

        # 边框
        p.setPen(QPen(QColor("#4a4a5e"), 1))
        p.drawRect(px, py, pw, ph)

        if self._db is not None:
            self._draw_time_ruler(p)
            self._draw_freq_ruler(p)
            self._draw_palette_bar(p)
            self._draw_crosshair(p)

        p.end()

    def _draw_time_ruler(self, p: QPainter):
        if self.duration <= 0:
            return
        px, py, pw, ph = self.plot_rect()
        y = py + ph
        p.setPen(QColor("#8a8a9e"))
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        label_px = p.fontMetrics().horizontalAdvance("00:00")
        step = choose_step(0, self.duration, pw, TIME_FACTORS, label_px)
        if step is None:
            return
        t = 0.0
        while t <= self.duration + 1e-6:
            x = px + t / self.duration * pw
            p.drawLine(int(x), y, int(x), y + 5)
            p.drawText(
                QRectF(x - 40, y + 7, 80, 16), Qt.AlignHCenter, format_time(t)
            )
            t += step

    def _draw_freq_ruler(self, p: QPainter):
        if self.sample_rate <= 0:
            return
        px, py, pw, ph = self.plot_rect()
        nyquist = self.sample_rate / 2.0
        f_min = self.f_lo * nyquist
        f_max = self.f_hi * nyquist
        p.setPen(QColor("#8a8a9e"))
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        label_px = p.fontMetrics().height()
        step = choose_step(f_min, f_max, ph, FREQ_FACTORS, label_px, spacing=3.0)
        if step is None:
            return
        v = np.ceil(f_min / step) * step
        while v <= f_max + 1e-6:
            frac = (v - f_min) / (f_max - f_min) if f_max > f_min else 0
            y = py + ph - frac * ph
            p.drawLine(px - 5, int(y), px, int(y))
            p.drawText(
                QRectF(0, y - 8, px - 10, 16), Qt.AlignRight, format_freq(v)
            )
            v += step

    def _draw_palette_bar(self, p: QPainter):
        px, py, pw, ph = self.plot_rect()
        bar_x = px + pw + GAP
        lut = get_lut(self.palette_name)
        # 逐行画色条（顶 = 高电平 = lut 末尾）
        for yy in range(ph):
            level = 1.0 - yy / max(ph - 1, 1)
            idx = min(int(level * 255 + 0.5), 255)
            r, g, b = lut[idx]
            p.setPen(QColor(int(r), int(g), int(b)))
            p.drawLine(bar_x, py + yy, bar_x + RULER_W, py + yy)

        # dB 刻度
        p.setPen(QColor("#8a8a9e"))
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        label_px = p.fontMetrics().height()
        step = choose_step(
            -self.urange, -self.lrange, ph, DB_FACTORS, label_px, spacing=3.0
        )
        if step is None:
            return
        v = -self.urange  # 从 0 dB 往下
        span = self.urange - self.lrange
        while -v <= -self.lrange + 1e-6:
            frac = (v - self.lrange) / span  # v 从 lrange(底) 到 urange(顶)
            y = py + ph - frac * ph
            p.drawLine(bar_x + RULER_W, int(y), bar_x + RULER_W + 5, int(y))
            p.drawText(
                QRectF(bar_x + RULER_W + 8, y - 8, 60, 16),
                Qt.AlignLeft,
                format_db(v),
            )
            v -= step
            if step <= 0:
                break

    def _draw_crosshair(self, p: QPainter):
        if self._hover is None or self._db is None:
            return
        tf = self._xy_to_tf(*self._hover)
        if tf is None:
            return
        t, freq = tf
        px, py, pw, ph = self.plot_rect()
        x, y = self._hover

        # 十字线
        pen = QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine)
        p.setPen(pen)
        p.drawLine(int(x), py, int(x), py + ph)
        p.drawLine(px, int(y), px + pw, int(y))

        # 读数框
        nyquist = self.sample_rate / 2.0
        col = min(int(t / self.duration * self.ncols), self.ncols - 1)
        band = min(int(freq / nyquist * (self.bands - 1)), self.bands - 1)
        db = float(self._db[band, col])
        text = f"{format_time(t)}  |  {format_freq(freq)}  |  {db:.1f} dB"

        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 16
        th = fm.height() + 10
        bx = min(x + 12, px + pw - tw - 2)
        by = max(y - th - 10, py + 2)
        p.setPen(QPen(QColor("#a78bfa"), 1))
        p.setBrush(QColor(20, 16, 40, 220))
        p.drawRoundedRect(QRectF(bx, by, tw, th), 4, 4)
        p.setPen(QColor("#e6e1ff"))
        p.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)

    # ---- 导出 ----

    def render_to_image(self) -> QImage:
        """所见即所得导出。"""
        img = QImage(self.size(), QImage.Format_RGB888)
        img.fill(QColor("#0b0b12"))
        p = QPainter(img)
        self.render(p)
        p.end()
        return img
