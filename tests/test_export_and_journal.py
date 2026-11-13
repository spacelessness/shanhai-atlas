"""导出层 / 期刊规范的新增测试。

与 ``test_shanhai_atlas.py`` 同一套运行方式::

    SHANHAI_FONT_DIR=/path/to/fonts python -m pytest tests -q

覆盖 8 组导出行为 + 期刊体检，全部不依赖 Ghostscript / 网络。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import shanhai_atlas as jt  # noqa: E402
from shanhai_atlas import exporter, journal, textnorm  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def cv():
    c = jt.Canvas(7.0, 3.6)
    jt.header(c, "EXPORT TEST", "导出测试", "Editable vector check",
              x0=0.3, y=0.12, sizes=dict(title=11, kicker=6, subtitle=7))
    ax = c.inset(0.45, 0.95, 3.1, 2.1)
    ax.plot([0, 1, 2, 3], [1, 3, 2, 4], lw=1.2)
    ax.set_xlabel("时间 $t$ (s)", fontsize=6.5)
    ax.set_ylabel("响应", fontsize=6.5)
    ax.set_title(r"$R^2 = 0.93,\ p < 0.05$", fontsize=7)
    c.text(0.45, 3.2, "量级 $10^{-3}$ s，误差 $\\mu \\pm \\sigma$", size=6.4,
           container=(0.2, 3.0, 6.8, 3.4))
    yield c
    c.close()


def _png_ok(p: Path) -> bool:
    return p.exists() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------- #
# ① 文本归一化
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src,expect", [
    ("$R^2$", "R²"),
    ("$\\mu \\pm \\sigma$", "μ ± σ"),
    ("$10^{-3}$ s", "10⁻³ s"),
    ("$\\frac{p}{q}$ = 0.3", "p/q = 0.3"),
    ("$\\mathbf{W}^{\\top}$", "Wᵀ"),
    ("时间 $t$ (s)", "时间 t (s)"),
])
def test_math_to_unicode(src, expect):
    assert textnorm.math_to_unicode(src) == expect


def test_math_to_unicode_rejects_unsupported():
    assert textnorm.math_to_unicode("$\\sqrt{x}$") is None


def test_braces_are_unwrapped_pairwise():
    """``strip('{}')`` 会把 ``10^{-3}`` 的右括号吃掉，必须成对脱壳。

    这里锁的是**不破坏**：没被整体包住的括号原样保留，整体包住的一层才脱。
    """
    assert textnorm._unwrap("10^{-3}") == "10^{-3}"     # 内部括号不能动
    assert textnorm._unwrap("{-3}") == "-3"             # 整段包住才脱壳
    assert textnorm.math_to_unicode("$10^{-3}$ s") == "10⁻³ s"


def test_normalize_figure_leaves_no_mathtext(cv):
    rep = textnorm.normalize_figure(cv.fig)
    leftover = [t.get_text() for t in cv.fig.findobj(matplotlib.text.Text)
                if "$" in t.get_text()]
    assert leftover == [], f"仍有未转换的公式：{leftover}"
    assert rep["converted"] >= 1


# --------------------------------------------------------------------------- #
# ② 默认导出 = PDF + SVG + PNG
# --------------------------------------------------------------------------- #
def test_default_save_emits_three_formats(cv, tmp_path):
    out = cv.save(tmp_path / "fig", check=False)
    names = sorted(Path(p).suffix for p in out)
    assert names == [".pdf", ".png", ".svg"]
    assert _png_ok(tmp_path / "fig.png")
    assert (tmp_path / "fig.pdf").read_bytes()[:5] == b"%PDF-"


# --------------------------------------------------------------------------- #
# ③ SVG 文字是真文字 + 字体内嵌
ked = None


def test_svg_text_is_editable_and_fonts_embedded(cv, tmp_path):
    cv.save(tmp_path / "e", formats=("svg",), text_mode="editable", check=False)
    rep = exporter.svg_report(tmp_path / "e.svg")
    assert rep["text_elements"] > 0, "SVG 里没有 <text>，文字被转曲了"
    assert rep["tspans"] == 0, "整句被拆成 tspan → Illustrator 里编辑体验退化"
    assert rep["font_face"] >= 1 and rep["embedded_b64"] >= 1
    css = (tmp_path / "e.svg").read_text(encoding="utf-8")
    assert "base64," in css and "@font-face" in css


def test_outline_mode_has_no_text(cv, tmp_path):
    cv.save(tmp_path / "o", formats=("svg",), text_mode="outline", check=False)
    rep = exporter.svg_report(tmp_path / "o.svg")
    assert rep["text_elements"] == 0 and rep["font_face"] == 0


def test_editable_svg_is_smaller_than_outline(cv, tmp_path):
    cv.save(tmp_path / "e", formats=("svg",), text_mode="editable", check=False)
    cv.save(tmp_path / "o", formats=("svg",), text_mode="outline", check=False)
    assert (tmp_path / "e.svg").stat().st_size < (tmp_path / "o.svg").stat().st_size


def test_both_mode_writes_two_svgs(cv, tmp_path):
    cv.save(tmp_path / "b", formats=("svg",), text_mode="both", check=False)
    assert (tmp_path / "b.svg").exists() and (tmp_path / "b.outline.svg").exists()
    assert exporter.svg_report(tmp_path / "b.svg")["text_elements"] > 0
    assert exporter.svg_report(tmp_path / "b.outline.svg")["text_elements"] == 0


# --------------------------------------------------------------------------- #
# ④ PDF：文字层 + TrueType 字体嵌入，没有 Type3 / LastResort
# --------------------------------------------------------------------------- #
def test_pdf_keeps_text_layer(cv, tmp_path):
    cv.save(tmp_path / "p", formats=("pdf",), check=False)
    rep = exporter.pdf_report(tmp_path / "p.pdf")
    assert rep["type3"] == 0, "Type3 字体 = 文字被当图形，Illustrator 里改不了"
    assert rep["fontfile2"] >= 1, "没有 TrueType 字体嵌入"
    assert rep["last_resort"] == [], f"有豆腐块字体：{rep['last_resort']}"


# --------------------------------------------------------------------------- #
# ⑤ strict_text 守门
# --------------------------------------------------------------------------- #
def test_strict_text_catches_outline(cv, tmp_path):
    cv.save(tmp_path / "ok", formats=("svg",), text_mode="editable",
            strict_text=True, check=False)          # 不应抛错
    with pytest.raises(RuntimeError, match="没有 <text>"):
        cv.save(tmp_path / "bad", formats=("svg",), text_mode="outline",
                strict_text=True, check=False)


def test_strict_text_catches_rasterized_pdf(cv, tmp_path):
    """pdf-outline 若偷偷成功，strict_text 必须能发现。"""
    with pytest.raises(RuntimeError):
        cv.save(tmp_path / "x", formats=("pdf-outline",), text_mode="editable",
                strict_text=True, check=False)


# --------------------------------------------------------------------------- #
# pdf-outline 遇 Ghostscript 缺失必须明确失败，也不留半成品。
# 原 skipif 用 shutil.which("gs") 探测，但工具自己的 ghostscript() 认
# gswin64c/gswin32c + 常见安装位（如 C:\gmt6\bin），本机有 gs 时测试会
# 假失败——改为 monkeypatch 模拟"没装"，与本机环境无关、两条路径都验。
# --------------------------------------------------------------------------- #
def test_pdf_outline_requires_ghostscript(cv, tmp_path, monkeypatch):
    monkeypatch.setattr("shanhai_atlas.canvas.ghostscript", lambda: None)
    cv.save(tmp_path / "ok", formats=("pdf",), check=False)
    with pytest.raises(RuntimeError, match="Ghostscript"):
        cv.save(tmp_path / "no", formats=("pdf-outline",), check=False)
    assert not list(tmp_path.glob("*.outline.pdf"))


# --------------------------------------------------------------------------- #
# ⑦ 内嵌字体后仍逐字节可复现
# --------------------------------------------------------------------------- #
def test_svg_is_byte_reproducible_with_embedded_fonts(cv, tmp_path):
    cv.save(tmp_path / "a", formats=("svg",), check=False)
    cv.save(tmp_path / "b", formats=("svg",), check=False)
    assert (tmp_path / "a.svg").read_bytes() == (tmp_path / "b.svg").read_bytes()


# --------------------------------------------------------------------------- #
# ⑧ 缺字修复：追加回退族，而不是整段换族
# --------------------------------------------------------------------------- #
def test_missing_glyph_detected_and_repaired(cv):
    from shanhai_atlas import fonts as jfonts
    fam = jfonts.FONT.cjk
    t = cv.fig.text(0.5, 0.5, "PROBE · 导出层")
    if not textnorm.missing_glyphs("PROBE · 导出层", [fam]):
        pytest.skip(f"{fam} 自身含 ·，无法构造缺字场景")
    fixed = textnorm.repair_missing_glyphs(cv.fig, cjk_family=fam)
    assert fixed, "没有检测到缺字"
    assert "DejaVu Sans" in [str(f) for f in t.get_fontfamily()]
    assert t.get_text() == "PROBE · 导出层"   # 文本内容不能被改动


def test_missing_glyphs_reports_per_family(cv):
    from shanhai_atlas import fonts as jfonts
    rep = textnorm.missing_glyphs("中文 ABC ²", [jfonts.FONT.cjk])
    assert isinstance(rep, dict)


# --------------------------------------------------------------------------- #
# ⑨ audit(full=True) 覆盖所有 Text
# --------------------------------------------------------------------------- #
def test_audit_full_covers_all_texts(cv):
    cv.audit(full=True)
    assert cv.report["texts"] > 0
    assert cv.report["mode"] == "full"


# --------------------------------------------------------------------------- #
# ⑩ 期刊规范
# --------------------------------------------------------------------------- #
def test_presets_cover_major_publishers():
    assert len(journal.PRESETS) >= 6
    for p in journal.PRESETS.values():
        assert p.source, f"{p.key} 缺出处"
        assert 0 < p.min_font_pt < p.max_font_pt
        assert p.single_mm < p.double_mm


def test_preset_inches():
    p = journal.journal_preset("nature")
    assert p.single_in == pytest.approx(89 / 25.4, abs=1e-6)
    with pytest.raises(KeyError):
        journal.journal_preset("no-such-journal")


def test_check_journal_flags_width_and_font(cv):
    r = journal.check_journal(cv, "science")          # 7.0 in = 177.8 mm
    checks = {e["check"] for e in r["errors"]}
    assert "width" in checks
    assert all(e["fix"] for e in r["errors"]), "每条问题都要给改法"
    assert r["preset"]["verified"] is False, "没有联网核对就必须标 verified=False"


def test_check_journal_passes_on_matching_width(cv):
    r = journal.check_journal(cv, "acs", raster_dpi=300)   # 177.8 mm = ACS 双栏
    assert r["ok"], r["errors"]
    assert r["metrics"]["width_mm"] == pytest.approx(177.8, abs=0.2)


def test_check_journal_strict_raises(cv):
    with pytest.raises(RuntimeError):
        journal.check_journal(cv, "plos", raster_dpi=72, strict=True)


def test_check_export_detects_outline_svg(cv, tmp_path):
    cv.save(tmp_path / "o", formats=("svg",), text_mode="outline", check=False)
    r = journal.check_export(tmp_path / "o.svg", "nature")
    assert not r["ok"]
    assert any(i["check"] == "editable" for i in r["issues"])


def test_check_export_accepts_editable_svg(cv, tmp_path):
    cv.save(tmp_path / "e", formats=("svg",), text_mode="editable", check=False)
    r = journal.check_export(tmp_path / "e.svg", "nature")
    assert not any(i["check"] in ("editable", "font_embedded") for i in r["issues"])


# --------------------------------------------------------------------------- #
# ⑪ 字体预设
# --------------------------------------------------------------------------- #
def test_font_presets_are_complete():
    from shanhai_atlas import fonts as jfonts
    assert len(jfonts.FONT_PRESETS) >= 4
    for key, pr in jfonts.FONT_PRESETS.items():
        assert pr["cjk"] and pr["latin"], f"{key} 必须同时给中文族与拉丁族"
        assert pr["license"], f"{key} 必须写明授权来源"
        assert all(ord(c) < 128 or c for c in pr["name"])


def test_font_preset_lookup_and_errors():
    from shanhai_atlas import fonts as jfonts
    assert jfonts.font_preset("noto")["key"] == "noto"
    with pytest.raises(KeyError):
        jfonts.font_preset("no-such-preset")


def test_check_fonts_reports_contour_flavor():
    from shanhai_atlas import fonts as jfonts
    rep = jfonts.check_fonts()
    assert rep["fonts"]
    for row in rep["fonts"]:
        assert set(row) >= {"family", "installed", "flavor", "glyf"}
    assert isinstance(rep["ok"], bool)


def test_setup_accepts_preset():
    from shanhai_atlas import fonts as jfonts
    f = jfonts.setup(quiet=True, preset="noto")
    assert f.cjk == jfonts.FONT.cjk


def test_delta_e_sanity():
    assert journal.delta_e("#000000", "#ffffff") > 90
    assert journal.delta_e("#B08D57", "#B08D57") == 0
    rep = journal.colorblind_report(["#000000", "#ffffff"])
    assert rep["ok"] and rep["min_delta_e"] > 90
