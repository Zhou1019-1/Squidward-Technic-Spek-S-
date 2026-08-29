# -*- coding: utf-8 -*-
"""音频解码层：基于 PyAV(FFmpeg)，对标 Spek 的 spek-audio.cc。

职责：
- 探测音频流信息（编码、码率、采样率、位深、声道数、时长）
- 增量解码并统一归一化为 float32 [-1, 1] 的 (channels, samples) 数据块
"""
from dataclasses import dataclass, field

import av
import numpy as np


@dataclass
class AudioInfo:
    path: str = ""
    codec_name: str = ""
    bit_rate: int = 0
    sample_rate: int = 0
    bits_per_sample: int = 0
    channels: int = 0
    duration: float = 0.0
    streams: int = 1
    total_frames: int = 0  # duration * sample_rate


def _bits_from_format(fmt_name: str) -> int:
    """从采样格式名推断位深，如 s16/s32/flt/dbl。"""
    if not fmt_name:
        return 0
    name = fmt_name.rstrip("p")  # 去掉 planar 后缀
    if name.startswith("s") or name.startswith("u"):
        try:
            return int(name[1:])
        except ValueError:
            return 0
    if name == "flt":
        return 32
    if name == "dbl":
        return 64
    return 0


# 有损编码：位深无意义（Spek 对 AAC/WMA 等同样只报码率）
LOSSY_CODECS = {"aac", "mp3", "mp2", "vorbis", "opus", "wmav1", "wmav2", "musepack8"}


def probe(path: str, stream_index: int = 0) -> AudioInfo:
    """打开文件并读取音频流元数据。"""
    info = AudioInfo(path=path)
    container = av.open(path)
    try:
        audio_streams = [s for s in container.streams if s.type == "audio"]
        info.streams = len(audio_streams)
        if not audio_streams:
            raise ValueError("文件不包含音频流")
        if stream_index >= len(audio_streams):
            stream_index = 0
        s = audio_streams[stream_index]
        ctx = s.codec_context

        info.codec_name = getattr(ctx, "name", "") or ""
        try:
            long_name = ctx.codec.long_name
            if long_name:
                info.codec_name = long_name
        except Exception:
            pass

        info.bit_rate = s.bit_rate or container.bit_rate or 0
        info.sample_rate = ctx.sample_rate or 0

        # 位深：优先解析解码器采样格式
        try:
            fmt_name = ctx.format.name if ctx.format else ""
        except Exception:
            fmt_name = ""
        info.bits_per_sample = _bits_from_format(fmt_name)
        if (ctx.name or "") in LOSSY_CODECS:
            info.bits_per_sample = 0

        try:
            info.channels = ctx.layout.nb_channels
        except Exception:
            info.channels = getattr(ctx, "channels", 0) or 0

        duration = 0.0
        if s.duration is not None and s.time_base is not None:
            duration = float(s.duration * s.time_base)
        elif container.duration:
            duration = container.duration / 1_000_000.0
        info.duration = duration
        info.total_frames = int(round(duration * info.sample_rate)) if info.sample_rate else 0
    finally:
        container.close()
    return info


def decode_chunks(path: str, stream_index: int = 0):
    """增量解码生成器。

    每次 yield 一个 float32 数组，形状 (channels, n_samples)，
    数值范围 [-1, 1]。fltp 平面格式天然满足该布局。
    """
    container = av.open(path)
    try:
        audio_streams = [s for s in container.streams if s.type == "audio"]
        if not audio_streams:
            return
        if stream_index >= len(audio_streams):
            stream_index = 0
        stream = audio_streams[stream_index]
        # 统一重采样为 float32 平面格式，保持原采样率与声道布局
        resampler = av.AudioResampler(format="fltp")
        for frame in container.decode(stream):
            for r in resampler.resample(frame):
                arr = r.to_ndarray()
                if arr.ndim == 1:
                    arr = arr.reshape(1, -1)
                yield np.ascontiguousarray(arr, dtype=np.float32)
        # 冲刷重采样器尾部
        for r in resampler.resample(None):
            arr = r.to_ndarray()
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.shape[1] > 0:
                yield np.ascontiguousarray(arr, dtype=np.float32)
    finally:
        container.close()
