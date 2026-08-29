# -*- coding: utf-8 -*-
"""调色板：移植自 Spek 的 spek-palette.cc，并新增章鱼特色配色。

所有调色板输入均为归一化电平 level ∈ [0, 1]，输出 (256, 3) uint8 查找表。
"""
import numpy as np

LUT_SIZE = 256


def _spectrum_lut() -> np.ndarray:
    """Dan Bruton 可见光波长算法（Spek 原版，向量化）。"""
    lv = np.linspace(0.0, 1.0, LUT_SIZE) * 0.6625
    r = np.zeros(LUT_SIZE)
    g = np.zeros(LUT_SIZE)
    b = np.zeros(LUT_SIZE)

    m = (lv >= 0) & (lv < 0.15)
    r[m] = (0.15 - lv[m]) / 0.225
    b[m] = 1.0
    m = (lv >= 0.15) & (lv < 0.275)
    g[m] = (lv[m] - 0.15) / 0.125
    b[m] = 1.0
    m = (lv >= 0.275) & (lv < 0.325)
    g[m] = 1.0
    b[m] = (0.325 - lv[m]) / 0.05
    m = (lv >= 0.325) & (lv < 0.5)
    r[m] = (lv[m] - 0.325) / 0.175
    g[m] = 1.0
    m = (lv >= 0.5) & (lv < 0.6625)
    r[m] = 1.0
    g[m] = (0.6625 - lv[m]) / 0.1625

    # 低强度渐暗修正
    cf = np.where(lv < 0.1, lv / 0.1, 1.0) * 255.0
    rgb = np.stack([r * cf, g * cf, b * cf], axis=1) + 0.5
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _sox_lut() -> np.ndarray:
    """SoX 经典配色（Rob Sykes 正弦曲线混合，Spek 默认）。"""
    lv = np.linspace(0.0, 1.0, LUT_SIZE)

    r = np.zeros(LUT_SIZE)
    m = (lv >= 0.13) & (lv < 0.73)
    r[m] = np.sin((lv[m] - 0.13) / 0.60 * np.pi / 2.0)
    r[lv >= 0.73] = 1.0

    g = np.zeros(LUT_SIZE)
    m = (lv >= 0.6) & (lv < 0.91)
    g[m] = np.sin((lv[m] - 0.6) / 0.31 * np.pi / 2.0)
    g[lv >= 0.91] = 1.0

    b = np.zeros(LUT_SIZE)
    m = lv < 0.60
    b[m] = 0.5 * np.sin(lv[m] / 0.6 * np.pi)
    m = lv >= 0.78
    b[m] = (lv[m] - 0.78) / 0.22

    rgb = np.stack([r, g, b], axis=1) * 255.0 + 0.5
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _mono_lut() -> np.ndarray:
    """灰度。"""
    v = (np.linspace(0.0, 1.0, LUT_SIZE) * 255.0 + 0.5).astype(np.uint8)
    return np.stack([v, v, v], axis=1)


def _octopus_lut() -> np.ndarray:
    """章鱼特色：深海黑 → 章鱼紫 → 品红 → 橙 → 亮白（触手渐变）。"""
    lv = np.linspace(0.0, 1.0, LUT_SIZE)
    stops = np.array([
        [0.00, 8, 6, 20],       # 深海黑
        [0.25, 61, 26, 120],    # 暗紫
        [0.50, 147, 51, 234],   # 章鱼紫
        [0.70, 236, 72, 153],   # 品红
        [0.85, 251, 146, 60],   # 橙
        [1.00, 255, 247, 237],  # 亮白
    ])
    xs = stops[:, 0]
    rgb = np.stack(
        [np.interp(lv, xs, stops[:, i]) for i in (1, 2, 3)], axis=1
    )
    return np.clip(rgb + 0.5, 0, 255).astype(np.uint8)


PALETTES = {
    "章鱼 Octopus": _octopus_lut,
    "SoX 经典": _sox_lut,
    "光谱 Spectrum": _spectrum_lut,
    "灰度 Mono": _mono_lut,
}
DEFAULT_PALETTE = "章鱼 Octopus"

_cache: dict = {}


def get_lut(name: str) -> np.ndarray:
    """取调色板查找表（带缓存），返回 (256, 3) uint8。"""
    if name not in _cache:
        _cache[name] = PALETTES.get(name, _octopus_lut)()
    return _cache[name]
