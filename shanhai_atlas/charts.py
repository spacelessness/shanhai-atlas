# -*- coding: utf-8 -*-
"""数据图：学术风格坐标轴与常用标注。

原则：去掉上 / 右框线；轴线与刻度用浅灰（#AEB7C2，0.5 pt）；网格极浅（#EDF0F4）；
刻度文字灰、轴标题墨色；分类数据用 ``theme.SERIES``，连续量用 ``sha.*`` 色带；
重点只用一个强调色（古铜金或陶土橙）。
"""

from __future__ import annotations

import numpy as np
import matplotlib.patheffects as pe

from .fonts import FONT
from .theme import C


def style_axes(ax, grid="y", spines=("left", "bottom"), tick_size=6.0, label_size=6.6,
               lw=0.5, ticklen=2.0, pad=1.5):
    """统一坐标轴样式。grid ∈ {"x", "y", "both", None}。"""
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(s in spines)
        ax.spines[s].set_color(C.axis)
        ax.spines[s].set_linewidth(lw)
    ax.tick_params(labelsize=tick_size, length=ticklen, width=lw, pad=pad, colors=C.gray)
    ax.xaxis.label.set_size(label_size)
    ax.yaxis.label.set_size(label_size)
    ax.xaxis.label.set_color(C.ink)
    ax.yaxis.label.set_color(C.ink)
    if grid:
        ax.grid(True, axis=grid, color=C.grid, lw=0.6, zorder=0)
        ax.set_axisbelow(True)
    else:
        ax.grid(False)
    return ax


def panel_label(ax, letter, x=-0.02, y=1.02, size=8.0, paren=False, color=C.navy):
    """面板编号 a / b / c（或 (a)），位于轴左上外侧。"""
    s = f"({letter})" if paren else letter
    return ax.text(x, y, s, transform=ax.transAxes, fontsize=size, weight=700, color=color,
                   ha="right", va="bottom", family=FONT.cjk)


def panel_title(ax, title, sub=None, size=7.0, x=0.0, y=1.02):
    """面板小标题（左对齐，黛蓝加粗）+ 可选灰色说明。"""
    t = ax.text(x, y, title, transform=ax.transAxes, fontsize=size, weight=700, color=C.navy,
                ha="left", va="bottom")
    if sub:
        ax.figure.canvas.draw()
        bb = t.get_window_extent()
        inv = ax.transAxes.inverted()
        x1 = inv.transform((bb.x1, bb.y0))[0]
        ax.text(x1 + 0.02, y, sub, transform=ax.transAxes, fontsize=size - 1.0, color=C.gray,
                ha="left", va="bottom")
    return t


def note(ax, x, y, text, size=5.6, color=C.gray, ha="left", va="center", halo=True, **kw):
    """数据坐标处的轻量注释（带白色描边）。"""
    pe_ = [pe.withStroke(linewidth=2.0, foreground="white")] if halo else None
    return ax.text(x, y, text, fontsize=size, color=color, ha=ha, va=va, path_effects=pe_,
                   **kw)


def callout(ax, xy, xytext, text, size=5.6, color=C.gray, arrow_color=None, ha="left",
            va="center"):
    """引线标注：浅灰细箭头 + 灰字。"""
    return ax.annotate(text, xy=xy, xytext=xytext, fontsize=size, color=color, ha=ha, va=va,
                       arrowprops=dict(arrowstyle="-|>", color=arrow_color or C.gray_lite,
                                       lw=0.45, mutation_scale=4, shrinkA=0, shrinkB=1))


def highlight_min(ax, x, y, color=C.gold, label=None, size=5.6):
    """在曲线最小值处画强调点 + 竖向虚线 + 标签（如 BIC 最优 K*）。"""
    i = int(np.argmin(y))
    ax.axvline(x[i], color=color, lw=0.6, ls=(0, (2.2, 1.6)), zorder=1)
    ax.scatter([x[i]], [y[i]], s=22, color=color, ec="white", lw=0.7, zorder=5)
    if label:
        note(ax, x[i], y[i], label, size=size, color=color, ha="center", va="top")
    return i


def bar_labels(ax, xs, ys, fmt="{:g}", size=5.4, dy=0.0, color=C.ink):
    for x, y in zip(xs, ys):
        ax.text(x, y + dy, fmt.format(y), fontsize=size, color=color, ha="center", va="bottom")
