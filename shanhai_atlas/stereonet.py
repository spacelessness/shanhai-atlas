# -*- coding: utf-8 -*-
"""下半球等面积投影（Schmidt 网）：极点、小圆（容差锥）、大圆（平面）。

约定：法向量 (x 东, y 北, z 向下)，自动翻到下半球（n_z ≥ 0）；
半径 r = √2 · sin(θ/2)，θ 为法向与竖直方向夹角。
"""

from __future__ import annotations

import numpy as np
from matplotlib.patches import Circle

from .theme import C


def normal_from_strike_dip(strike, dip):
    """右手定则走向 / 倾角 → 单位法向（下半球，x 东、y 北、z 下）。

    倾向 = strike + 90°；节面内水平指向 = (sin(dd), cos(dd))，法向量取其负的倾角投影，
    保证倾向 = strike + 90°（2026-10-20 修正上游水平分量符号镜像 bug）。
    """
    s, d = np.radians(strike), np.radians(dip)
    dd = s + np.pi / 2                          # 倾向
    n = np.array([-np.sin(dd) * np.sin(d), -np.cos(dd) * np.sin(d), np.cos(d)])
    return n / np.linalg.norm(n)


def pole_xy(n):
    n = np.asarray(n, float)
    n = n / np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.where(n[..., 2:3] < 0, -n, n)
    tr = np.arctan2(n[..., 0], n[..., 1])
    r = np.sqrt(2.0) * np.sin(np.arccos(np.clip(n[..., 2], -1, 1)) / 2.0)
    return r * np.sin(tr), r * np.cos(tr)


def small_circle(n, alpha_deg, m=200):
    """绕法向 n、半角 alpha 的小圆（只保留下半球部分，越界截断不折返）。返回线段列表。"""
    n = np.asarray(n, float) / np.linalg.norm(n)
    a = np.cross(n, [0.0, 0.0, 1.0])
    a = a / np.linalg.norm(a) if np.linalg.norm(a) > 1e-6 else np.array([1.0, 0.0, 0.0])
    b = np.cross(n, a)
    t = np.linspace(0, 2 * np.pi, m)
    al = np.radians(alpha_deg)
    v = np.cos(al) * n[None, :] + np.sin(al) * (np.cos(t)[:, None] * a + np.sin(t)[:, None] * b)
    keep = v[:, 2] >= 0
    x, y = pole_xy(v)
    segs, cur = [], []
    for i in np.r_[np.arange(len(x)), 0]:
        if keep[i]:
            cur.append([x[i], y[i]])
        elif cur:
            segs.append(np.array(cur))
            cur = []
    if cur:
        segs.append(np.array(cur))
    if len(segs) > 1 and keep[0] and keep[-1]:
        segs = [np.vstack([segs[-1], segs[0]])] + segs[1:-1]
    return [sg for sg in segs if len(sg) > 1]


def great_circle(strike, dip, m=181):
    """平面（走向 / 倾角）的大圆迹线（下半球）。"""
    n = normal_from_strike_dip(strike, dip)
    s = np.radians(strike)
    u = np.array([np.sin(s), np.cos(s), 0.0])                  # 走向方向
    w = np.cross(n, u)
    w = w if w[2] >= 0 else -w                                  # 倾向方向（向下）
    t = np.linspace(0, np.pi, m)
    v = np.cos(t)[:, None] * u + np.sin(t)[:, None] * w
    x, y = pole_xy(v)
    return np.c_[x, y]


def net(ax, dip_circles=(30, 60), tick_every=30, fs=6.0, north=True):
    """网底：外圆、方位短刻度、倾角参考圆、中心十字、N。"""
    ax.add_patch(Circle((0, 0), 1.0, fc="white", ec=C.navy, lw=0.8, zorder=1))
    for ang in dip_circles:
        ax.add_patch(Circle((0, 0), np.sqrt(2) * np.sin(np.radians(ang) / 2), fc="none",
                            ec="#E3E8EE", lw=0.45, zorder=1))
    for az in range(0, 360, tick_every):
        a = np.radians(az)
        ax.plot([0.95 * np.sin(a), np.sin(a)], [0.95 * np.cos(a), np.cos(a)], color=C.navy,
                lw=0.5, zorder=2)
    ax.plot([-0.04, 0.04], [0, 0], color=C.gray_lite, lw=0.5)
    ax.plot([0, 0], [-0.04, 0.04], color=C.gray_lite, lw=0.5)
    if north:
        ax.text(0, 1.06, "N", fontsize=fs, color=C.navy, ha="center", va="bottom", weight=700)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlim(-1.18, 1.18)
    ax.set_ylim(-1.14, 1.20)
    ax.axis("off")
