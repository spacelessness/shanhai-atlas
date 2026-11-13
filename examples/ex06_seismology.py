# -*- coding: utf-8 -*-
"""示例 06 · 地震学综合图：震中分布 + 震源剖面 + 震级–频度。

目录来自 _synthetic.py 的合成示意数据，不是任何机构发布的地震编目，
统计结果（Mc / b 值）仅演示计算流程，不作科学解释。

    python examples/ex06_seismology.py [--out output] [--formats svg,png,pdf]
    python examples/ex06_seismology.py --catalog your_authorized_catalog.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import shanhai_atlas as sha                              # noqa: E402
from shanhai_atlas.geo import gshhs_available           # noqa: E402
from shanhai_atlas.theme import C                       # noqa: E402
from _synthetic import SOURCE, catalog as synth_catalog, write_csv  # noqa: E402


def build(cat, out, formats=("svg", "png", "pdf")):
    W, H = 7.48, 5.55
    cv = sha.Canvas(W, H)
    sha.header(cv, "REGIONAL SEISMOLOGY   ·   区域地震学", "地震学综合图（合成目录）",
               "Epicentres · Cross-section · Frequency–magnitude",
               x0=0.36, y=0.15, sizes=dict(title=13.0, kicker=6.0, subtitle=7.2))

    # (a) 区域震中图：深度着色、震级定量分档；区域小范围等距圆柱近似
    extent = (172.15, 174.12, -43.20, -42.00)
    axm = cv.inset(0.43, 1.13, 3.72, 3.05)
    m = sha.geo.GeoMap(axm, extent)
    if gshhs_available("h"):
        m.coast("h", land=C.land, edge=C.coast, lw=0.42, eps_in=0.004)
    m.graticule(0.25, lw=0.35)
    dots = sha.plot_events(axm, cat, color_by="depth_km", size_range=(5, 25),
                           magnitude_range=(1.5, 6.0), levels=6, alpha=0.72, linewidth=0.12)
    m.scale_bar(20, segments=2, loc=(0.03, 0.04), height_in=0.045, size=5.2)
    m.north_arrow(loc=(0.94, 0.86), size_in=0.23, fontsize=7)
    m.ticks(0.5, size=5.4, pad=2.2)
    m.zebra(0.5, width_in=0.032)
    sha.magnitude_legend(axm, (2, 3, 4), magnitude_range=(1.5, 6.0),
                         size_range=(5, 25), levels=6, loc="lower right", fontsize=5.2,
                         title="震级", title_fontsize=5.3, borderaxespad=0.35)
    cax = cv.inset(1.18, 4.66, 2.25, 0.09)
    cb = cv.fig.colorbar(dots, cax=cax, orientation="horizontal")
    cb.set_label("深度 (km)", fontsize=5.6, labelpad=1)
    cb.ax.tick_params(labelsize=5.0, length=1.2, pad=1.0, colors=C.gray)
    sha.panel_label(axm, "a", x=-0.035, y=1.02, size=7.2)
    sha.panel_title(axm, "震中分布", f"N = {len(cat):,}", size=6.1, x=0.02, y=1.02)

    # (b) 沿 A–A′ 的震源剖面
    axp = cv.inset(4.58, 1.30, 2.53, 1.43)
    start, end = (172.24, -42.65), (174.05, -42.65)
    m.ax.plot([start[0], end[0]], [start[1], end[1]], color=C.clay, lw=0.85,
              ls=(0, (3, 2)), zorder=7)
    m.text(start[0], start[1], "A", size=6.2, color=C.clay, ha="right", va="bottom")
    m.text(end[0], end[1], "A′", size=6.2, color=C.clay, ha="left", va="bottom")
    section = sha.plot_cross_section(axp, cat, start, end, half_width_km=12,
                                     depth_limits_km=(0, 40), color_by="depth_km",
                                     size_range=(5, 20), magnitude_range=(1.5, 6.0), levels=6)
    sha.panel_label(axp, "b", x=-0.12, y=1.035, size=7.2)
    sha.panel_title(axp, "震源剖面 A–A′", f"±12 km；N = {section.n_selected}",
                    size=6.1, x=0.0, y=1.035)

    # (c) 震级–频度：Mc = 最大曲率 + 0.2，仅演示统计流程
    axf = cv.inset(4.58, 3.98, 2.53, 1.12)
    sha.plot_magnitude_frequency(axf, cat.magnitude, bin_width=0.1,
                                 magnitude_bin=0.01, annotate=True)
    sha.panel_label(axf, "c", x=-0.12, y=1.035, size=7.2)
    sha.panel_title(axf, "震级–频度", "Mc：最大曲率 + 0.2；Aki (1965)",
                    size=6.1, x=0.0, y=1.035)

    cv.text(0.43, 5.34,
            f"{SOURCE}；海岸线：GSHHG（Wessel & Smith, 1996）；"
            f"剖面 N={section.n_selected}；Mc 仅演示。",
            size=5.3, color=C.gray)
    bad = cv.audit(verbose=False)
    files = cv.save(Path(out) / "ex06_seismology", formats=formats, check=False)
    cv.close()
    return files, bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE.parent / "output"))
    ap.add_argument("--formats", default="svg,png,pdf")
    ap.add_argument("--fonts", action="append", default=[])
    ap.add_argument("--catalog", help="自己的 CSV 目录；留空则用合成示意数据")
    a = ap.parse_args(argv)
    sha.setup(a.fonts, fetch=True)
    if a.catalog:
        cat = sha.read_catalog(a.catalog, source="user-provided catalog")
    else:
        cat = synth_catalog()
    files, bad = build(cat, a.out, tuple(f for f in a.formats.split(",") if f))
    for path in files:
        print("written:", path)
    print(f"events: {len(cat)}; audit issues: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
