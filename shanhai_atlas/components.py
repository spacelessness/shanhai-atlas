# -*- coding: utf-8 -*-
"""版面构件：页眉、卡片、公式框、要点、数据对象标签、参数标签、流程箭头、
分组框、底栏注释、学术表格、图例、标注避让。

全部构件画在 :class:`shanhai_atlas.canvas.Canvas` 上，坐标单位为英寸（左上原点）。
每个构件都把文字登记到所属容器，``cv.audit()`` 可发现越界与压字。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import matplotlib.patheffects as pe
from matplotlib.colors import to_rgb

from .fonts import FONT
from .theme import C, TYPE, resolve_cmap

T = TYPE.diagram


def halo(width=2.0, color="white"):
    """文字白色描边（压在数据点上时保证可读）。"""
    return [pe.withStroke(linewidth=width, foreground=color)]


# ================================================================ 页眉 / 页脚
def header(cv, kicker, title, subtitle=None, x0=0.34, x1=None, y=0.36, accent_w=1.3,
           sizes=None):
    """页眉：古铜金小标（kicker）+ 黛蓝主标题 + 衬线斜体英文副题 + 金色题线。

    返回题线的 y（英寸），正文可从其下方开始排。
    """
    s = {**dict(kicker=T.kicker, title=T.title, subtitle=T.subtitle), **(sizes or {})}
    x1 = cv.W - x0 if x1 is None else x1
    page = cv.page
    cv.text(x0, y, kicker, size=s["kicker"], weight=700, color=C.gold, container=page,
            name="kicker")
    ty = y + 0.35 * s["title"] / 17.5 + 0.0
    cv.text(x0, ty, title, size=s["title"], weight=700, color=C.navy, container=page,
            name="title")
    ry = ty + 0.13
    if subtitle:
        sy = ty + 0.24 * max(s["subtitle"], 7) / 8.5
        cv.text(x0, sy, subtitle, size=s["subtitle"], style="italic", family=FONT.serif,
                color=C.gray, container=page, name="subtitle")
        ry = sy + 0.13
    cv.line([x0, x1], [ry, ry], color=C.gold, lw=0.8, z=2)
    cv.line([x0, x0 + accent_w], [ry, ry], color=C.navy, lw=2.2, z=3, solid_capstyle="butt")
    return ry


def info_box(cv, x, y, w, h, kicker, title, note=None):
    """右上角信息框（如“运行示例 RUNNING EXAMPLE”）：金色浅底 + 左侧金条。"""
    page = cv.page
    cv.rect(x, y, w, h, r=0.05, fc=C.gold_wash, ec="#E3D5BB", lw=0.6, z=2)
    cv.rect(x, y, 0.05, h, r=0.0, fc=C.gold, z=3)
    cv.text(x + 0.18, y + 0.20, kicker, size=6.5, weight=700, color=C.gold, container=page)
    cv.text(x + 0.18, y + 0.43, title, size=9.0, weight=700, color=C.navy, container=page)
    if note:
        cv.text(x + 0.18, y + 0.62, note, size=6.7, color=C.gray, container=page)


def footer_notes(cv, y, columns, x0=0.34, x1=None, gap=0.25, size=6.4, head_size=6.8):
    """底栏多列注释：[(标题, 正文或 runs), …]，列间细竖线。"""
    x1 = cv.W - x0 if x1 is None else x1
    n = len(columns)
    fw = (x1 - x0 - gap * (n - 1)) / n
    for k, (head, body) in enumerate(columns):
        fx = x0 + k * (fw + gap)
        if k:
            cv.line([fx - gap / 2, fx - gap / 2], [y - 0.02, y + 0.30], color=C.line, lw=0.5)
        cv.text(fx, y + 0.10, head, size=head_size, weight=700, color=C.gold, container=cv.page)
        runs = body if isinstance(body, list) else [(body, None)]
        cv.para(fx, y + 0.15, fw, runs, size=size, color=C.gray, leading=1.45,
                container=(fx, y, fx + fw, cv.H - 0.02), name=head)


def source_line(cv, x, y, w, runs, size=6.6):
    """单行/多行数据来源说明（“数据：” 加粗）。"""
    if isinstance(runs, str):
        runs = [("数据：", dict(weight=700, color=C.navy)), (runs, None)]
    return cv.para(x, y, w, runs, size=size, color=C.gray, leading=1.45,
                   container=(x, y - 0.05, x + w, cv.H), name="source")


# ================================================================ 卡片
@dataclass
class Card:
    x: float
    y: float
    w: float
    h: float

    @property
    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def inner(self, top, height, pad=0.08):
        """卡片内一块区域：(x, y, w, h)，top/height 相对卡片顶部。"""
        return (self.x + pad, self.y + top, self.w - 2 * pad, height)


def card(cv, x, y, w, h, title, subtitle=None, badge=None, accent=None, badge_style=None,
         title_size=None):
    """流程卡片：白底细框 + 顶部色条 + 编号徽标（圆形数字 / 胶囊文字）+ 中文标题 + 英文副题。

    badge="1"…"9" 用黛蓝圆形徽标；badge="IN"/"OUT" 等文字用古铜金胶囊。
    """
    title_size = title_size or T.h1
    is_word = badge is not None and not str(badge).isdigit()
    style = badge_style or ("pill" if is_word else "circle")
    accent = accent or (C.gold if style == "pill" else C.navy)
    box = (x, y, x + w, y + h)
    cv.rect(x, y, w, h, r=0.08, fc="white", ec="#D3DAE3", lw=0.7, z=1)
    cv.rect(x + 0.08, y, w - 0.16, 0.026, r=0.0, fc=accent, z=2)
    tx = x + 0.12
    if badge is not None and style == "pill":
        bw = cv.adv(str(badge), 6.2, 700) + 0.14
        cv.rect(x + 0.12, y + 0.15, bw, 0.22, r=0.05, fc=accent, z=3)
        cv.text(x + 0.12 + bw / 2, y + 0.31, str(badge), size=6.2, weight=700, color="white",
                ha="center", z=4)
        tx = x + 0.12 + bw + 0.10
    elif badge is not None:
        cv.circle(x + 0.26, y + 0.27, 0.135, fc=accent, z=3)
        cv.text(x + 0.26, y + 0.27, str(badge), size=9.0, weight=700, color="white",
                ha="center", va="center_baseline", family=FONT.serif, z=4)
        tx = x + 0.49
    cv.text(tx, y + 0.33, title, size=title_size, weight=700, color=C.navy, container=box,
            name=title)
    if subtitle:
        cv.text(x + 0.12, y + 0.52, subtitle, size=T.h2, style="italic", family=FONT.serif,
                color=C.gray, container=box, name=subtitle)
    return Card(x, y, w, h)


def tile(cv, x, y, w, h, fc="white", ec=None):
    """卡片内的图块底框（细发丝线）。返回容器 (x0, y0, x1, y1)。"""
    cv.rect(x, y, w, h, r=0.05, fc=fc, ec=ec or C.hair, lw=0.6, z=1.5)
    return (x, y, x + w, y + h)


def group_frame(cv, x0, y0, x1, y1, label=None, sublabel=None, label_y=None):
    """把若干卡片框成一组（浅灰蓝底），左上角组名 + 斜体副名。"""
    cv.rect(x0, y0, x1 - x0, y1 - y0, r=0.12, fc=C.frame, ec="#D6DDE7", lw=0.7, z=0.5)
    if label:
        ly = label_y if label_y is not None else y0 + 0.22
        cv.text(x0 + 0.16, ly, label, size=T.group, weight=700, color=C.navy,
                container=cv.page, name=label)
        if sublabel:
            cv.text(x0 + 0.16 + cv.adv(label, T.group, 700) + 0.12, ly, sublabel, size=7.0,
                    style="italic", family=FONT.serif, color=C.gray, container=cv.page)


def formula_box(cv, x, y, w, lines, h=None, size=None, min_size=5.6, accent=C.navy,
                pitch=0.235, container=None):
    """公式框：浅底 + 左侧色条，逐行 mathtext；过长自动缩字（不低于 min_size）。"""
    size = size or T.formula
    h = h or 0.33 + pitch * (len(lines) - 1) + 0.0
    cv.rect(x, y, w, h, r=0.04, fc=C.card, z=1.5)
    cv.rect(x, y, 0.03, h, r=0.0, fc=accent, z=1.6)
    for i, f in enumerate(lines):
        s = cv.fit_size(f, w - 0.18, size, min_size)
        cv.text(x + 0.12, y + 0.165 + i * pitch, f, size=s, color=C.ink, va="center_baseline",
                container=container, name=f"formula{i}")
    return y + h


def bullets(cv, x, y, w, items, size=None, gap=0.06, marker=C.gold, leading=1.5,
            container=None, color=C.ink):
    """方块要点列表；item 可为字符串或 runs。返回结束 y。"""
    size = size or T.body
    for it in items:
        cv.rect(x, y + size / 72 * 0.50, 0.045, 0.045, r=0.0, fc=marker, z=6)
        y, _ = cv.para(x + 0.12, y, w - 0.12, it, size=size, leading=leading, color=color,
                       container=container, name=str(it)[:16])
        y += gap
    return y


def chip(cv, cx, cy, s, size=7.0, h=0.27, padx=0.11, container=None, fc=C.gold_wash,
         ec=C.gold_line, color=C.navy):
    """数据对象标签（胶囊）：居中于 (cx, cy)。返回宽度。"""
    w = cv.adv(s, size) + 2 * padx
    cv.rect(cx - w / 2, cy - h / 2, w, h, r=h / 2, fc=fc, ec=ec, lw=0.6, z=7)
    cv.text(cx, cy + size / 72 * 0.34, s, size=size, color=color, ha="center", z=8,
            container=container, name=s)
    return w


def param_chips(cv, x, bottom, width, items, size=None, h=0.21, gap=0.06, vgap=0.05,
                container=None):
    """参数标签组：自动换行，整体底端对齐 bottom。返回顶端 y。"""
    size = size or T.chip
    rows, cx = [[]], x
    for s in items:
        w = cv.adv(s, size) + 0.16
        if cx + w > x + width + 1e-6 and cx > x:
            rows.append([])
            cx = x
        rows[-1].append((s, cx, w))
        cx += w + gap
    y0 = bottom - len(rows) * h - (len(rows) - 1) * vgap
    for r, row in enumerate(rows):
        cy = y0 + r * (h + vgap)
        for s, cx, w in row:
            cv.rect(cx, cy, w, h, r=0.04, fc="white", ec="#CDD5DF", lw=0.5, z=6)
            cv.text(cx + 0.08, cy + h / 2 + size / 72 * 0.34, s, size=size, color=C.gray, z=7,
                    container=container, name=s)
    return y0


# ================================================================ 流程
def flow_arrow(cv, p0, p1, strong=False, color=C.navy, **kw):
    return cv.arrow(p0, p1, color=color, lw=1.3 if strong else 1.0, ms=10 if strong else 7,
                    **kw)


def data_spine(cv, y, x0, x1, gaps=(), color=C.gold_line):
    """数据流脊线：贯穿各列的细金线，列间放小三角（gaps 为三角中心 x 列表）。"""
    cv.line([x0, x1], [y, y], color=color, lw=0.8, z=1.2)
    for xm in gaps:
        cv.poly([[xm - 0.035, y - 0.045], [xm + 0.04, y], [xm - 0.035, y + 0.045]], fc=C.gold,
                z=1.3)


def loop_arc(cv, x_from, x_to, y, label=None, label_y=None, color=C.clay, rad=0.13):
    """回路箭头（如“迭代 ⇄”）：从 x_from 弧形指回 x_to，可带标签。"""
    cv.arrow((x_from, y), (x_to, y), color=color, lw=0.9, ms=7, rad=rad, z=8)
    if label:
        cv.text((x_from + x_to) / 2, label_y if label_y is not None else y - 0.18, label,
                size=6.6, weight=500, color=color, ha="center", container=cv.page)


def step_columns(x0, x1, widths, gap=0.15):
    """按相对宽度切分列：返回 [(x, w), …]（总宽 = x1 − x0，含列间距）。"""
    widths = np.asarray(widths, float)
    avail = x1 - x0 - gap * (len(widths) - 1)
    ws = avail * widths / widths.sum()
    out, x = [], x0
    for w in ws:
        out.append((x, float(w)))
        x += w + gap
    return out


# ================================================================ 表格 / 图例
def table(cv, x, y, w, columns, rows, size=6.6, head_size=5.9, pitch=0.215, swatches=None,
          container=None, rule=True):
    """紧凑学术表格（无竖线）。

    columns: [(表头, 相对宽度, 对齐 "l"/"r")]；rows: [[单元格文字 | (文字, 样式 dict)], …]；
    swatches: 每行行首色块颜色（可选）。返回表格底 y。
    """
    tot = sum(c[1] for c in columns)
    xs, cx = [], x
    for name, cw, *al in columns:
        xs.append((cx, w * cw / tot, (al[0] if al else "l")))
        cx += w * cw / tot
    for (cx, cw, al), (name, *_rest) in zip(xs, columns):
        cv.text(cx + (cw if al == "r" else 0), y, name, size=head_size, color=C.gray,
                ha="right" if al == "r" else "left", container=container, name="hdr" + name)
    if rule:
        cv.line([x, x + w], [y + 0.06, y + 0.06], color=C.rule, lw=0.5, z=5)
    yy = y + 0.06 + pitch
    for i, row in enumerate(rows):
        for k, ((cx, cw, al), cell) in enumerate(zip(xs, row)):
            txt, st = (cell if isinstance(cell, tuple) else (cell, {}))
            off = 0.0
            if k == 0 and swatches:
                sz = st.get("size", size)
                rad = 0.04 * sz / 6.6
                cv.circle(cx + rad, yy - sz / 72 * 0.36, rad, fc=swatches[i], z=6)
                off = 2 * rad + 0.06
            cv.text(cx + off + (cw - off if al == "r" else 0), yy, str(txt),
                    size=st.get("size", size), weight=st.get("weight", 400),
                    color=st.get("color", C.ink), ha="right" if al == "r" else "left",
                    family=st.get("family"), container=container, name=str(txt)[:12])
        yy += pitch
    end = yy - pitch + 0.10
    if rule:
        cv.line([x, x + w], [end, end], color="#E1E6EC", lw=0.5, z=5)
    return end


def legend_item(cv, x, y, kind, label, color=C.blue, size=6.0, container=None, **kw):
    """图例条目：kind = "dot" | "ring" | "line" | "dash" | "patch" | "square"。返回结束 x。"""
    a = cv.top
    yc = y - size / 72 * 0.34
    if kind in ("dot", "ring"):
        a.scatter([x + 0.04], [yc], s=kw.get("s", 16),
                  fc=color if kind == "dot" else "white",
                  ec="white" if kind == "dot" else color, lw=0.8, zorder=60)
    elif kind in ("line", "dash"):
        cv.line([x - 0.01, x + 0.11], [yc, yc], color=color, lw=kw.get("lw", 1.0), z=60,
                top=True, ls="-" if kind == "line" else (0, (2.2, 1.6)))
    elif kind in ("patch", "square"):
        r = 0.0 if kind == "square" else 0.015
        cv.rect(x - 0.01, yc - 0.045, 0.11, 0.09, r=r, fc=to_rgb(color), z=60, top=True,
                ec=kw.get("ec", "none"), lw=0.6)
    tx = x + 0.15
    cv.text(tx, y, label, size=size, color=C.ink, top=True, container=container, name=label)
    return tx + cv.adv(label, size)


def colorbar(cv, x, y, w, h, cmap, vmin, vmax, ticks=None, label=None, vertical=True,
             size=5.0, invert=False, side="right", fmt="{:.3g}"):
    """细长色条（英寸定位）；竖条刻度默认在右侧（side="left" 可改）。"""
    cmap = resolve_cmap(cmap)
    ax = cv.inset(x, y, w, h, z=6)
    grad = np.linspace(0, 1, 128)
    ticks = ticks if ticks is not None else [vmin, vmax]
    if vertical:
        ext = (0, 1, vmax, vmin) if invert else (0, 1, vmin, vmax)
        ax.imshow(grad[::-1, None] if not invert else grad[:, None], aspect="auto", cmap=cmap,
                  extent=ext, origin="upper")
        ax.set_xticks([])
        ax.set_yticks(ticks)
        ax.set_yticklabels([fmt.format(t) for t in ticks])
        if side == "right":
            ax.yaxis.tick_right()
        ax.tick_params(labelsize=size, length=1.2, pad=1.0, width=0.4, colors=C.gray)
    else:
        ax.imshow(grad[None, :], aspect="auto", cmap=cmap, extent=(vmin, vmax, 0, 1))
        ax.set_yticks([])
        ax.set_xticks(ticks)
        ax.set_xticklabels([fmt.format(t) for t in ticks])
        ax.tick_params(labelsize=size, length=1.2, pad=1.0, width=0.4, colors=C.gray)
    for s in ax.spines.values():
        s.set_linewidth(0.3)
        s.set_color(C.axis)
    if label:
        ax.set_title(label, fontsize=size, color=C.gray, pad=7 if vertical else 2, loc="left")
    return ax


# ================================================================ 标注避让
def place_labels(anchors, obstacles, radius, bounds, angles=None, prefer=None):
    """贪心标注：在锚点周围候选位置中选与障碍 / 已放标注最远者。

    anchors/obstacles 为 [(x, y)]（同一坐标系）；bounds = (x0, x1, y0, y1)。
    prefer > 0 时偏好上方。返回每个锚点的标注位置。
    """
    angles = np.radians(np.arange(0, 360, 22.5) if angles is None else angles)
    placed = []
    for i, (x, y) in enumerate(anchors):
        others = [a for j, a in enumerate(anchors) if j != i]
        best, best_s = (x, y + radius), -1e9
        for rr in (radius, 1.35 * radius):
            for ang in angles:
                lx, ly = x + rr * np.cos(ang), y + rr * np.sin(ang)
                if not (bounds[0] <= lx <= bounds[1] and bounds[2] <= ly <= bounds[3]):
                    continue
                pts = list(obstacles) + placed + others
                dmin = min(np.hypot(lx - px, ly - py) for px, py in pts) if pts else 9.9
                s = dmin - 0.25 * rr
                if prefer is not None:
                    s += prefer * np.sin(ang)
                if s > best_s:
                    best_s, best = s, (lx, ly)
        placed.append(best)
    return placed
