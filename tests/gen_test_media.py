# -*- coding: utf-8 -*-
"""生成测试音频：扫频 + 高切白噪声（模拟真假无损），并编码为多种格式。"""
import os

import av
import numpy as np

MEDIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_media")
os.makedirs(MEDIA, exist_ok=True)

SR = 44100
DUR = 5.0
t = np.arange(int(SR * DUR)) / SR

# 对数扫频 20Hz → 20kHz
f0, f1 = 20.0, 20000.0
k = (f1 / f0) ** (1 / DUR)
phase = 2 * np.pi * f0 * (k ** t - 1) / np.log(k)
sweep = 0.6 * np.sin(phase)

# 16kHz 高切白噪声（模拟"假无损"：频谱在 16kHz 处截断）
rng = np.random.default_rng(42)
noise = rng.standard_normal(len(t)).astype(np.float64)
# 简单 FFT 低通
spec = np.fft.rfft(noise)
freqs = np.fft.rfftfreq(len(t), 1 / SR)
spec[freqs > 16000] = 0
noise_lp = np.fft.irfft(spec)
noise_lp *= 0.15 / np.max(np.abs(noise_lp))

left = (sweep + noise_lp).astype(np.float32)
right = (0.8 * sweep).astype(np.float32)
stereo = np.stack([left, right])  # (2, N)


def write_wav(path):
    import wave
    pcm = (np.clip(stereo, -1, 1).T * 32767).astype(np.int16)  # (N, 2) interleaved
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def encode(path, codec, bit_rate=None):
    container = av.open(path, "w")
    kwargs = {}
    if bit_rate:
        kwargs["bit_rate"] = bit_rate
    stream = container.add_stream(codec, rate=SR, **kwargs)
    stream.layout = "stereo"

    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SR)
    frame = av.AudioFrame.from_ndarray(
        np.ascontiguousarray(stereo), format="fltp", layout="stereo"
    )
    frame.sample_rate = SR
    for r in resampler.resample(frame):
        r.sample_rate = SR
        for packet in stream.encode(r):
            container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()


write_wav(os.path.join(MEDIA, "base.wav"))
print("base.wav ok")

for fname, codec, br in [
    ("test.flac", "flac", None),
    ("test.m4a", "aac", 128000),
    ("test.opus", "opus", 96000),
    ("test.mp3", "libmp3lame", 192000),
    ("test.mp3", "mp3", 192000),  # 无 libmp3lame 时退回内置 mp3
]:
    try:
        encode(os.path.join(MEDIA, fname), codec, br)
        print(fname, "ok")
    except Exception as e:
        print(fname, "skip:", e)

print("done")
