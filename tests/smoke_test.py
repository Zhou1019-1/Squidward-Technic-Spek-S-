# -*- coding: utf-8 -*-
"""冒烟测试：对 test_media 下所有文件验证 probe + decode + worker 计算。

注意：本环境 stdout 捕获不可靠，日志直接写文件 smoke_log.txt。
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop

from octopus.decoder import probe
from octopus.worker import SpectrogramWorker

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(BASE, "test_media")
LOG = open(os.path.join(BASE, "tests", "smoke_log.txt"), "w", encoding="utf-8")


def log(*args):
    LOG.write(" ".join(str(a) for a in args) + "\n")
    LOG.flush()


def test_file(path):
    log(f"\n=== {os.path.basename(path)} ===")
    info = probe(path)
    log(
        f"codec={info.codec_name} br={info.bit_rate} sr={info.sample_rate} "
        f"bits={info.bits_per_sample} ch={info.channels} dur={info.duration:.2f}s "
        f"frames={info.total_frames} streams={info.streams}"
    )
    assert info.sample_rate > 0, "采样率异常"
    assert info.channels > 0, "声道数异常"

    cols = {}
    worker = SpectrogramWorker(
        path=path, stream=0, channel=-1, fft_bits=11,
        window_name="Hann", ncols=200, total_frames=info.total_frames,
    )
    worker.column_ready.connect(lambda i, db: cols.__setitem__(i, db))

    loop = QEventLoop()
    ok = {"done": False}
    worker.finished_all.connect(lambda: (ok.__setitem__("done", True), loop.quit()))
    worker.failed.connect(lambda m: (log("FAILED:", m), loop.quit()))

    t0 = time.time()
    worker.start()
    loop.exec()
    worker.wait(10000)
    dt = time.time() - t0

    log(f"columns={len(cols)}/200 done={ok['done']} time={dt:.2f}s")
    assert len(cols) == 200, f"列数不足: {len(cols)}"
    sample = cols[100]
    log(
        f"col100: bands={len(sample)} max={sample.max():.1f}dB "
        f"min={sample.min():.1f}dB mean={sample.mean():.1f}dB"
    )
    assert len(sample) == 1025, "频带数异常"
    assert np.isfinite(sample).all(), "存在非法值"
    assert sample.max() > -60, f"信号电平过低({sample.max():.1f}dB)，疑似全零"

    # 验证 16kHz 高切特征：16k 以上频段应显著低于 8-16k 频段
    nyq = info.sample_rate / 2
    if nyq >= 20000:
        b16k = int(16000 / nyq * 1024)
        b8k = int(8000 / nyq * 1024)
        lo = sample[b8k:b16k].mean()
        hi = sample[b16k + 10:].mean()
        log(f"8-16kHz均值={lo:.1f}dB  >16kHz均值={hi:.1f}dB  落差={lo - hi:.1f}dB")


def main():
    app = QCoreApplication(sys.argv)
    files = sorted(os.listdir(MEDIA_DIR))
    assert files, f"测试目录为空: {MEDIA_DIR}"
    log(f"发现 {len(files)} 个测试文件: {files}")
    n_pass = 0
    for name in files:
        try:
            test_file(os.path.join(MEDIA_DIR, name))
            n_pass += 1
        except Exception:
            log(traceback.format_exc())
    log(f"\n通过 {n_pass}/{len(files)}")
    LOG.close()
    # 退出码反映成败，方便终端判断
    sys.exit(0 if n_pass == len(files) else 1)


if __name__ == "__main__":
    main()
