# -*- coding: utf-8 -*-
"""示例 04 · 期刊双栏多面板数据图：震级–频度 / 深度分布 / 累积事件 / 深度–震级。

数据为合成示意目录（见 _synthetic.py），统计结果不作任何科学解释。

    python examples/ex04_data_panels.py [--out output] [--formats svg,png,pdf]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import shanhai_atlas as sha                              # noqa: E402
from shanhai_atlas.theme import C, TYPE                  # noqa: E402
from _synthetic import SOURCE, catalog                  # noqa: E402


def build(out, formats):
    cat = catalog()
    mag = cat.magnitude
    dep = cat.depth_km

    W, H = 7.48, 5.51                         # 期刊双栏标准宽度（英寸）
    cv = sha.Canvas(W, H)
    sha.header(cv, "STATISTICAL PANELS  ·  多面板数据图", "目录统计四联图",
               "MFD · depth distribution · cumulative counts · depth–magnitude",
               x0=0.36, y=0.28, sizes=dict(title=11.0, kicker=5.8, subtitle=6.4))

    # (a) 震级–频度：Mc 与 b 值由工具算出，数字全部来自程序输出
    ax1 = cv.inset(0.48, 1.28, 3.20, 1.72)
    mfd = sha.plot_magnitude_frequency(ax1, mag, bin_width=0.2, annotate=True)
    sha.panel_label(ax1, "a")
    ax1.set_title(f"震级–频度  Mc={mfd.mc:.2f}  b={mfd.b_value:.2f}", fontsize=6.4,
                  color=C.navy, loc="left", pad=7)

    # (b) 深度分布
    ax2 = cv.inset(4.10, 1.28, 3.00, 1.72)
    ax2.hist(dep, bins=np.arange(0, 42, 3), color=C.blue, edgecolor="white", linewidth=0.5)
    sha.style_axes(ax2, grid="y")
    ax2.set_xlabel("深度 (km)", fontsize=6.2)
    ax2.set_ylabel("事件数", fontsize=6.2)
    sha.panel_label(ax2, "b")
    ax2.set_title(f"深度分布  中位={np.median(dep):.1f} km", fontsize=6.4,
                  color=C.navy, loc="left", pad=7)

    # (c) 累积事件数（按时间排序）
    ax3 = cv.inset(0.48, 3.55, 3.20, 1.42)
    order = np.argsort(cat.time)
    ax3.plot(np.arange(len(order)) + 1, np.arange(len(order)) + 1, color=C.navy, lw=1.1)
    ax3.plot(np.arange(len(order)) + 1, np.cumsum(np.ones(len(order))), color=C.gold,
             lw=1.0, ls=(0, (3, 2)))
    sha.style_axes(ax3)
    ax3.set_xlabel("按时间排序的事件序号", fontsize=6.2)
    ax3.set_ylabel("累积 N", fontsize=6.2)
    sha.panel_label(ax3, "c")
    ax3.set_title(f"累积事件数  N = {len(cat):,}", fontsize=6.4,
                  color=C.navy, loc="left", pad=7)

    # (d) 深度–震级关系（散点 + 分箱中位）
    ax4 = cv.inset(4.10, 3.55, 3.00, 1.42)
    ax4.scatter(dep, mag, s=8, color=C.gold, alpha=0.65, edgecolors="white", linewidth=0.3)
    edges = np.arange(0, 45, 5)
    centers, meds = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (dep >= lo) & (dep < hi)
        if sel.sum() >= 5:
            centers.append((lo + hi) / 2)
            meds.append(float(np.median(mag[sel])))
    ax4.plot(centers, meds, color=C.clay, lw=1.2, marker="o", ms=2.5)
    sha.style_axes(ax4)
    ax4.set_xlabel("深度 (km)", fontsize=6.2)
    ax4.set_ylabel("震级", fontsize=6.2)
    sha.panel_label(ax4, "d")
    ax4.set_title("深度–震级（分箱中位）", fontsize=6.4,
                  color=C.navy, loc="left", pad=7)

    sha.source_line(cv, 0.48, 5.18, 6.60,
                    f"{SOURCE}；N={len(cat):,}；Mc 用最大曲率 + 0.2（仅演示统计流程）。",
                    size=5.8)

    bad = cv.audit(verbose=False)
    files = cv.save(Path(out) / "ex04_data_panels", formats=formats, check=False)
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
