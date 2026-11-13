#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""示例 01 · 方法流程图（模型结构图模板）：地形晕渲算法，从 DEM 到成图。

版式与 BayesFault 模型结构图同源：输入 → ①–④ 核心步骤 → 输出，每列 =
「编号 + 标题 → 真实中间结果小图 → 数据对象 → 公式 → 要点 → 参数标签」。
所有小图都是程序对同一份真实 DEM（matplotlib 自带 3″ 地形样例）的实际中间输出。

复用：复制本文件，改 ``COLUMNS``（标题 / 公式 / 要点 / 参数）和各 ``tile_*`` 小图函数即可，
排版、配色、自检、导出全部沿用。

    python examples/ex01_structure_figure.py [--out output] [--formats svg,png]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import shanhai_atlas as sha                                         # noqa: E402
from shanhai_atlas import terrain                                  # noqa: E402
from shanhai_atlas.geo import GeoMap                               # noqa: E402
from shanhai_atlas.theme import C, CMAPS                           # noqa: E402

AZ, ALT, VEX, STRENGTH = 315.0, 45.0, 1.0, 0.62


# ================================================================ 1. 数据与中间结果
def compute():
    dem = terrain.sample_dem("jacksboro")
    z = dem.z
    slope = terrain.slope_deg(dem, VEX)
    hs = terrain.hillshade(dem, AZ, ALT, VEX, multidirectional=True)
    lo, hi = np.percentile(z, 1), np.percentile(z, 99.5)
    tint = CMAPS.terrain(np.clip((z - lo) / (hi - lo), 0, 1))[..., :3]
    rgb = terrain.shade(dem, sea=False, strength=STRENGTH, altitude=ALT, vert_exag=VEX)
    dx, dy = dem.spacing_m()
    return dict(dem=dem, z=z, slope=slope, hs=hs, tint=tint, rgb=rgb, lo=lo, hi=hi, dx=dx, dy=dy)


# ================================================================ 2. 小图
def _img(ax, d, arr, **kw):
    ax.imshow(arr, extent=d["dem"].extent, origin="upper", interpolation="bilinear", **kw)
    ax.set_aspect(1 / math.cos(math.radians(sum(d["dem"].extent[2:]) / 2)))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(C.pane_edge)
        s.set_linewidth(0.5)


def img_box(t, bar=True):
    """小图区域：顶部留标题、底部留图注、右侧留色条。"""
    return (t[0] + 0.10, t[1] + 0.30, t[2] - (0.52 if bar else 0.20), t[3] - 0.62)


def bar_at(cv, t, ax, cmap, vmin, vmax):
    """色条顶端与小图实际顶端对齐（小图受纵横比约束后居中）。"""
    ax.apply_aspect()
    top = (1 - ax.get_position().y1) * cv.H
    sha.colorbar(cv, t[0] + t[2] - 0.38, top, 0.05, 0.62, cmap, vmin, vmax,
                ticks=[vmin, vmax], fmt="{:.0f}")


def caption(cv, t, s):
    cv.text(t[0] + 0.10, t[1] + t[3] - 0.10, s, size=5.6, color=C.gray, container=box(t),
            top=True)


def tile_input(cv, t, d):
    ax = cv.inset(*img_box(t))
    _img(ax, d, d["z"], cmap=CMAPS.navy, vmin=d["z"].min(), vmax=d["z"].max())
    bar_at(cv, t, ax, CMAPS.navy, float(d["z"].min()), float(d["z"].max()))
    cv.text(t[0] + 0.10, t[1] + 0.20, "高程 z（m）", size=6.0, weight=700, color=C.navy,
            container=box(t), top=True)
    e = d["dem"].extent
    caption(cv, t, f"{e[2]:.2f}–{e[3]:.2f}°N · {-e[1]:.2f}–{-e[0]:.2f}°W")


def tile_slope(cv, t, d):
    ax = cv.inset(*img_box(t))
    vmax = float(np.percentile(d["slope"], 99))
    _img(ax, d, d["slope"], cmap=CMAPS.gold, vmin=0, vmax=vmax)
    bar_at(cv, t, ax, CMAPS.gold, 0.0, vmax)
    cv.text(t[0] + 0.10, t[1] + 0.20, "坡度 θ（°）", size=6.0, weight=700, color=C.navy,
            container=box(t), top=True)
    caption(cv, t, "颜色越深 = 坡度越大（P99 截断）")


def tile_hillshade(cv, t, d):
    ax = cv.inset(*img_box(t, bar=False))
    _img(ax, d, d["hs"], cmap="gray", vmin=0, vmax=1)
    cv.text(t[0] + 0.10, t[1] + 0.20, "阴影强度 I", size=6.0, weight=700, color=C.navy,
            container=box(t), top=True)
    # 四方位光源罗盘
    r, cx, cy = 0.17, t[0] + t[2] - 0.33, t[1] + 0.52
    cv.circle(cx, cy, r + 0.07, fc="white", ec=C.pane_edge, lw=0.5, z=60, top=True)
    for az in (225, 270, 315, 360):
        a = math.radians(az)
        x1, y1 = cx + r * math.sin(a), cy - r * math.cos(a)
        cv.arrow((x1, y1), (cx + 0.02 * math.sin(a), cy - 0.02 * math.cos(a)), color=C.gold,
                 lw=0.8, ms=4.5, z=61, top=True)
    cv.text(cx, cy - r - 0.10, "N", size=5.0, weight=700, color=C.navy, ha="center", top=True,
            z=61)
    caption(cv, t, "右上：四个光源方位 225°–360°")


def tile_tint(cv, t, d):
    ax = cv.inset(*img_box(t))
    _img(ax, d, d["tint"])
    bar_at(cv, t, ax, CMAPS.terrain, float(d["lo"]), float(d["hi"]))
    cv.text(t[0] + 0.10, t[1] + 0.20, "色带映射 c", size=6.0, weight=700, color=C.navy,
            container=box(t), top=True)
    caption(cv, t, "低饱和暖色 · 只表达高低层次")


def tile_composite(cv, t, d):
    ax = cv.inset(*img_box(t, bar=False))
    _img(ax, d, d["rgb"])
    cv.text(t[0] + 0.10, t[1] + 0.20, "c × f（晕渲）", size=6.0, weight=700, color=C.navy,
            container=box(t), top=True)
    caption(cv, t, "平地保持原色 · 向光坡提亮 · 背光坡压暗")


def tile_output(cv, t, d):
    ax = cv.inset(t[0] + 0.10, t[1] + 0.30, t[2] - 0.20, t[3] - 0.62)
    dem = d["dem"]
    m = GeoMap(ax, dem.extent)
    terrain.draw(ax, dem, rgb=d["rgb"])
    terrain.contours(ax, dem, interval=50, index_every=5, lw=0.18, index_lw=0.42, alpha=0.40)
    m.scale_bar(10, segments=2, loc=(0.06, 0.06), height_in=0.035, size=5.0)
    m.north_arrow(loc=(0.90, 0.80), size_in=0.22, fontsize=6.5)
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(C.navy)
        s.set_linewidth(0.6)
    cv.text(t[0] + 0.10, t[1] + 0.20, "晕渲 + 等高线（50 m）", size=6.0, weight=700,
            color=C.navy, container=box(t), top=True)
    caption(cv, t, "计曲线 250 m · 比例尺按中纬度换算")


def box(t):
    return (t[0], t[1], t[0] + t[2], t[1] + t[3])


# ================================================================ 3. 文字内容
def columns(d):
    ny, nx = d["z"].shape
    med = float(np.median(d["slope"]))
    return [
        dict(badge="IN", title="数字高程模型", sub="Digital elevation model",
             chip=rf"$\mathbf{{Z}}\in\mathbb{{R}}^{{{ny}\times {nx}}}$", tile=tile_input,
             forms=[r"$z_{ij}=z(\lambda_j,\varphi_i)$  规则经纬网格",
                    r"$\Delta x=\Delta\lambda\cdot 111\,320\,\cos\varphi_0$ m",
                    r"$\Delta y=\Delta\varphi\cdot 110\,574$ m"],
             bullets=["3″（≈ 90 m）栅格：每个像元一个高程值，行自北向南、列自西向东。",
                      "先把经纬度间距换算为米，坡度与光照才有正确的几何尺度。",
                      "load_dem() 读 GeoTIFF / ASCII / NetCDF；fetch_terrarium() 在线取任意区域。"],
             params=[f"{nx} × {ny} 像元", f"Δx ≈ {d['dx']:.0f} m", f"Δy ≈ {d['dy']:.0f} m",
                     f"高程 {d['z'].min():.0f}–{d['z'].max():.0f} m"]),
        dict(badge="1", title="梯度与法向", sub="Gradient · surface normal",
             chip=r"$(p,\,q),\ \hat{\mathbf{n}}$", tile=tile_slope,
             forms=[r"$p=\partial z/\partial x,\ \ q=\partial z/\partial y$  （中心差分）",
                    r"$\hat{\mathbf{n}}=(-p,\,-q,\,1)\,/\sqrt{1+p^2+q^2}$",
                    r"坡度 $\theta=\arctan\sqrt{p^2+q^2}$"],
             bullets=["中心差分求偏导，边缘自动退化为单侧差分；垂向放大 V 直接乘在 p、q 上。",
                      "法向量决定像元朝向；坡向 = 下坡方向方位角 atan2(−p, −q)。",
                      "坡度图本身可用于断层陡坎识别、滑坡易发性等分析。"],
             params=[f"V = {VEX:g}", "中心差分", f"坡度中位数 {med:.1f}°"]),
        dict(badge="2", title="多方向光照", sub="Multidirectional hillshading",
             chip=r"$I\in[0,\,1]$", tile=tile_hillshade,
             forms=[r"$I_a=\max(0,\ \hat{\mathbf{n}}\cdot\hat{\boldsymbol{\ell}}_a)$",
                    r"$\hat{\boldsymbol{\ell}}_a=(\sin a\,\cos e,\ \cos a\,\cos e,\ \sin e)$",
                    r"$I={\sum}_a w_a I_a/2,\ \ w_a=\cos^2(\alpha-a)$"],
             bullets=["Lambert 余弦定律：表面越正对光源越亮；高度角 e = 45°，平地亮度 sin e。",
                      "Mark（1992）斜向加权：四个方位按坡向 α 加权，任意走向的山脊都有立体感。",
                      "四个权重之和恒为 2，平地亮度与单光源一致，色调不漂移。"],
             params=["a = 225 / 270 / 315 / 360°", f"e = {ALT:g}°", "Σw = 2"]),
        dict(badge="3", title="分层设色", sub="Hypsometric tinting",
             chip=r"$\mathbf{c}\in[0,\,1]^3$", tile=tile_tint,
             forms=[r"$\mathbf{c}=\mathrm{cmap}\left((z-z_{lo})/(z_{hi}-z_{lo})\right)$",
                    r"$z_{lo},\,z_{hi}=P_{1},\,P_{99.5}$  （百分位截断）",
                    "色带 sha.terrain：灰绿 → 浅沙 → 驼 → 岩灰"],
             bullets=["低饱和暖色带，只表达高低层次，不与叠加的数据点争夺注意力。",
                      "百分位截断防止极端值压缩色阶；海域另用 sha.sea 水深色带。",
                      "色带与 PPT 主题同源（theme.CMAPS），论文与汇报配色一致。"],
             params=[f"P1 = {d['lo']:.0f} m", f"P99.5 = {d['hi']:.0f} m", "sha.terrain"]),
        dict(badge="4", title="明暗合成", sub="Shading composite",
             chip=r"$\mathbf{rgb}=\mathbf{c}\cdot f$", tile=tile_composite,
             forms=[r"$f=1-s+s\,I/\sin e$",
                    r"$\mathbf{rgb}=\mathbf{c}\,f\quad (f\leq 1)$",
                    r"$\mathbf{rgb}=\mathbf{c}+(1-\mathbf{c})(f-1)\cdot 0.9\quad (f>1)$"],
             bullets=["以平地亮度归一化：平地 f = 1 保持色带原色，向光坡提亮、背光坡压暗。",
                      f"强度 s = {STRENGTH:g}：立体感清晰，同时不把低处颜色压脏。",
                      "最终 RGB 以位图嵌入 SVG，线条与文字仍为矢量，可直接用于论文与 PPT。"],
             params=[f"s = {STRENGTH:g}", "提亮 ≤ 0.9", "RGB 位图"]),
        dict(badge="OUT", title="出版级地形图", sub="Publication-ready relief map",
             chip="SVG · PNG · PDF", tile=tile_output, forms=None,
             bullets=[[("可叠加：", dict(weight=700, color=C.navy)),
                       ("地震、断层迹线、GeoJSON / Shapefile、城镇与采样点（shanhai_atlas.geo）。", None)],
                      "等高距 50 m、计曲线 250 m；比例尺按图幅中纬度换算，指北针自动定位。",
                      "同一套设色与晕渲参数可批量应用于任意区域，系列图风格统一。"],
             params=["SVG 文字转曲", "PNG 300 dpi", "等高线 / 比例尺 / 指北针"]),
    ]


# ================================================================ 4. 组版
def build(out, formats):
    d = compute()
    cols_spec = columns(d)
    cv = sha.Canvas(16, 9)
    L, R = 0.34, 16 - 0.34
    sha.header(cv, "MODEL  ARCHITECTURE   ·   方法流程图模板",
              "地形晕渲制图：从 DEM 到出版级地形图的算法流程",
              "From a digital elevation model to a publication-ready relief map — gradients · "
              "multidirectional hillshading · hypsometric tinting · shading composite")
    sha.info_box(cv, 12.10, 0.24, R - 12.10, 0.74, "示例数据  SAMPLE DATA",
                "Jacksboro 断层一带 · 3″ DEM 样例",
                f"{d['z'].shape[1]} × {d['z'].shape[0]} 像元 · 图中数值均为程序实际输出")

    FT, CT, CB = 1.20, 1.60, 8.14
    YG = 1.42
    gap_io, gap_c, fpad = 0.30, 0.15, 0.12
    w_in, w_core = 2.02, [2.32, 2.32, 2.32, 2.32]
    fx0 = L + w_in + gap_io
    xs, xc = [], fx0 + fpad
    for wc in w_core:
        xs.append(xc)
        xc += wc + gap_c
    fx1 = xc - gap_c + fpad
    x_out = fx1 + gap_io
    cols = [(L, w_in)] + list(zip(xs, w_core)) + [(x_out, R - x_out)]
    Y_TILE, H_TILE = 0.60, 2.40
    Y_CHIP = Y_TILE + H_TILE + 0.18
    Y_FORM, H_FORM = Y_CHIP + 0.22, 0.80
    Y_BUL = Y_FORM + H_FORM + 0.12

    sha.group_frame(cv, fx0, FT, fx1, CB + fpad, "核心算法", "Core steps · shanhai_atlas.terrain",
                   label_y=YG)
    for (x, w), (cn, en) in [(cols[0], ("数据", "DATA")), (cols[-1], ("成果", "RESULT"))]:
        cv.text(x + 0.02, YG, f"{cn}  {en}", size=7.3, weight=700, color=C.gold,
                container=cv.page)

    tiles = []
    for (x, w), spec in zip(cols, cols_spec):
        card = sha.card(cv, x, CT, w, CB - CT, spec["title"], spec["sub"], badge=spec["badge"])
        t = (x + 0.08, CT + Y_TILE, w - 0.16, H_TILE)
        sha.tile(cv, *t)
        tiles.append((t, card))

    ymid = CT + Y_TILE + H_TILE / 2
    sha.flow_arrow(cv, (L + w_in + 0.03, ymid), (fx0 + fpad - 0.03, ymid), strong=True)
    sha.flow_arrow(cv, (fx1 - fpad + 0.03, ymid), (x_out - 0.03, ymid), strong=True)
    for k in range(3):
        xa = xs[k] + w_core[k]
        sha.flow_arrow(cv, (xa + 0.005, ymid), (xa + gap_c - 0.005, ymid))

    ychip = CT + Y_CHIP
    gaps = [(x + w + x2) / 2 for (x, w), (x2, _) in zip(cols[:-1], cols[1:])]
    sha.data_spine(cv, ychip, cols[0][0] + 0.25, cols[-1][0] + cols[-1][1] - 0.25, gaps)
    for (x, w), spec in zip(cols, cols_spec):
        sha.chip(cv, x + w / 2, ychip, spec["chip"], container=(x, CT, x + w, CB))

    for (t, card), spec in zip(tiles, cols_spec):
        spec["tile"](cv, t, d)
        x, w = card.x, card.w
        cbox = card.box
        if spec["forms"]:
            sha.formula_box(cv, x + 0.08, CT + Y_FORM, w - 0.16, spec["forms"], h=H_FORM,
                           accent=C.gold if spec["badge"] == "IN" else C.navy, container=cbox)
            yb = sha.bullets(cv, x + 0.12, CT + Y_BUL, w - 0.24, spec["bullets"], container=cbox)
        else:
            yb = sha.bullets(cv, x + 0.12, CT + Y_FORM + 0.02, w - 0.24, spec["bullets"],
                            container=cbox)
        top = sha.param_chips(cv, x + 0.12, CB - 0.10, w - 0.24, spec["params"], container=cbox)
        if yb > top - 0.04:
            cv.issues.append(f"column {spec['badge']}: bullets reach {yb:.2f} > chips {top:.2f}")

    sha.footer_notes(cv, CB + fpad + 0.14, [
        ("为什么用“流程 + 真实中间结果”", "每列小图都是程序对同一份 DEM 的实际中间输出，读者能直接看到"
                                  "每一步把数据变成了什么；公式与参数和代码一一对应。"),
        ("如何复用本模板", "复制本脚本，替换数据读取与 columns() 中各列的标题 / 公式 / 要点 / 参数，"
                     "以及 tile_* 小图函数；版式、配色、断行与自检全部沿用。"),
        ("数据与实现", "DEM：matplotlib 自带 3″ 地形样例（美国田纳西 Jacksboro 断层一带）；\n"
                  "实现：shanhai_atlas.terrain（NumPy）· shanhai_atlas.canvas · shanhai_atlas.components"),
    ])
    bad = cv.audit()
    files = cv.save(Path(out) / "ex01_方法流程图_地形晕渲", formats=formats, check=False)
    cv.close()
    return files, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE.parent / "output"))
    ap.add_argument("--formats", default="svg,png")
    ap.add_argument("--fonts", action="append", default=[])
    a = ap.parse_args()
    sha.setup(a.fonts, fetch=True)
    files, bad = build(a.out, [f for f in a.formats.split(",") if f])
    for f in files:
        print("written:", f)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
