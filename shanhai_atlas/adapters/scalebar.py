# -*- coding: utf-8 -*-
"""比例尺：装了 `matplotlib-scalebar` 就交给它，没装就用内置实现。

地理图的底图可能用等距圆柱、也可能用兰勃特/墨卡托——**同一段图上比例尺不是常数**，
所以这里不假装"自动算"，而是要求调用方给出 `km_per_xunit`（数据坐标 1 单位 = 多少 km），
或者给出 `lat`（度坐标下按该纬度的 111.32·cos(lat) km/° 估算）。算不准就别画，
一个标错的比例尺比没有比例尺更糟。
"""
from __future__ import annotations

import math

__all__ = ["add_scalebar", "backend", "km_per_degree"]


def backend() -> str:
    try:
        import matplotlib_scalebar  # noqa: F401
        return "matplotlib-scalebar"
    except Exception:
        return "native"


def km_per_degree(lat_deg: float) -> float:
    """该纬度上 1° 经度对应的公里数（球面近似，WGS84 子午圈略去扁率影响）。"""
    return 111.32 * math.cos(math.radians(lat_deg))


def add_scalebar(ax, length_km=100.0, *, km_per_xunit=None, lat=None, loc="lower right",
                 pad=0.03, height=0.014, segments=2, color="#2A3342", label=None, fontsize=6.0):
    """在地图轴上加比例尺。

    Parameters
    ----------
    length_km : float
        比例尺代表的长度（km）。
    km_per_xunit : float | None
        数据坐标 1 单位 = 多少 km。等距圆柱投影下通常就是 1（度）→ 用 ``lat``。
    lat : float | None
        传入时按 ``km_per_degree(lat)`` 估 `km_per_xunit`（适用于以度为单位的地图）。
    segments : int
        黑白相间的段数（2 段最容易读）。
    """
    if km_per_xunit is None:
        if lat is None:
            raise ValueError("必须给 km_per_xunit 或 lat —— 比例尺不能猜")
        km_per_xunit = km_per_degree(lat)

    if backend() == "matplotlib-scalebar":
        from matplotlib_scalebar.scalebar import ScaleBar
        sb = ScaleBar(km_per_xunit * 1000, units="m", length_fraction=None,
                      fixed_value=length_km, location=loc.replace(" ", "-"),
                      frameon=False, color=color, font_properties={"size": fontsize},
                      border_pad=0.4, sep=3, height=height * 2)
        ax.add_artist(sb)
        return sb

    # ---- 内置实现 ----
    x0, x1 = ax.get_xlim()
    span = abs(x1 - x0)
    frac = (length_km / km_per_xunit) / span          # 比例尺占轴宽的比例
    frac = min(max(frac, 0.05), 0.85)
    w = frac
    x = pad if "left" in loc else 1 - pad - w
    y = 1 - pad if "upper" in loc else pad + height + 0.012
    seg_w = w / max(int(segments), 1)
    artists = []
    for i in range(int(segments)):
        artists.append(ax.add_patch(
            __import__("matplotlib").patches.Rectangle(
                (x + i * seg_w, y), seg_w, height, transform=ax.transAxes,
                fc=color if i % 2 == 0 else "white", ec=color, lw=0.5, zorder=20,
                clip_on=False)))
    txt = label if label is not None else (
        f"{length_km:g} km" if length_km >= 1 else f"{length_km * 1000:g} m")
    ax.text(x + w / 2, y + height + 0.008, txt, transform=ax.transAxes, ha="center",
            va="bottom", fontsize=fontsize, color=color, zorder=21, clip_on=False)
    return {"rects": artists, "width_axes_frac": w, "text": txt}
