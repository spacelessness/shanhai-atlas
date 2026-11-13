# -*- coding: utf-8 -*-
"""适配层测试：**在没装外部包的环境里**跑内置实现（这正是本地最常见的状态）。"""
from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from shanhai_atlas.adapters import (add_scalebar, backends, count_overlaps,  # noqa: E402
                                    significance_brackets, spread_labels, stars)


@pytest.fixture()
def ax():
    a = plt.figure(figsize=(3.0, 2.2)).add_subplot(111)
    yield a
    plt.close(a.figure)


# --------------------------------------------------------------------------- #
# 比例尺
# --------------------------------------------------------------------------- #
def test_scalebar_native_draws_segments(ax):
    ax.set_xlim(0, 10)
    res = add_scalebar(ax, 100, km_per_xunit=20, loc="lower right", segments=2)
    if isinstance(res, dict):                     # 内置实现
        assert len(res["rects"]) == 2
        assert 0.05 <= res["width_axes_frac"] <= 0.85
        assert "km" in res["text"]
    else:                                         # 装了 matplotlib-scalebar
        assert res is not None


def test_scalebar_requires_scale(ax):
    ax.set_xlim(0, 10)
    with pytest.raises(ValueError, match="不能猜"):
        add_scalebar(ax, 100)


def test_scalebar_lat_conversion():
    from shanhai_atlas.adapters.scalebar import km_per_degree
    assert km_per_degree(0) == pytest.approx(111.32, abs=0.01)
    assert km_per_degree(60) == pytest.approx(55.66, abs=0.05)   # cos60 = 0.5


def test_scalebar_fraction_matches_geometry(ax):
    ax.set_xlim(0, 8)                             # 8 个单位，1 单位 = 10 km → 总长 80 km
    res = add_scalebar(ax, 40, km_per_xunit=10, segments=1)
    if isinstance(res, dict):
        assert res["width_axes_frac"] == pytest.approx(40 / 80, rel=0.02)


# --------------------------------------------------------------------------- #
# 标签避让
# --------------------------------------------------------------------------- #
def test_spread_labels_reduces_overlap(ax):
    ys = np.linspace(0.4, 0.6, 6)                 # 六条注释挤在同一条竖直线上
    texts = [ax.text(2.0, y, f"样本 {i} 的说明文字") for i, y in enumerate(ys)]
    before = count_overlaps(texts)
    res = spread_labels(texts, max_iter=60)
    assert before > 0
    assert res["after"] < before or res["backend"] != "native"
    assert res["moved"] > 0


def test_spread_labels_handles_annotations(ax):
    """Annotation 的位置在 `.xy` 上，不在 `.get_position()`——踩过这个坑。"""
    ys = np.linspace(0.4, 0.6, 4)
    texts = [ax.annotate(f"注 {i}", (2.0, y)) for i, y in enumerate(ys)]
    before = count_overlaps(texts)
    res = spread_labels(texts, max_iter=40)
    assert before > 0 and res["after"] <= before


def test_spread_labels_handles_empty(ax):
    assert spread_labels([])["after"] == 0


# --------------------------------------------------------------------------- #
# 显著性括号
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("p,expect", [(0.0001, "***"), (0.005, "**"), (0.03, "*"), (0.4, "ns")])
def test_stars_mapping(p, expect):
    assert stars(p) == expect


def test_stars_passthrough_and_none():
    assert stars("p = 0.07") == "p = 0.07"
    assert stars(None) == ""


def test_significance_brackets_stack(ax):
    ax.set_ylim(0, 10)
    res = significance_brackets(ax, [(1, 2, 0.0005), (1, 3, 0.02)])
    assert len(res["brackets"]) == 2
    assert res["brackets"][0]["label"] == "***"
    assert res["brackets"][1]["y"] > res["brackets"][0]["y"]     # 第二组自动上叠
    assert ax.get_ylim()[1] > 10                                 # 顶部让出空间


def test_brackets_respect_explicit_y(ax):
    ax.set_ylim(0, 10)
    res = significance_brackets(ax, [(1, 2, 0.03, 8.0)], h=0.3)
    assert res["brackets"][0]["y"] == 8.0
    assert res["brackets"][0]["label"] == "*"


# --------------------------------------------------------------------------- #
# 后端探测
# --------------------------------------------------------------------------- #
def test_backends_reports_three_adapters():
    b = backends()
    assert set(b) == {"scalebar", "labels", "signif"}
    for v in b.values():
        assert isinstance(v, str) and v
