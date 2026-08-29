# -*- coding: utf-8 -*-
"""频谱计算流水线：对标 Spek 的 spek-pipeline.cc。

核心思路（复刻 Spek）：
- 频谱图列数 = 绘图区像素宽度，一列像素对应一个时间区间；
- 区间边界均匀分摊（等价于 Spek 的 Bresenham 误差累积）；
- 每个区间内做若干次加窗 FFT（hop = nfft，即不重叠），幅度取平均；
- 区间短于 nfft 时保底做一次 FFT；
- 逐列 emit 信号，UI 渐进渲染。
"""
import numpy as np
from PySide6.QtCore import QThread, Signal

from .decoder import decode_chunks

EPS = 1e-12
DB_FLOOR = -120.0

WINDOW_FUNCTIONS = ["Hann", "Hamming", "Blackman-Harris"]


def make_window(name: str, n: int) -> np.ndarray:
    """生成窗函数，系数与 Spek 保持一致。"""
    i = np.arange(n)
    cf = 2.0 * np.pi / (n - 1.0)
    coss = np.cos(cf * i)
    if name == "Hamming":
        return (0.53836 - 0.46164 * coss).astype(np.float32)
    if name == "Blackman-Harris":
        return (
            0.35875
            - 0.48829 * coss
            + 0.14128 * np.cos(2 * cf * i)
            - 0.01168 * np.cos(3 * cf * i)
        ).astype(np.float32)
    # 默认 Hann
    return (0.5 * (1.0 - coss)).astype(np.float32)


class SpectrogramWorker(QThread):
    """后台线程：解码 + STFT，逐列输出 dB 频谱（行 0 = 最低频）。"""

    column_ready = Signal(int, object)  # (列索引, float32 (bands,) dB 值)
    finished_all = Signal()
    failed = Signal(str)

    def __init__(
        self,
        path: str,
        stream: int,
        channel: int,  # -1 表示混合声道
        fft_bits: int,
        window_name: str,
        ncols: int,
        total_frames: int,
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.stream = stream
        self.channel = channel
        self.fft_bits = fft_bits
        self.window_name = window_name
        self.ncols = max(1, ncols)
        self.total_frames = total_frames
        self._stop = False

    def stop(self):
        self._stop = True

    @property
    def bands(self) -> int:
        return (1 << (self.fft_bits - 1)) + 1

    def run(self):
        try:
            self._run()
        except Exception as e:  # noqa: BLE001
            if not self._stop:
                self.failed.emit(str(e))

    # ---- 内部实现 ----

    def _run(self):
        nfft = 1 << self.fft_bits
        window = make_window(self.window_name, nfft)
        ncols = self.ncols

        chunks = []
        decoded = 0
        col = 0
        total = self.total_frames  # 可能为 0（未知时长）

        bounds = None
        buf = None
        if total > 0:
            bounds = np.rint(np.arange(ncols + 1) * (total / ncols)).astype(np.int64)
            buf = np.zeros(total, dtype=np.float32)  # 预分配，避免反复拼接

        for arr in decode_chunks(self.path, self.stream):
            if self._stop:
                return
            if 0 <= self.channel < arr.shape[0]:
                mono = arr[self.channel]
            else:
                mono = arr.mean(axis=0)
            mono = np.ascontiguousarray(mono, dtype=np.float32)
            n = mono.shape[0]
            if buf is not None and decoded + n <= total:
                buf[decoded:decoded + n] = mono
            else:
                chunks.append(mono)  # 超出预估时长或时长未知
            decoded += n

            if bounds is None:
                continue  # 时长未知：先攒数据，结束后一次性计算

            # 处理所有数据已就绪的列
            while col < ncols and bounds[col + 1] <= decoded:
                self.column_ready.emit(col, self._compute_column(buf, bounds, col, nfft, window))
                col += 1
                if self._stop:
                    return

        if self._stop:
            return

        if chunks:
            # 有溢出数据或时长未知：拼接完整缓冲并重算边界
            extra = self._assemble(chunks)
            if buf is not None:
                buf = np.concatenate([buf[: decoded - len(extra)], extra]) \
                    if len(extra) < decoded else extra
            else:
                buf = extra
            total = max(decoded, 1)
            bounds = np.rint(np.arange(ncols + 1) * (total / ncols)).astype(np.int64)
            col = 0  # 边界变了，已发的列需按新边界重发（控件会直接覆盖）

        # 收尾：计算所有剩余列（数据不足的列保底一次 FFT）
        floor = np.full(self.bands, DB_FLOOR, dtype=np.float32)
        while col < ncols and not self._stop:
            if decoded > 0 and bounds[col] < decoded:
                self.column_ready.emit(
                    col, self._compute_column(buf, bounds, col, nfft, window, eof=True)
                )
            else:
                self.column_ready.emit(col, floor)
            col += 1
        if not self._stop:
            self.finished_all.emit()

    @staticmethod
    def _assemble(chunks):
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        if len(chunks) == 1:
            return chunks[0]
        return np.concatenate(chunks)

    def _compute_column(self, buf, bounds, col, nfft, window, eof=False):
        """计算一列：区间内多次 FFT 幅度平均后转 dB。"""
        start = int(bounds[col])
        end = int(bounds[col + 1])
        if eof:
            end = min(end, len(buf))
        # FFT 触发点：列内每 nfft 帧一次（hop = nfft，与 Spek 一致）
        heads = list(range(start + nfft, end + 1, nfft))
        if not heads:
            heads = [max(end, start + 1)]  # 区间太短，保底一次
        acc = None
        count = 0
        for head in heads:
            lo = head - nfft
            hi = min(head, len(buf))
            seg = np.zeros(nfft, dtype=np.float32)
            if hi > lo:
                src_lo = max(lo, 0)
                data = buf[src_lo:hi]
                seg[nfft - len(data):] = data  # 右对齐，左侧补零
            mag = np.abs(np.fft.rfft(seg * window))
            acc = mag if acc is None else acc + mag
            count += 1
        avg = acc / max(count, 1)
        # 归一化：满幅正弦（Hann 窗）≈ 0 dB
        db = 20.0 * np.log10(avg * 4.0 / nfft + EPS)
        return db.astype(np.float32)
