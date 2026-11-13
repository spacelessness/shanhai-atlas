"""ML 图件（`shanhai_atlas/mlfigs.py`）的测试。

重点不在"能画出来"，而在 **读数对不对**：AUC / AP / 混淆矩阵命中数 / 最优行判定，
这些是要写进图注和论文正文的数字，错了比画错更糟。
"""
from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

import shanhai_atlas as jt  # noqa: E402
from shanhai_atlas import mlfigs  # noqa: E402


# --------------------------------------------------------------------------- #
# 指标
# --------------------------------------------------------------------------- #
def test_roc_perfect_separation():
    y = np.r_[np.zeros(50, bool), np.ones(50, bool)]
    s = np.r_[np.linspace(0, 0.4, 50), np.linspace(0.6, 1.0, 50)]
    fpr, tpr, auc = mlfigs.roc_from_scores(y, s)
    assert auc == pytest.approx(1.0)
    assert fpr[0] == 0.0 and tpr[0] == 0.0 and fpr[-1] == 1.0 and tpr[-1] == 1.0


def test_roc_random_is_near_half():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 4000)
    s = rng.random(4000)                       # 与标签无关
    _, _, auc = mlfigs.roc_from_scores(y, s)
    assert 0.45 < auc < 0.55


def test_roc_rejects_single_class():
    with pytest.raises(ValueError):
        mlfigs.roc_from_scores([1, 1, 1], [0.1, 0.2, 0.3])
    with pytest.raises(ValueError):
        mlfigs.roc_from_scores([1, 0], [0.1])   # 长度不一致


def test_pr_perfect_is_one():
    y = np.r_[np.zeros(30, bool), np.ones(30, bool)]
    s = np.r_[np.linspace(0, 0.4, 30), np.linspace(0.6, 1.0, 30)]
    rec, prec, ap = mlfigs.pr_from_scores(y, s)
    assert ap == pytest.approx(1.0, abs=1e-9)


def test_pr_baseline_case():
    """全随机时 AP ≈ 正类比例（PR 的"随机基线"就是 prevalence）。"""
    rng = np.random.default_rng(1)
    y = (rng.random(6000) < 0.3).astype(int)
    s = rng.random(6000)
    _, _, ap = mlfigs.pr_from_scores(y, s)
    assert abs(ap - 0.3) < 0.03


# --------------------------------------------------------------------------- #
# 训练曲线
# --------------------------------------------------------------------------- #
def test_training_curves_best_epoch():
    loss = np.r_[np.linspace(2, 0.5, 10), np.linspace(0.5, 1.2, 10)]   # 第 10 轮最优
    res = mlfigs.training_curves(_ax(), {"loss": loss, "val_loss": loss[::-1]}, "loss")
    assert res["info"]["loss"]["best_epoch"] == 10
    assert res["info"]["loss"]["best"] == pytest.approx(0.5)
    assert len(res["lines"]) == 2


def test_training_curves_smooth_does_not_change_readings():
    loss = np.array([3.0, 1.0, 2.0, 0.5, 1.5])
    res = mlfigs.training_curves(_ax(), {"loss": loss}, "loss", smooth=3)
    assert res["info"]["loss"]["best"] == pytest.approx(0.5)   # 读数用原始值


def test_training_curves_accepts_plain_sequence():
    res = mlfigs.training_curves(_ax(), [1.0, 0.9, 0.8], "loss")
    assert set(res["lines"]) == {"loss"}


# --------------------------------------------------------------------------- #
# 混淆矩阵
# --------------------------------------------------------------------------- #
def test_confusion_matrix_readings():
    cm = np.array([[86, 4, 2], [7, 61, 5], [3, 6, 41]])
    res = mlfigs.confusion_matrix(_ax(), cm, ["猫", "狗", "鸟"])
    assert res["n"] == cm.sum()
    assert res["errors"] == int(cm.sum() - np.trace(cm))
    assert res["acc"] == pytest.approx(np.trace(cm) / cm.sum())


def test_confusion_matrix_normalize():
    cm = np.array([[8, 2], [2, 8]])
    ax = _ax()
    res = mlfigs.confusion_matrix(ax, cm, ["a", "b"], normalize=True)
    assert res["normalized"]
    assert res["acc"] == pytest.approx(0.8)


def test_confusion_matrix_rejects_non_square():
    with pytest.raises(ValueError):
        mlfigs.confusion_matrix(_ax(), np.zeros((2, 3)))
    with pytest.raises(ValueError):
        mlfigs.confusion_matrix(_ax(), np.zeros((2, 2)), ["只有一个"])


# --------------------------------------------------------------------------- #
# 消融表
# --------------------------------------------------------------------------- #
def test_ablation_table_picks_best_row():
    rows = [{"模型": "A", "mAP": 0.71, "FPS": 48},
            {"模型": "B", "mAP": 0.79, "FPS": 45},
            {"模型": "C", "mAP": 0.75, "FPS": 41}]
    cv = jt.Canvas(7.0, 3.0)
    try:
        res = mlfigs.ablation_table(cv, 0.5, 0.8, 4.0, rows, columns=list(rows[0]),
                                    highlight_col="mAP")
        assert res["best_row"] == 1
        assert len(res["rows_y"]) == 3
    finally:
        cv.close()


def test_ablation_table_min_mode_and_errors():
    rows = [{"模型": "A", "loss": 0.4}, {"模型": "B", "loss": 0.2}]
    cv = jt.Canvas(6.0, 2.5)
    try:
        res = mlfigs.ablation_table(cv, 0.5, 0.6, 3.0, rows, columns=list(rows[0]),
                                    highlight="min", highlight_col="loss")
        assert res["best_row"] == 1
        with pytest.raises(ValueError):
            mlfigs.ablation_table(cv, 0.5, 0.6, 3.0, rows, columns=["只有一列"])
    finally:
        cv.close()


# --------------------------------------------------------------------------- #
# 注意力热图 / 结构图
# --------------------------------------------------------------------------- #
def test_attention_topk_is_argmax():
    w = np.atleast_2d([0.1, 0.7, 0.05, 0.15])   # 1×4，避免写成双层方括号
    res = mlfigs.attention_map(_ax(), w, tokens=["a", "b", "c", "d"], topk=2)
    assert res["top"][0] == [1, 3]
    assert res["shape"] == (1, 4)


def test_attention_accepts_1d_and_rejects_3d():
    res = mlfigs.attention_map(_ax(), np.array([0.2, 0.8]), tokens=["x", "y"])
    assert res["shape"] == (1, 2)
    with pytest.raises(ValueError):
        mlfigs.attention_map(_ax(), np.zeros((2, 2, 2)))


def test_arch_diagram_returns_boxes():
    cv = jt.Canvas(6.0, 3.0)
    try:
        pos = mlfigs.arch_diagram(cv, [[{"label": "输入"}],
                                       [{"label": "Encoder"}, {"label": "Decoder"}],
                                       [{"label": "输出"}]], x=0.8, y=0.4)
        assert set(pos) == {"输入", "Encoder", "Decoder", "输出"}
        for (x, y, w, h) in pos.values():
            assert w > 0 and h > 0 and x >= 0 and y >= 0
    finally:
        cv.close()


# --------------------------------------------------------------------------- #
# 整图集成：ML 图也必须过"文字可编辑 + 无豆腐块 + 0 越界"
# --------------------------------------------------------------------------- #
def test_ml_panel_exports_as_editable_vector(tmp_path):
    from shanhai_atlas import exporter

    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 200)
    s = np.clip(y * 0.6 + rng.normal(0, 0.35, 200), 0, 1)

    cv = jt.Canvas(7.48, 3.6)
    try:
        jt.header(cv, "ML", "模型评估", "roc · confusion", x0=0.3, y=0.1,
                  sizes=dict(title=11, kicker=6, subtitle=7))
        mlfigs.roc_curves(cv.inset(0.6, 1.1, 1.9, 1.5), {"ResNet": (y, s)}, panel="a")
        mlfigs.confusion_matrix(cv.inset(2.9, 1.1, 1.5, 1.5),
                                np.array([[8, 2], [3, 7]]), ["正", "负"], panel="b")
        mlfigs.training_curves(cv.inset(4.85, 1.12, 2.0, 1.42),
                               {"loss": np.linspace(2, 0.3, 20)}, panel="c")

        assert cv.audit(full=True, verbose=False) == 0, cv.report
        cv.save(tmp_path / "ml", formats=("svg", "pdf"), check=False)

        svg = exporter.svg_report(tmp_path / "ml.svg")
        assert svg["text_elements"] > 10 and svg["font_face"] >= 1
        pdf = exporter.pdf_report(tmp_path / "ml.pdf")
        assert pdf["type3"] == 0 and pdf["last_resort"] == []
    finally:
        cv.close()


# --------------------------------------------------------------------------- #
def _ax():
    import matplotlib.pyplot as plt
    ax = plt.figure(figsize=(2.0, 1.6)).add_subplot(111)
    return ax
