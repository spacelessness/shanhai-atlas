# -*- coding: utf-8 -*-
"""示例 02 · 地理 / 地质底图：海岸线 + 断层迹线 + 震中 + 台站 + 比例尺 + 位置图。

数据全部为合成示意数据（见 _synthetic.py），不含行政边界、国界或真实台站坐标。
海岸线来自 GSHHG（pip install shanhai-atlas[geo]）；未安装时自动跳过底图，图仍可出。

    python examples/ex02_geo_map.py [--out output] [--formats svg,png,pdf]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import shanhai_atlas as sha                                        # noqa: E402
from shanhai_atlas.geo import GeoMap, gshhs_available, locator     # noqa: E402
from shanhai_atlas.theme import C, SERIES                          # noqa: E402
from _synthetic import EXTENT, SOURCE, catalog, fault_traces, stations  # noqa: E402


def build(out, formats):
    cv = sha.Canvas(13.333, 7.5)
    sha.header(cv, "GEOLOGY  ·  REGIONAL BASEMAP", "区域地理与构造底图",
               "Coastline · fault traces · epicentres · stations (synthetic)")

    lo0, lo1, la0, la1 = EXTENT
    phi0 = (la0 + la1) / 2
    h = 5.0
    w = h * (lo1 - lo0) / ((la1 - la0) / np.cos(np.radians(phi0)))
    ax = cv.inset(0.55, 1.42, w, h, z=3)
    m = GeoMap(ax, EXTENT)

    has_coast = gshhs_available("h")
    if has_coast:
        m.coast("h", land=C.land, edge=C.coast, lw=0.45, eps_in=0.004)
    m.graticule(0.25, lw=0.35)
    m.ticks(0.5, size=6.0)
    m.zebra(0.5, width_in=0.035)

    for i, (fx, fy) in enumerate(fault_traces()):
        ax.plot(fx, fy, color=SERIES[i % len(SERIES)], lw=1.5,
                ls=(0, (5, 2)), zorder=3, label=f"示意断层 F{i + 1}")

    cat = catalog()
    pts = sha.plot_events(ax, cat, color_by="depth_km", size_range=(6, 46), alpha=0.86)
    cb = cv.fig.colorbar(pts, ax=ax, fraction=0.032, pad=0.02)
    cb.set_label("深度 (km)", fontsize=6.4, color=C.gray)
    cb.ax.tick_params(labelsize=5.6, colors=C.gray)

    slo, sla = stations()
    ax.scatter(slo, sla, marker="^", s=30, facecolor="white", edgecolor=C.navy,
               lw=0.9, zorder=7)
    m.scale_bar(25)
    m.north_arrow()

    # 右栏：图例说明
    rx = 0.55 + w + 0.42
    rw = 13.333 - rx - 0.55
    cv.text(rx, 1.55, "图面要素", size=10, weight=700, color=C.navy)
    items = [
        ("●", "震中：深度着色、面积随震级", C.navy),
        ("▽", "台站：示意点位，非真实台站", C.navy),
        ("—", "断层迹线：三条合成折线", SERIES[0]),
        ("~", "海岸线：GSHHG（若已安装）", C.gray),
    ]
    for k, (mark, desc, col) in enumerate(items):
        y = 2.05 + k * 0.55
        cv.text(rx, y, mark, size=9, color=col)
        cv.text(rx + 0.32, y, desc, size=7.4, color=C.ink)

    cv.text(rx, 4.55, "说明", size=9.5, weight=700, color=C.navy)
    cv.para(rx, 4.85, rw,
            "本图为 API 与版式演示：所有点位、断层与震级均为随机生成的合成数据，"
            "不代表任何真实地震活动，也不含行政边界或国界。",
            size=7.0, color=C.ink, leading=1.5)

    if has_coast:
        la = cv.inset(rx, 5.75, rw, 0.95, z=2)
        try:
            locator(la, (168.0, 178.5, -47.5, -38.0), EXTENT, res="i")
        except Exception:
            la.set_axis_off()
        la.set_title("研究区位置（示意）", fontsize=6.2, color=C.gray, pad=1)

    sha.source_line(cv, 0.55, 6.95, 12.2,
                    f"{SOURCE}；海岸线 GSHHG (Wessel & Smith, 1996)；"
                    "图示为合成数据，不用于科学解释。", size=6.2)

    bad = cv.audit(verbose=False)
    files = cv.save(Path(out) / "ex02_geo_map", formats=formats, check=False)
    cv.close()
    return files, bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE.parent / "output"))
    ap.add_argument("--formats", default="svg,png")
    ap.add_argument("--fonts", action="append", default=[])
    a = ap.parse_args(argv)
    sha.setup(a.fonts, fetch=True)
    files, bad = build(a.out, [f for f in a.formats.split(",") if f])
    for f in files:
        print("written:", f)
    print(f"audit issues: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
