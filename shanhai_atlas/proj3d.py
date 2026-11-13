# -*- coding: utf-8 -*-
"""轻量三维：正交投影点云 / 面片 / 坐标盒（不依赖 mplot3d，SVG 干净、可精确排版）。

坐标约定：x 东、y 北、z 深度（向下为正，单位任意，常用 km）。
"""

from __future__ import annotations

import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Polygon

from .theme import C


class View:
    """正交投影相机：azim 为相机方位（自北顺时针，°），elev 为仰角（°），vex 为垂向放大。"""

    def __init__(self, azim=160.0, elev=37.0, vex=1.0):
        a, e = np.radians(azim), np.radians(elev)
        self.d = np.array([np.sin(a) * np.cos(e), np.cos(a) * np.cos(e), np.sin(e)])
        self.rt = np.array([-np.cos(a), np.sin(a), 0.0])
        self.up = np.array([-np.sin(a) * np.sin(e), -np.cos(a) * np.sin(e), np.cos(e)])
        self.vex = vex

    def world(self, P):
        Q = np.array(P, float).copy()
        Q[..., 2] = -Q[..., 2] * self.vex
        return Q

    def __call__(self, P):
        """→ (u, w, depth)：屏幕横 / 纵坐标与视深（越大越靠近相机）。"""
        Q = self.world(P)
        return Q @ self.rt, Q @ self.up, Q @ self.d

    def cov2d(self, cov):
        """三维协方差在屏幕平面上的 2×2 投影（画 nσ 椭圆用）。"""
        F = np.diag([1.0, 1.0, -self.vex])
        M = np.vstack([self.rt, self.up])
        return M @ F @ cov @ F @ M.T


def draw_box(ax, view, bounds, north=True, scale=20, depth_ticks=(0, 10, 20, 30), fs=5.5,
             unit="km", depth_label="深度 km"):
    """背面三块浅色坐标面 + 深度刻度 + 底面比例尺 + 指北针。返回盒角点屏幕坐标 (u, w)。"""
    x0, x1, y0, y1, z0, z1 = bounds
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    faces = [([4, 5, 6, 7], [0, 0, 1]), ([3, 2, 6, 7], [0, 1, 0]), ([0, 1, 5, 4], [0, -1, 0]),
             ([0, 3, 7, 4], [-1, 0, 0]), ([1, 2, 6, 5], [1, 0, 0]), ([0, 1, 2, 3], [0, 0, -1])]
    u, w, _ = view(v)
    for ids, nrm in faces:
        if view.world(np.array(nrm, float)) @ view.d < 0:          # 背面
            ax.add_patch(Polygon(np.c_[u[ids], w[ids]], closed=True, fc=C.pane,
                                 ec=C.pane_edge, lw=0.45, zorder=1))
    span = max(x1 - x0, y1 - y0)
    tk = 0.02 * span
    zt = [z for z in depth_ticks if z0 <= z <= z1]
    if zt:
        eu, ew, _ = view(np.array([[x0, y0, z] for z in zt], float))
        for z, a, c in zip(zt, eu, ew):
            ax.plot([a, a - tk], [c, c], color=C.gray_lite, lw=0.45, zorder=2)
            ax.text(a - 1.5 * tk, c, f"{z:g}", fontsize=fs, color=C.gray, ha="right",
                    va="center", zorder=2)
        if depth_label:
            ax.text(eu[0] - 1.5 * tk, ew[0] + 2.2 * tk, depth_label, fontsize=fs - 0.2,
                    color=C.gray, ha="right", va="bottom", zorder=2)
    if scale:
        m = 0.055 * span
        su, sw, _ = view(np.array([[x1 - m - scale, y0 + m, z1], [x1 - m, y0 + m, z1]], float))
        ax.plot(su, sw, color=C.ink, lw=0.9, solid_capstyle="butt", zorder=4)
        ax.text(su.mean(), sw.max() + 0.8 * tk, f"{scale:g} {unit}", fontsize=fs, color=C.ink,
                ha="center", va="bottom", zorder=4)
    if north:
        m = 0.08 * span
        nu, nw, _ = view(np.array([[x0 + m, y1 - 1.6 * m, z0], [x0 + m, y1 + 0.2 * m, z0]], float))
        ax.annotate("", xy=(nu[1], nw[1]), xytext=(nu[0], nw[0]),
                    arrowprops=dict(arrowstyle="-|>", color=C.navy, lw=0.7, mutation_scale=5),
                    zorder=4)
        ax.text(nu[1], nw[1] + 0.7 * tk, "N", fontsize=fs, color=C.navy, ha="center",
                va="bottom", weight=700, zorder=4)
    return u, w


def fit_panel(ax, u, w, pad=0.04):
    """按投影后坐标范围设置等比例视窗并关闭坐标轴。"""
    ax.set_aspect("equal", adjustable="datalim")
    du, dw = np.ptp(u), np.ptp(w)
    ax.set_xlim(np.min(u) - pad * du, np.max(u) + pad * du)
    ax.set_ylim(np.min(w) - pad * dw, np.max(w) + pad * dw)
    ax.axis("off")


def scatter3d(ax, view, X, colors, size=1.2, alpha=0.6, z=3):
    """按视深由远及近绘制点云；size 取标量时 SVG 复用同一标记（文件更小）。"""
    u, w, dep = view(X)
    o = np.argsort(dep)
    c = np.asarray(colors)
    ax.scatter(u[o], w[o], s=size, c=c[o] if c.ndim > 1 else c, lw=0, alpha=alpha, zorder=z)
    return u, w


def plane_corners(centroid, v1, v2, length, width):
    """面片四角点：中心 ± L/2·v1 ± W/2·v2。"""
    c, hl, hw = np.asarray(centroid, float), length / 2.0, width / 2.0
    v1, v2 = np.asarray(v1, float), np.asarray(v2, float)
    return np.array([c - hl * v1 - hw * v2, c + hl * v1 - hw * v2,
                     c + hl * v1 + hw * v2, c - hl * v1 + hw * v2])


def draw_planes(ax, view, planes, colors, alpha=0.30, lw=0.9, z=6):
    """按视深排序画若干面片；planes 为四角点数组列表。返回 [(u, w)]。"""
    items = []
    for j, P in enumerate(planes):
        cu, cw, cd = view(P)
        items.append((cd.mean(), j, cu, cw))
    out = [None] * len(planes)
    for _, j, cu, cw in sorted(items):
        ax.add_patch(Polygon(np.c_[cu, cw], closed=True, fc=(*to_rgb(colors[j]), alpha),
                             ec=colors[j], lw=lw, zorder=z))
        out[j] = (cu, cw)
    return out
