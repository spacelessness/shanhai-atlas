#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""示例 03 · 地形图 + 剖面（期刊双栏尺寸 190 mm）：真实 DEM 晕渲、等高线、剖面线与统计。

(a) 分层设色 + 多方向山体阴影 + 等高线（计曲线标注）+ 剖面线 A–A′ + 经纬网 / 斑马框 / 比例尺 / 指北针
(b) A–A′ 地形剖面（填充 + 垂向放大说明）
(c) 坡度分布直方图（中位数、> 25° 占比）

数据：默认用 matplotlib 自带的 3″ 真实地形样例（美国田纳西 Jacksboro 断层一带）；
换成自己的 DEM：--dem path/to/dem.tif（GeoTIFF / ASC / NetCDF / NPZ），或 --terrarium
lon0,lon1,lat0,lat1 在线下载任意区域（需联网），并用 --profile 指定剖面端点。

    python examples/ex03_terrain_map.py [--dem FILE | --terrarium W,E,S,N] [--profile lon0,lat0,lon1,lat1]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import shanhai_atlas as sha                                      # noqa: E402
from shanhai_atlas import terrain                               # noqa: E402
from shanhai_atlas.geo import GeoMap                            # noqa: E402
from shanhai_atlas.theme import C, CMAPS, TYPE                  # noqa: E402

P = TYPE.paper


def build(dem, prof, out, formats, stem):
    W, H = sha.SIZES.paper_double[0], 4.45
    cv = sha.Canvas(W, H)
    lo0, lo1, la0, la1 = dem.extent
    phi0 = (la0 + la1) / 2
    mh = 3.62
    mw = mh * (lo1 - lo0) / ((la1 - la0) / math.cos(math.radians(phi0)))
    MX, MY = 0.52, 0.22
    ax = cv.inset(MX, MY, mw, mh)
    m = GeoMap(ax, dem.extent, sea=C.white)
    vmin, vmax = np.percentile(dem.z, 1), np.percentile(dem.z, 99.5)
    terrain.draw(ax, dem, sea=False, strength=0.62, vmin=vmin, vmax=vmax)
    terrain.contours(ax, dem, interval=50, index_every=5, lw=0.16, index_lw=0.38, alpha=0.38,
                     labels=True, label_size=4.2)
    # 剖面线
    dist, zp, plon, plat = prof
    ax.plot(plon, plat, color="white", lw=2.4, zorder=9, solid_capstyle="round")
    ax.plot(plon, plat, color=C.clay, lw=1.1, zorder=9.5, solid_capstyle="round")
    for (x, y), s, ha in (((plon[0], plat[0]), "A", "right"), ((plon[-1], plat[-1]), "A′", "left")):
        ax.plot([x], [y], marker="o", ms=3.2, color=C.clay, mec="white", mew=0.6, zorder=10)
        dx, _ = m.in2deg(0.06)
        m.text(x + (-dx if ha == "right" else dx), y, s, size=7.0, color=C.clay, weight=700,
               ha=ha, va="center", z=10)
    step = 0.1
    m.scale_bar(5, segments=2, loc=(0.05, 0.05), height_in=0.04, size=5.6)
    m.north_arrow(loc=(0.92, 0.86), size_in=0.24, fontsize=7)
    m.ticks(step, size=P.tick, pad=4)
    m.zebra(step, width_in=0.035)
    sha.panel_label(ax, "a", x=-0.06, y=1.005, size=8.5)
    # 色条（地图下方）
    cbx = MX + 0.02
    sha.colorbar(cv, cbx, MY + mh + 0.36, 1.25, 0.055, CMAPS.terrain, float(vmin), float(vmax),
                ticks=[float(vmin), float((vmin + vmax) / 2), float(vmax)], vertical=False,
                size=5.2, fmt="{:.0f}")
    cv.text(cbx + 1.36, MY + mh + 0.43, "高程（m）· 等高距 50 m，计曲线 250 m", size=5.6, color=C.gray,
            container=cv.page)

    # (b) 剖面
    bx = MX + mw + 0.62
    bw = W - bx - 0.18
    ab = cv.inset(bx, 0.30, bw, 1.55)
    ab.fill_between(dist, zp, zp.min() - 40, color=C.gold_pale, lw=0, zorder=1)
    ab.plot(dist, zp, color=C.navy, lw=0.9, zorder=3)
    ab.set_xlim(0, dist[-1])
    ab.set_ylim(zp.min() - 40, zp.max() + 60)
    ab.set_xlabel("距 A 点距离（km）", labelpad=1.5)
    ab.set_ylabel("高程（m）", labelpad=1.5)
    sha.style_axes(ab, grid="y", tick_size=P.tick, label_size=P.label)
    ve = (dist[-1] / bw) / ((ab.get_ylim()[1] - ab.get_ylim()[0]) / 1000 / 1.55)
    sha.note(ab, 0.98, 0.94, f"垂向放大 ≈ {ve:.0f}×", size=5.4, ha="right", va="top",
            transform=ab.transAxes)
    i = int(np.argmax(zp))
    ab.scatter([dist[i]], [zp[i]], s=10, color=C.clay, zorder=4, lw=0)
    sha.note(ab, dist[i], zp[i] + 18, f"{zp[i]:.0f} m", size=5.4, color=C.clay, ha="center",
            va="bottom")
    ab.text(0, 1.02, "A", transform=ab.transAxes, fontsize=6.5, weight=700, color=C.clay,
            ha="left", va="bottom")
    ab.text(1, 1.02, "A′", transform=ab.transAxes, fontsize=6.5, weight=700, color=C.clay,
            ha="right", va="bottom")
    sha.panel_label(ab, "b", x=-0.16, y=1.02, size=8.5)

    # (c) 坡度直方图
    ac = cv.inset(bx, 2.40, bw, 1.45)
    sl = terrain.slope_deg(dem).ravel()
    bins = np.arange(0, 46, 2.5)
    cnt, _ = np.histogram(sl, bins=bins)
    frac = cnt / cnt.sum() * 100
    ac.bar(bins[:-1] + 1.25, frac, width=2.1, color=[C.blue_soft if b < 25 else C.clay
                                                     for b in bins[:-1]], lw=0, zorder=2)
    med = float(np.median(sl))
    top = frac.max() * 1.22
    ac.plot([med, med], [0, frac.max() * 1.08], color=C.gold, lw=0.8, ls=(0, (2.2, 1.6)), zorder=3)
    sha.note(ac, med, frac.max() * 1.10, f"中位数 {med:.1f}°", size=5.4, color=C.gold, ha="center",
            va="bottom")
    steep = float((sl > 25).mean() * 100)
    sha.note(ac, 44, frac.max() * 0.55, f"> 25°：{steep:.1f}%", size=5.4, color=C.clay, ha="right")
    ac.set_ylim(0, top)
    ac.set_xlim(0, 45)
    ac.set_xlabel("坡度（°）", labelpad=1.5)
    ac.set_ylabel("像元占比（%）", labelpad=1.5)
    sha.style_axes(ac, grid="y", tick_size=P.tick, label_size=P.label)
    sha.panel_label(ac, "c", x=-0.16, y=1.02, size=8.5)

    cv.text(bx, H - 0.10, f"DEM：{dem.source}", size=5.2, color=C.gray_lite, container=cv.page)
    bad = cv.audit()
    files = cv.save(Path(out) / stem, formats=formats, check=False)
    cv.close()
    return files, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE.parent / "output"))
    ap.add_argument("--formats", default="svg,png")
    ap.add_argument("--fonts", action="append", default=[])
    ap.add_argument("--dem", help="本地 DEM 文件")
    ap.add_argument("--terrarium", help="在线下载范围 W,E,S,N（度）")
    ap.add_argument("--profile", help="剖面端点 lon0,lat0,lon1,lat1")
    a = ap.parse_args()
    sha.setup(a.fonts, fetch=True)
    if a.terrarium:
        dem = terrain.fetch_terrarium(tuple(float(v) for v in a.terrarium.split(",")))
    elif a.dem:
        dem = terrain.load_dem(a.dem)
    else:
        dem = terrain.sample_dem("jacksboro")
    dem = dem.coarsen(900)
    lo0, lo1, la0, la1 = dem.extent
    if a.profile:
        x0, y0, x1, y1 = (float(v) for v in a.profile.split(","))
    else:                                     # 默认：自西向东横穿高原—陡崖—谷地
        x0, y0 = lo0 + 0.06 * (lo1 - lo0), la0 + 0.42 * (la1 - la0)
        x1, y1 = lo0 + 0.94 * (lo1 - lo0), la0 + 0.66 * (la1 - la0)
    prof = terrain.profile(dem, (x0, y0), (x1, y1))
    files, bad = build(dem, prof, a.out, [f for f in a.formats.split(",") if f],
                       "ex03_地形图_剖面" if not (a.dem or a.terrarium) else "ex03_地形图_自定义")
    for f in files:
        print("written:", f)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
