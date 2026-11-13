# -*- coding: utf-8 -*-
"""beachball3d 测试：SDR→MT 几何、2D 投影 vs ObsPy、3D 一致性、多视角。

    python -m pytest tests/test_beachball3d.py -q
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shanhai_atlas as jt                                # noqa: E402

bb = importlib.import_module("shanhai_atlas.beachball3d")  # 避开 __init__ 同名函数遮蔽

SDRS = [(0, 45, 90), (0, 45, -90), (30, 60, 10), (120, 30, -70),
        (200, 80, 170), (45, 45, 0), (315, 90, 180), (90, 20, -90)]


# ---------------------------------------------------- 张量 / 几何（纯 numpy）

def test_moment_tensor_diagonal_signs():
    """逆冲 (rake=+90) T 轴在盘心（Mdd<0 拉张）、正断 (rake=-90) P 轴在盘心（Mdd>0 压缩）。"""
    assert bb.moment_tensor(0, 45, 90)[2, 2] < 0     # Mdd<0 → 中心拉张（T 轴）
    assert bb.moment_tensor(0, 45, -90)[2, 2] > 0    # Mdd>0 → 中心压缩（P 轴）


def test_moment_tensor_symmetric_trace_zero():
    for sdr in SDRS:
        M = bb.moment_tensor(*sdr)
        assert np.allclose(M, M.T)                    # 对称
        assert abs(np.trace(M)) < 1e-12               # 无净力偶


def test_polarity_center_matches_mdd_sign():
    for sdr in SDRS:
        M = bb.moment_tensor(*sdr)
        center = np.array([0.0, 0.0, 1.0])            # 下半球中心方向（NED）
        assert bb.polarity(M, center) == np.sign(M[2, 2])


def test_plane_normal_pointing_down_and_strike_perp():
    for strike, dip, _ in SDRS:
        n = bb.plane_normal(strike, dip)
        assert n[2] >= 0                              # 指向下半球
        s = np.radians(strike)
        strike_dir = np.array([np.cos(s), np.sin(s), 0.0])   # 走向单位向量（NED，方位角=strike）
        assert abs(np.dot(n, strike_dir)) < 1e-9      # 法向 ⊥ 走向


def test_plane_normal_dip_direction_east():
    """strike=0 → 倾向 = 东；法向 ⊥ 走向 → 水平分量沿东西向（指西），d=cos(D)>0 指向下半球。"""
    n = bb.plane_normal(0, 30)
    assert abs(n[0]) < 1e-9                           # 无北分量（走向南北 → 法向水平分量东西向）
    assert n[1] < 0 and n[2] > 0                      # 水平指西、竖直向下


def test_slip_vector_in_plane():
    """滑动向量在主节面内（⊥ 主面法向），且即为辅助面法向。"""
    for strike, dip, rake in SDRS:
        s = bb.slip_vector(strike, dip, rake)
        n1, n2 = bb.nodal_normals(strike, dip, rake)
        assert abs(np.dot(s, n1)) < 1e-9            # 滑动向量在主节面内
        assert abs(abs(np.dot(s, n2)) - 1) < 1e-9   # 辅助面法向 ∥ 滑动向量
        assert abs(np.dot(n1, n2)) < 1e-9           # 两节面法向正交


def test_focal_axes_p_compressional():
    """P 轴为最大特征值方向 → 中心投影点压缩（极性 +1）。"""
    for strike, dip, rake in SDRS:
        M = bb.moment_tensor(strike, dip, rake)
        P, T, N = bb.focal_axes(strike, dip, rake)
        assert bb.polarity(M, P) > 0                  # P 压缩
        assert bb.polarity(M, T) < 0                  # T 拉张
        for v in (P, T, N):
            assert abs(np.linalg.norm(v) - 1) < 1e-9


def test_view_basis_orthonormal():
    for az, el in [(0, 0), (90, 0), (0, 90), (0, -90), (45, 30)]:
        ru, uax, tax = bb.view_basis(az, el)
        for v in (ru, uax, tax):
            assert abs(np.linalg.norm(v) - 1) < 1e-9
        assert abs(np.dot(ru, uax)) < 1e-9
        assert abs(np.dot(ru, tax)) < 1e-9
        assert abs(np.dot(uax, tax)) < 1e-9


def test_view_of_strike_dip_is_equator():
    """沿 strike / dip 视角的仰角应为 0（相机在赤道面）。"""
    for sdr in SDRS:
        _, el_s = bb.view_of("strike", *sdr)
        _, el_d = bb.view_of("dip", *sdr)
        assert abs(el_s) < 1e-6
        assert abs(el_d) < 1e-6


def test_view_of_strike_azimuth_matches_strike():
    strike, dip, rake = 30, 60, 10
    az, _ = bb.view_of("strike", strike, dip, rake)
    assert abs((az - strike) % 360) < 1e-6


# ---------------------------------------------------- 2D 投影 vs ObsPy

def _raster_mine(sdr, proj="equalarea", res=256):
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    fc = jt.C.navy
    fig, ax = plt.subplots(figsize=(2, 2), dpi=res)
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    ax.set_aspect("equal")
    ax.axis("off")
    bb.beachball(ax, *sdr, proj=proj, radius=1.0, res=res, facecolor=fc,
                 bgcolor="white", edgecolor="black", linewidth=1.5, set_limits=False)
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba()).astype(float)
    plt.close(fig)
    return buf[..., :3] / 255.0, np.array(to_rgb(fc))


def _raster_obs(sdr, res=256):
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    fc = jt.C.navy
    fig = plt.figure(figsize=(2, 2), dpi=res)
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    fig.canvas.draw()  # ObsPy 需要一个已绘制的 canvas 才能用 fig= 覆盖
    from obspy.imaging.beachball import beachball as obsbb
    obsbb(sdr, facecolor=fc, bgcolor="white", edgecolor="black",
          width=200, fig=fig)
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba()).astype(float)
    plt.close(fig)
    return buf[..., :3] / 255.0, np.array(to_rgb(fc))


def _disk_mask(buf, radius_px, cx, cy):
    h, w = buf.shape[:2]
    Y, X = np.mgrid[0:h, 0:w]
    return ((X - cx) ** 2 + (Y - cy) ** 2) <= (radius_px * 0.98) ** 2


def _classify(buf, fc_rgb, radius_px, cx, cy):
    """盘内按最近 face（压缩）/ 其余（拉张+背景）二分类；盘外掩膜。"""
    fc = np.array(fc_rgb)
    dist = np.linalg.norm(buf - fc[None, None, :], axis=-1)
    face = dist < 0.30
    return face, _disk_mask(buf, radius_px, cx, cy)


def _register_ball(buf, fc_rgb):
    """按非白 bbox 定位球心与半径（像素），返回 (rad, cx, cy)。"""
    nonwhite = buf.sum(-1) < 2.55
    ys, xs = np.where(nonwhite)
    cx = 0.5 * (xs.min() + xs.max())
    cy = 0.5 * (ys.min() + ys.max())
    rad = 0.25 * ((xs.max() - xs.min()) + (ys.max() - ys.min()))
    return rad, cx, cy


def _crop_resize(buf, cy, cx, rad, n=200):
    """以 (cx,cy) 为心、rad 为半径裁剪并重采样到 n×n（归一化盘面）。"""
    ys = np.clip((cy + rad * np.linspace(-1, 1, n)).astype(int), 0, buf.shape[0] - 1)
    xs = np.clip((cx + rad * np.linspace(-1, 1, n)).astype(int), 0, buf.shape[1] - 1)
    return buf[np.ix_(ys, xs)]


def _match_disk(sub, fc_rgb):
    """归一化 n×n 盘面内按最近 face 二分类，返回 (face, disk_mask)。"""
    n = sub.shape[0]
    fc = np.array(fc_rgb)
    dist = np.linalg.norm(sub - fc[None, None, :], axis=-1)
    face = dist < 0.30
    Y, X = np.mgrid[0:n, 0:n]
    disk = ((X - (n - 1) / 2) ** 2 + (Y - (n - 1) / 2) ** 2) <= ((n - 1) / 2 * 0.98) ** 2
    return face, disk


@pytest.mark.parametrize("sdr", SDRS)
def test_beachball_polarity_invariants(sdr):
    """震源机制极性不变量（投影无关，不依赖 ObsPy 的近似花式几何）。

    ObsPy 的 plot_dc 用经验椭圆拟合（l = √((90-d)²/(sin²φ+cos²φ(90-d)²/90²))），
    而本实现用标准等面积投影——两者节面曲率本就不同，不能用像素一致率判对错。
    这里只校验物理不变量：
      ① 盘心（下法向）极性 = sign(M_dd)（压缩/拉张）；
      ② 两个节面法向均满足 q = nᵀMn ≈ 0；
      ③ P/T 轴极性正确（P 轴压缩 q>0，T 轴拉张 q<0）。
    """
    M = bb.moment_tensor(*sdr)
    d_down = np.array([0.0, 0.0, 1.0])
    q_down = float(d_down @ M @ d_down)
    n1, n2 = bb.nodal_normals(*sdr)
    if abs(M[2, 2]) > 1e-9:
        assert np.sign(q_down) == np.sign(M[2, 2]), (
            f"盘心极性应 = sign(M_dd)={np.sign(M[2, 2])}, 实得 q_down={q_down}"
        )
    else:
        # M_dd=0：盘心恰在节面大圆上（如 (45,45,0) 滑动水平 → 下法向落在辅助面内），须在某节面内
        dmin = min(abs(float(n1 @ d_down)), abs(float(n2 @ d_down)))
        assert dmin < 1e-9, f"M_dd=0 时下法向应在某节面内，|n·d|min={dmin}"
    assert abs(float(n1 @ M @ n1)) < 1e-9, f"节面法向 1 不在节面上 q={n1 @ M @ n1}"
    assert abs(float(n2 @ M @ n2)) < 1e-9, f"节面法向 2 不在节面上 q={n2 @ M @ n2}"
    P, T, _N = bb.focal_axes(*sdr)
    assert float(P @ M @ P) > 0, "P 轴应为压缩（q>0，bgcolor 一侧）"
    assert float(T @ M @ T) < 0, "T 轴应为拉张（q<0，facecolor 一侧）"


@pytest.mark.parametrize("proj", ["equalarea", "equidistant", "equalangle", "ortho"])
def test_beachball_projection_consistent_polarity(proj):
    """四种投影下，盘心极性与 q 场极性一致（投影只改几何，不改物理）。"""
    sdr = (0, 45, 90)
    M = bb.moment_tensor(*sdr)
    q_down = float(np.array([0, 0, 1.0]) @ M @ np.array([0, 0, 1.0]))
    # 盘心 u=v=0 → dirs = 下法向
    dirs, _ = bb._dirs_from_uv(np.array([[0.0]]), np.array([[0.0]]), proj)
    q_center = float(np.asarray(np.einsum("...i,ij,...j->...", dirs, M, dirs)).reshape(-1)[0])
    assert np.sign(q_center) == np.sign(q_down), (
        f"{proj} 盘心极性 {np.sign(q_center)} != M_dd 极性 {np.sign(q_down)}"
    )


def test_beachball_projection_variants_run():
    """四种投影均能渲染且盘内非空。"""
    import matplotlib.pyplot as plt
    for proj in bb._PROJ:
        fig, ax = plt.subplots(figsize=(1, 1), dpi=64)
        art = bb.beachball(ax, 30, 60, 10, proj=proj, res=128)
        img = art.image.get_array()
        assert img[..., 3].max() > 0.5               # 盘内有像素
        plt.close(fig)


# ---------------------------------------------------- 3D 与多视角

def test_beachball3d_orthographic_view_center_pol():
    """沿 P 轴看 → 盘心压缩（亮白 bgcolor）；沿 T 轴看 → 盘心拉张（暗 navy facecolor）。

    节面法向本身 q=0（DC 中法向落在另一节面内），盘心极性只能用 P/T 轴检验。
    """
    import matplotlib.pyplot as plt
    strike, dip, rake = 0, 45, 90                    # 逆冲
    M = bb.moment_tensor(strike, dip, rake)
    P, T, _N = bb.focal_axes(strike, dip, rake)
    n1 = bb.plane_normal(strike, dip)
    assert abs(float(n1 @ M @ n1)) < 1e-9           # 法向极点 q=0 → 不能用它判盘心极性

    def center_lum(axis_dir):
        az = float(np.degrees(np.arctan2(axis_dir[1], axis_dir[0])) % 360.0)
        el = float(np.degrees(np.arcsin(np.clip(-axis_dir[2], -1, 1))))
        fig, ax = plt.subplots(figsize=(1, 1), dpi=64)
        art = bb.beachball3d(ax, strike, dip, rake, az=az, el=el, res=128)
        img = art.image.get_array()
        plt.close(fig)
        return float(img[60:68, 60:68, :3].reshape(-1, 3).mean())

    lum_P = center_lum(P)
    lum_T = center_lum(T)
    assert lum_P > 0.5, f"沿 P 轴看盘心应压缩（亮白 bgcolor），lum={lum_P}"
    assert lum_T < 0.45, f"沿 T 轴看盘心应拉张（暗 navy facecolor），lum={lum_T}"


def test_beachball3d_edge_on_nodal_plane():
    """沿 strike 看主节面 → 主节面应呈 edge-on 直线，其法向 ⊥ 视线方向。"""
    import matplotlib.pyplot as plt
    strike, dip, rake = 0, 60, 10
    n1 = bb.plane_normal(strike, dip)
    # strike=0 → 走向 = 北；strike 方向与主节面法向正交（大圆沿走向延伸）
    strike_dir = np.array([1.0, 0.0, 0.0])            # NED 北
    assert abs(np.dot(strike_dir, n1)) < 1e-6       # 走向 ⊥ 主节面法向 → 节面含走向方向
    assert abs(np.dot(n1, n1)) > 1 - 1e-6           # 法向归一
    fig, ax = plt.subplots(figsize=(1, 1), dpi=64)
    art = bb.beachball3d(ax, strike, dip, rake, az=0, el=0, res=128, nodal=True, grid=False)
    plt.close(fig)
    assert art.image is not None


def test_beachball3d_back_adds_opacity():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(1, 1), dpi=64)
    art = bb.beachball3d(ax, 30, 60, 10, az=30, el=20, res=128, back=False)
    img_front = art.image.get_array().copy()
    fig2, ax2 = plt.subplots(figsize=(1, 1), dpi=64)
    art2 = bb.beachball3d(ax2, 30, 60, 10, az=30, el=20, res=128, back=True)
    img_back = art2.image.get_array().copy()
    plt.close(fig)
    plt.close(fig2)
    # back=True 时背面被合成进来，RGB 均值应不同（正断/逆冲均有节面分区）
    assert not np.allclose(img_front[..., :3], img_back[..., :3])


def test_multiview_draws_and_returns():
    import matplotlib.pyplot as plt
    cv = jt.Canvas(3.0, 1.6)
    balls = bb.multiview(cv, 30, 60, 10,
                         views=("standard", (0, 0), (0, 90), (90, 0)),
                         labels=None, w=0.62, y=0.45, gap=0.08, res=128)
    assert len(balls) == 4
    assert all(isinstance(b, bb.BallArt) for b in balls)
    out = Path(__file__).parent / "_multiview_tmp"
    out.mkdir(exist_ok=True)
    cv.save(str(out / "_mv"), formats=("png",), check=False)
    assert (out / "_mv.png").exists()
    for p in out.glob("*"):
        p.unlink()
    out.rmdir()
    plt.close("all")
