# -*- coding: utf-8 -*-
"""Shanhai Atlas 基本测试：排版 / 自检 / 地形 / 瓦片 / 几何 / 地图 / PPT / 可复现。

    cd Shanhai_Atlas && python -m pytest -q
"""

from __future__ import annotations

import io
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shanhai_atlas as jt                                # noqa: E402
from shanhai_atlas import geo, terrain                    # noqa: E402

try:
    jt.setup(quiet=True)
    HAVE_CJK = True
except RuntimeError:                               # 无中文字体的 CI：只跑非排版测试
    HAVE_CJK = False

cjk = pytest.mark.skipif(not HAVE_CJK, reason="no CJK font (python -m shanhai_atlas fonts)")


# ---------------------------------------------------------------- 排版
@cjk
def test_para_wraps_within_width_and_audit_passes():
    cv = jt.Canvas(4, 3, dpi=100)
    box = (0.2, 0.2, 2.2, 2.8)
    y, n = cv.para(0.2, 0.3, 2.0, "精定位地震目录沿发震断层“显影”为薄片状点云，" * 3, size=8,
                   container=box)
    assert n >= 3 and y < 2.8
    assert cv.audit(verbose=False) == 0
    cv.close()


@cjk
def test_audit_detects_overflow_and_overlap():
    cv = jt.Canvas(4, 3, dpi=100)
    cv.text(0.2, 0.5, "这一行文字明显比容器更宽更宽更宽更宽", size=10, container=(0.2, 0.3, 1.0, 0.7))
    cv.text(0.2, 1.5, "压字 A", size=10, container=cv.page)
    cv.text(0.25, 1.5, "压字 B", size=10, container=cv.page)
    cv.audit(verbose=False)
    assert cv.report["overflow"] >= 1 and cv.report["overlap"] >= 1
    cv.close()


@cjk
def test_kinsoku_no_line_starts_with_closing_punct():
    cv = jt.Canvas(4, 3, dpi=100)
    text = "甲乙丙丁戊己庚辛，壬癸子丑寅卯辰巳。午未申酉戌亥（天干地支）、" * 4
    for w in np.linspace(0.8, 2.0, 9):
        lines = cv._lines(w, text, 8, "#000", 400, "normal", None)
        for ln in lines[1:]:
            assert ln[0][0][0] not in cv.NO_START
            assert ln[-1][0][-1] not in cv.NO_END or ln is lines[-1]
    cv.close()


@cjk
def test_svg_is_byte_reproducible(tmp_path):
    def make(p):
        cv = jt.Canvas(3, 2, dpi=100)
        jt.header(cv, "KICKER", "标题", "Subtitle", x0=0.1, y=0.25,
                  sizes=dict(title=10, subtitle=6, kicker=5))
        ax = cv.inset(0.3, 0.9, 2.4, 0.9)
        ax.plot([0, 1, 2], [1, 3, 2], color=jt.C.navy)
        cv.save(p, formats=("svg",), check=False)
        cv.close()
        return Path(str(p) + ".svg").read_bytes()
    assert make(tmp_path / "a") == make(tmp_path / "b")


# ---------------------------------------------------------------- 地形
def _plane_dem(tilt_east=0.0, n=60):
    x = np.linspace(0, 1, n)
    z = np.tile(x * tilt_east, (n, 1))
    return terrain.DEM(z, (0.0, 0.01, 0.0, 0.01), geographic=True)


def test_hillshade_flat_equals_sin_altitude():
    hs = terrain.hillshade(_plane_dem(0.0), altitude=45, multidirectional=True)
    assert np.allclose(hs, math.sin(math.radians(45)), atol=1e-9)
    hs1 = terrain.hillshade(_plane_dem(0.0), altitude=30, multidirectional=False)
    assert np.allclose(hs1, 0.5, atol=1e-9)


def test_hillshade_lit_slope_brighter():
    # 向东升高 → 坡面朝西，被西北光照亮；向西升高 → 背光
    lit = terrain.hillshade(_plane_dem(+300.0), azimuth=315, multidirectional=False).mean()
    dark = terrain.hillshade(_plane_dem(-300.0), azimuth=315, multidirectional=False).mean()
    assert lit > math.sin(math.radians(45)) > dark


def test_dem_crop_coarsen_profile():
    dem = terrain.sample_dem("jacksboro")
    assert dem.z.shape == (344, 403)
    c = dem.crop((dem.extent[0], dem.extent[0] + 0.1, dem.extent[2], dem.extent[2] + 0.1))
    assert c.z.shape[0] < 344 and c.z.shape[1] < 403
    k = dem.coarsen(100)
    assert max(k.z.shape) <= 100
    d, z, lon, lat = terrain.profile(dem, (dem.extent[0], dem.extent[2]),
                                     (dem.extent[1], dem.extent[3]), n=50)
    assert d[0] == 0 and d[-1] > 30 and np.isfinite(z).all()


def test_terrarium_mosaic_roundtrip():
    """用合成瓦片（已知高程场）验证 Terrarium 解码、拼接与墨卡托 → 经纬度重采样。"""
    from PIL import Image

    def field(lon, lat):                       # 1000–1500 m（Terrarium 可表示 −32768…32512 m）
        return 1000.0 + 800.0 * (lon - 173.0) + 500.0 * (lat + 42.6)

    def getter(z, x, y):
        n = 2 ** z
        px = (np.arange(256) + 0.5) / 256
        lon = (x + px) / n * 360.0 - 180.0
        yy = (y + px) / n
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * yy))))
        e = field(lon[None, :], lat[:, None]) + 32768.0
        r = np.floor(e / 256)
        g = np.floor(e - r * 256)
        b = np.round((e - r * 256 - g) * 256)
        rgb = np.clip(np.dstack([r, g, b]), 0, 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, "PNG")
        return buf.getvalue()

    ext = (173.0, 173.4, -42.6, -42.3)
    dem = terrain.fetch_terrarium(ext, zoom=10, getter=getter, verbose=False)
    X, Y = dem.grid()
    err = np.abs(dem.z - field(X, Y))
    assert err.max() < 2.0, err.max()


def test_terrarium_credit_lists_region_sources():
    nz = terrain.terrarium_credit((172.4, 173.95, -43.1, -42.15))
    assert any("Land Information New Zealand" in t for t in nz)
    assert any("U.S. Geological Survey" in t for t in nz)
    assert not any("Kartverket" in t for t in nz)


def test_geotiff_roundtrip(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    z = np.arange(20 * 30, dtype=np.float32).reshape(20, 30)
    p = tmp_path / "dem.tif"
    tifffile.imwrite(p, z, extratags=[(33550, "d", 3, (0.01, 0.01, 0.0), False),
                                      (33922, "d", 6, (0, 0, 0, 100.0, 40.0, 0), False)])
    dem = terrain.load_dem(p)
    assert dem.z.shape == (20, 30)
    assert np.allclose(dem.extent, (100.0, 100.3, 39.8, 40.0))


# ---------------------------------------------------------------- 几何 / 地图
def test_simplify_and_clip():
    t = np.linspace(0, 2 * np.pi, 2000)
    xy = np.c_[np.cos(t), np.sin(t)]
    s = geo.simplify(xy, 1e-3)
    assert 20 < len(s) < 400 and np.allclose(s[0], xy[0]) and np.allclose(s[-1], xy[-1])
    sq = np.array([[0, 0], [2, 0], [2, 2], [0, 2]], float)
    c = geo.clip_polygon(sq, (1, 3, -1, 1))
    assert np.allclose(sorted(map(tuple, c.round(9))), sorted([(1, 0), (2, 0), (2, 1), (1, 1)]))


@pytest.mark.skipif(not geo.gshhs_available("h"), reason="pip install basemap-data-hires")
def test_gshhs_new_zealand():
    polys = geo.read_gshhs("h", (166, 179, -47.5, -34), types=(1,))
    assert sum(len(b) for _, b in polys) > 5000


@cjk
def test_geomap_geojson_and_terrain_keep_aspect():
    cv = jt.Canvas(4, 3, dpi=100)
    ax = cv.inset(0.3, 0.3, 3.2, 2.4)
    m = geo.GeoMap(ax, (172.0, 173.0, -43.0, -42.3))
    dem = terrain.DEM(np.random.default_rng(0).normal(500, 50, (40, 50)), m.extent)
    terrain.draw(ax, dem, sea=False)
    assert abs(ax.get_aspect() - m.aspect) < 1e-9 and ax.get_xlim() == (172.0, 173.0)
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString",
                                         "coordinates": [[172.1, -42.9], [172.9, -42.4]]}},
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
            [[172.2, -42.8], [172.6, -42.8], [172.6, -42.5], [172.2, -42.5]],
            [[172.3, -42.7], [172.4, -42.7], [172.4, -42.6]]]}},
        {"type": "Feature", "geometry": {"type": "MultiPoint",
                                         "coordinates": [[172.5, -42.6], [172.7, -42.7]]}}]}
    assert m.geojson(gj) == 4
    m.graticule(0.25)
    m.ticks(0.25)
    m.zebra(0.25)
    m.scale_bar(20)
    m.north_arrow()
    assert geo.nice_step(m.extent) == 0.2
    cv.close()


# ---------------------------------------------------------------- PPT
@cjk
def test_ppt_embeds_svg_with_png_fallback(tmp_path):
    pytest.importorskip("pptx")
    from shanhai_atlas.ppt import Deck
    cv = jt.Canvas(4, 2.25, dpi=100)
    cv.text(0.2, 0.6, "矢量图", size=14, color=jt.C.navy)
    stem = tmp_path / "fig"
    cv.save(stem, formats=("svg", "png"), check=False)
    cv.close()
    deck = Deck(footer="测试")
    deck.cover("封面")
    deck.figure("图页", str(stem) + ".svg", kicker="KICKER", notes="讲稿")
    out = deck.save(tmp_path / "t.pptx")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert any(n.endswith(".svg") for n in names) and any(n.endswith(".png") for n in names)
        slide = z.read("ppt/slides/slide2.xml").decode("utf-8")
        assert "svgBlip" in slide and "96DAC541" in slide
        assert "image/svg+xml" in z.read("[Content_Types].xml").decode("utf-8")
        assert any("notesSlide" in n for n in names)


# ---------------------------------------------------------------- 地震学工具

def test_catalog_csv_aliases_roundtrip_and_metadata(tmp_path):
    p = tmp_path / "events.tsv"
    p.write_text("id\ttime_utc\tlongitude\tlatitude\tdepth\tmag\n"
                 "e1\t2020-01-02T03:04:05Z\t172.5\t-42.8\t8.2\t3.4\n"
                 "e2\t2020-01-02T03:05:05Z\t172.6\t-42.7\t\t2.9\n", encoding="utf-8")
    cat = jt.read_catalog(p, source="test catalog", citation="Example citation")
    assert len(cat) == 2 and cat.event_id.tolist() == ["e1", "e2"]
    assert cat.depth_km[0] == pytest.approx(8.2) and np.isnan(cat.depth_km[1])
    out = cat.to_csv(tmp_path / "roundtrip.csv")
    reread = jt.read_catalog(out)
    assert np.allclose(reread.lon, cat.lon) and np.allclose(reread.magnitude, cat.magnitude)
    meta = (tmp_path / "roundtrip.csv.meta.json").read_text(encoding="utf-8")
    assert "Example citation" in meta and "test catalog" in meta


def test_fetch_usgs_catalog_query_and_disk_cache(tmp_path):
    payload = ("time,latitude,longitude,depth,mag,id\n"
               "2020-01-01T00:00:00.000Z,-42.5,173.0,12.5,3.2,us123\n").encode()
    calls = []

    def fetcher(url):
        calls.append(url)
        return payload

    kwargs = dict(extent=(172, 174, -43, -42), starttime="2020-01-01", endtime="2020-02-01",
                  min_magnitude=2.5, cache_dir=tmp_path, fetcher=fetcher)
    first = jt.fetch_usgs_catalog(**kwargs)
    second = jt.fetch_usgs_catalog(**{**kwargs, "fetcher": lambda url: pytest.fail("cache miss")})
    assert len(calls) == 1 and len(first) == len(second) == 1
    assert first.lon[0] == pytest.approx(173) and first.depth_km[0] == pytest.approx(12.5)
    assert "minmagnitude=2.5" in calls[0] and second.metadata["cache_hit"]
    with pytest.raises(ValueError, match="跨日期变更线"):
        jt.fetch_usgs_catalog((170, 190, -45, -40), "2020-01-01", "2020-02-01",
                              fetcher=fetcher)


def test_magnitude_sizes_and_cross_section_projection():
    sizes = jt.magnitude_sizes([1, 2, 3, np.nan], (10, 80), magnitude_range=(1, 3), levels=8)
    assert sizes[0] == 10 and sizes[2] == 80 and sizes[1] > sizes[0]
    assert sizes[3] == sizes[0]
    proj = jt.project_cross_section([0.5, 0.5], [0.1, -0.1], (0, 0), (1, 0))
    assert proj.length_km == pytest.approx(111.32)
    assert proj.along_km == pytest.approx([55.66, 55.66], abs=0.05)
    assert proj.offset_km[0] == pytest.approx(11.0574, abs=0.05)
    assert proj.offset_km[1] == pytest.approx(-11.0574, abs=0.05)


def test_seismic_plots_and_aki_b_value():
    import matplotlib.pyplot as plt

    cat = jt.EventCatalog(lon=[172.5, 172.6, 172.7, 172.8], lat=[-42.5] * 4,
                         depth_km=[5, 8, 12, 18], magnitude=[2.1, 2.3, 2.8, 3.2])
    fig, (map_ax, sec_ax, mfd_ax) = plt.subplots(1, 3)
    coll = jt.plot_events(map_ax, cat)
    assert len(coll.get_offsets()) == 4
    result = jt.plot_cross_section(sec_ax, cat, (172.4, -42.5), (172.9, -42.5),
                                   half_width_km=8, depth_limits_km=(0, 25))
    assert result.n_selected == 4 and sec_ax.get_ylim()[0] > sec_ax.get_ylim()[1]
    b, sb, n = jt.aki_b_value(cat.magnitude, 2.0, magnitude_bin=0.1)
    assert b > 0 and sb == pytest.approx(b / np.sqrt(n)) and n == 4
    mfd = jt.plot_magnitude_frequency(mfd_ax, cat.magnitude, mc=2.0, bin_width=0.1,
                                      magnitude_bin=0.1)
    assert mfd.n_complete == 4 and mfd.b_value == pytest.approx(b)
    plt.close(fig)


def test_geospatial_vector_quiver_units():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4, 3))
    m = geo.GeoMap(ax, (172, 174, -43, -42))
    q = m.vectors([173], [-42.5], [10], [5], key_km=10)
    assert q.U[0] == pytest.approx(10 / m.km_lon)
    assert q.V[0] == pytest.approx(5 / m.km_lat)
    plt.close(fig)


@cjk
def test_strict_save_does_not_reuse_stale_audit(tmp_path):
    cv = jt.Canvas(3, 2, dpi=100)
    cv.text(0.2, 0.6, "这段文字会越界" * 4, size=12, container=(0.2, 0.3, 0.8, 0.8))
    cv.audit(verbose=False)
    with pytest.raises(RuntimeError, match="layout audit failed"):
        cv.save(tmp_path / "must-not-save", formats=("svg",), strict=True)
    assert not (tmp_path / "must-not-save.svg").exists()
    cv.close()


@cjk
def test_pdf_is_vector_export_with_signature(tmp_path):
    cv = jt.Canvas(3, 2, dpi=100)
    cv.text(0.2, 0.6, "PDF 矢量图", size=12, color=jt.C.navy)
    cv.line([0.2, 2.8], [1.2, 1.2], color=jt.C.gold, lw=1.0)
    out = cv.save(tmp_path / "paper", formats=("svg", "pdf"), check=False)
    cv.close()
    assert [p.suffix for p in out] == [".svg", ".pdf"]
    pdf = (tmp_path / "paper.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-") and b"/Subtype /Image" not in pdf
    assert b"<svg" in (tmp_path / "paper.svg").read_bytes()


def test_focal_mechanism_optional_obspy():
    pytest.importorskip("obspy")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    geo.GeoMap(ax, (170, 176, -46, -40))
    ball = jt.focal_mechanism(ax, 173, -43, 30, 45, 90, width_km=12)
    assert ball in ax.collections
    assert ax.get_xlim() == (170, 176)
    plt.close(fig)
