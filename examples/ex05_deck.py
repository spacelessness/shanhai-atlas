# -*- coding: utf-8 -*-
"""示例 05 · 同风格 PPT：先出一张矢量图，再生成带讲稿备注的 .pptx。

需要可选依赖 python-pptx（pip install shanhai-atlas[ppt]）；未安装时优雅跳过。

    python examples/ex05_deck.py [--out output]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import shanhai_atlas as sha                       # noqa: E402
from shanhai_atlas.theme import C, SERIES        # noqa: E402


def build(out):
    try:
        from shanhai_atlas.ppt import Deck
    except ImportError:
        print("skip: 需要 python-pptx —— pip install shanhai-atlas[ppt]")
        return []

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / "ex05_deck_figure"

    cv = sha.Canvas(13.333, 7.5)
    sha.header(cv, "DEMO  ·  REPRODUCIBLE FIGURE", "同风格图件与汇报",
               "One design system, from paper figure to slide deck")
    ax = cv.inset(0.85, 1.85, 11.6, 4.55)
    x = np.linspace(0, 10, 240)
    for i, (a, b) in enumerate(((0.55, 0.06), (0.38, 0.14), (0.22, 0.22))):
        y = np.exp(-b * x) * np.sin(2.0 * x + a * 2) + 0.5
        ax.plot(x, y, color=SERIES[i], lw=1.8, label=f"模型 {i + 1}")
    sha.style_axes(ax, grid="both")
    ax.set_xlabel("归一化距离", fontsize=8)
    ax.set_ylabel("响应", fontsize=8)
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    cv.audit(verbose=False)
    cv.save(stem, formats=("svg", "png"), check=False)
    cv.close()

    deck = Deck(footer="Shanhai Atlas · 示例", org="合成数据演示")
    deck.cover("山海图 · 科研绘图", "从论文图件到同风格汇报",
               meta="示例 · 全部数据为合成示意",
               notes="这一页说明工具定位：一套设计令牌贯穿图件与 PPT。")
    deck.full_figure(str(stem.with_suffix(".svg")), vector=True,
                     notes="SVG 矢量嵌入，同时附 PNG 回退图，旧版 Office / WPS 也能显示。")
    deck.cards("四类核心能力", [
        ("地理 / 地质", ["GSHHG 海岸线、断层迹线、台站", "比例尺、指北针、位置图"]),
        ("地形", ["DEM 晕渲、等高线、剖面", "离线样例或用户自有 DEM"]),
        ("地震", ["震中、剖面、Mc / b 值", "三维震源机制球"]),
        ("科研绘图", ["可编辑 SVG / PDF / PNG", "版面自检 + 期刊体检"]),
    ], notes="四类能力共用同一套配色、字体与版面自检。")
    deck.closing("谢谢", sub="Shanhai Atlas · 0.2.0",
                 notes="示例结束。真实研究请换成自己已获授权的数据。")

    path = out / "ex05_deck.pptx"
    deck.save(str(path))
    return [str(path)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE.parent / "output"))
    ap.add_argument("--fonts", action="append", default=[])
    a = ap.parse_args(argv)
    sha.setup(a.fonts, fetch=True)
    for f in build(a.out):
        print("written:", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
