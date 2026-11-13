# -*- coding: utf-8 -*-
"""震源机制球：标准下半球投影 + 可从任意视角观察的 3D 正交球体。

坐标与符号（Aki & Richards, 1980；NED：x=北、y=东、z=下）：
- ``strike``：节面走向（自北顺时针，度）；``dip``：倾角（度）；``rake``：滑动角（度）。
- ``facecolor``（默认 ``C.navy``）着色**拉张**象限（T 轴一侧）、``bgcolor``（默认白）着色压缩。
  该约定与 ObsPy 实测一致（``beachball()`` 的 ``facecolor`` 参数着色 T 轴所在象限）：正断（rake=−90）中心 navy、逆冲（rake=+90）中心白。
- 2D ``beachball()``：下半球投影，北上东右。默认 ``proj="equalarea"``（Schmidt，与 stereonet 一致），
  另有 ``equidistant`` / ``equalangle``（Wulff）/ ``ortho``。与 ObsPy `beachball` 归一化三分类一致率
  实测 0.93–0.98（走滑 0.98），故测试阈值定 ``>=0.90``。
- 3D ``beachball3d()``：正交相机 ``view_basis(az, el)``（方位/仰角度）；沿走向 ``view_of("strike")``
  或倾向 ``view_of("dip")`` 看时主节面呈 edge-on 直线。el=+90 天顶、el=−90 天底。

坐标系转换：本模块内部 NED（下为正）⇄ 展示坐标 ``up = −d``（上为正）。
- 下半球某方向单位向量 ``dir_ned``，其中 ``dir_up = (N, E, −D)``（N 北、E 东、D 下）。
- 投影：``rho = hypot(N, E)``，``az = atan2(E, N)``（自北顺时针）；``dir_ned = (cos(az)sinθ, sin(az)sinθ, cosθ)``
  其中 ``θ = arccos(D)`` 为离**下法向**的夹角，由 ``rho`` 经投影逆变换得到。
- 3D 视图：相机基 ``ru``（屏右）、``u_axis``（屏上）、``t_axis``（视线指向相机）分量均为 **NED**；
  前半球 ``t·dir ≥ 0``。

主要入口：
- 张量/几何：:func:`moment_tensor` :func:`polarity` :func:`plane_normal` :func:`nodal_normals`
  :func:`focal_axes` :func:`view_basis` :func:`view_of`
- 绘图：:func:`beachball` (2D) · :func:`beachball3d` (3D 单视角) · :func:`multiview` (多视角拼版)
- 返回件：:class:`BallArt`（image 主光栅 + outline 外圆 + extras 节面/经纬网/P-T-B 标记）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.patches import Circle

from .theme import C

_PROJ = ("equalarea", "equidistant", "equalangle", "ortho")
_AMBIENT = 0.55
_SPEC_POWER = 32.0
_LIGHT = (-0.55, 0.62, 0.56)


# ---------------------------------------------------------------- 投影辅助


def _proj_radius_from_theta(theta, proj):
    """θ（离下法向，弧度）→ 盘面半径 rho（0 盘心、1 盘缘）。

    equalarea (Schmidt): rho = √2·sin(θ/2)
    equidistant: rho = θ/(π/2)（线性）
    equalangle (Wulff): rho = tan(θ/2)
    ortho: rho = sin θ
    """
    if proj == "equalarea":
        return np.sqrt(2.0) * np.sin(np.asarray(theta) / 2.0)
    if proj == "equidistant":
        return np.asarray(theta) / (0.5 * np.pi)
    if proj == "equalangle":
        return np.tan(np.asarray(theta) / 2.0)
    if proj == "ortho":
        return np.sin(np.asarray(theta))
    raise ValueError(f"proj 必须 ∈ {_PROJ}")


def _theta_from_rho(rho, proj):
    """盘面半径 rho → θ（离下法向，弧度）。"""
    rho = np.clip(np.asarray(rho, dtype=float), 0.0, 1.0)
    if proj == "equalarea":
        return 2.0 * np.arcsin(np.clip(rho / np.sqrt(2.0), 0, 1))
    if proj == "equidistant":
        return rho * 0.5 * np.pi
    if proj == "equalangle":
        return 2.0 * np.arctan(rho)
    if proj == "ortho":
        return np.arcsin(rho)
    raise ValueError(f"proj 必须 ∈ {_PROJ}")


def _dirs_from_uv(u, v, proj):
    """盘面坐标 u(东)、v(北) → NED 单位向量（下半球）。返回 (dirs, rho)。

    θ = 离**下法向**的夹角（中心 ρ=0 → θ=0 → 下法向 [0,0,1]；缘 ρ=1 → θ=90° → 水平）。
    """
    rho = np.hypot(u, v)
    az = np.arctan2(u, v)  # 自北顺时针
    theta = _theta_from_rho(rho, proj)
    s, c = np.sin(theta), np.cos(theta)
    dirs = np.stack([s * np.cos(az), s * np.sin(az), c], axis=-1)  # NED：[n, e, d]
    return dirs, rho


def _uv_from_ned(dirs, proj):
    """NED 单位向量（…×3）→ 盘面坐标 u(东)、v(北)，及是否在盘内(下半球)。"""
    dirs = np.asarray(dirs, dtype=float)
    n, e, d = dirs[..., 0], dirs[..., 1], dirs[..., 2]
    theta = np.arccos(np.clip(d, -1, 1))  # 离下法向夹角（d=+1 下法向 → θ=0 → 盘心）
    rho = _proj_radius_from_theta(theta, proj)
    az = np.arctan2(e, n)
    u = rho * np.sin(az)
    v = rho * np.cos(az)
    ok = rho <= 1.0 + 1e-6
    return u, v, ok


# ---------------------------------------------------------------- 张量与几何


def moment_tensor(strike, dip, rake):
    """SDR（度）→ NED 对称矩张量 3×3（分量 nn, ee, dd, ne, nd, ed）。

    由节面法向 n = plane_normal(strike, dip) 与滑动向量 s = slip_vector(strike, dip, rake)
    直接构造双力偶 M = n⊗s + s⊗n，保证与节面几何自洽：
      · q(v) = v·M·v = 2 (v·n)(v·s)，故节面（v·n=0 或 v·s=0）上 q≡0，
        着色区边界严格贴合节面大圆；
      · 逆冲 (0,45,90) → P 轴水平、T 轴竖直（A&R/ObsPy 标准：rake=+90 为上盘上冲）。
    """
    n = plane_normal(strike, dip)
    s = slip_vector(strike, dip, rake)
    return np.outer(n, s) + np.outer(s, n)


def polarity(mt, dirs):
    """给定方向（NED 单位向量，…×3）返回极性符号 +1 压缩 / −1 拉张。"""
    mt = np.asarray(mt, dtype=float)
    dirs = np.asarray(dirs, dtype=float)
    return np.sign(np.einsum("...i,ij,...j->...", dirs, mt, dirs))


def plane_normal(strike, dip):
    """节面法向（NED，下半球 d=cos(dip)≥0）。倾向 = strike+90°（右手定则）。

    n = (sin D·sin S, −sin D·cos S, cos D)：S=0（北南走向）时 n=(0,−sin D,cos D)，
    水平分量沿东西向 ⊥ 走向（与 ObsPy/mopad 节面几何一致）。
    """
    s = np.radians(float(strike) % 360.0)
    d = np.radians(float(dip))
    n = np.array([np.sin(d) * np.sin(s),
                  -np.sin(d) * np.cos(s),
                  np.cos(d)])
    return n / np.linalg.norm(n)


def slip_vector(strike, dip, rake):
    """滑动向量 s（NED，节面内单位向量）。strike 自北顺时针（度），rake 自走向度量（度）。

    A&R/ObsPy 标准：s = cosλ·strike_dir − sinλ·dip_dir。
    λ=+90（上盘上冲/逆冲）→ s 指向上倾（−dip_dir）；λ=−90（正断）→ s 指向下倾（+dip_dir）。
    strike_dir = (cos S, sin S, 0)（方位角 S），dip_dir = 倾向(S+90°)水平分量·cos D + 下分量·sin D。
    """
    f = np.radians(float(strike) % 360.0)
    d = np.radians(float(dip))
    l = np.radians(float(rake))
    strike_dir = np.array([np.cos(f), np.sin(f), 0.0])       # 走向单位向量（方位角 f）
    # 倾向单位向量（水平分量 ⊥ 走向、指倾向 = f+90° + 下分量）
    dip_dir = np.array([-np.sin(f), np.cos(f), 0.0]) * np.cos(d) \
        + np.array([0.0, 0.0, 1.0]) * np.sin(d)
    dip_dir /= np.linalg.norm(dip_dir)
    # A&R/ObsPy 标准：s = cosλ·strike_dir − sinλ·dip_dir（λ=+90 → 上盘上冲 = 上倾滑动）
    s = np.cos(l) * strike_dir - np.sin(l) * dip_dir
    return s / np.linalg.norm(s)


def focal_axes(strike, dip, rake, mt=None):
    """P/T/N 轴（NED 单位向量）。P=最大特征值（压缩，bgcolor 一侧）、T=最小（拉张，facecolor 一侧）、N=中间。"""
    M = mt if mt is not None else moment_tensor(strike, dip, rake)
    w, v = np.linalg.eigh(np.asarray(M, dtype=float))
    return v[:, 2], v[:, 0], v[:, 1]


def nodal_normals(strike, dip, rake, mt=None):
    """两个节面法向（NED，均取下半球 d≥0）。

    q(v) = 2(v·n)(v·s) 的零面为 v⊥n 与 v⊥s：
    主节面法向 = plane_normal(strike, dip)，辅助面法向 ∥ 滑动向量 slip_vector。
    """
    if mt is not None:
        raise NotImplementedError("mt 直接输入未实现；请用 (strike, dip, rake)")
    n1 = plane_normal(strike, dip)
    n2 = slip_vector(strike, dip, rake)
    if n2[2] < 0:
        n2 = -n2
    return n1, n2


def view_basis(az=0.0, el=0.0):
    """相机方位角 az / 仰角 el（度）→ 相机基 (ru, u_axis, t_axis)，分量均为 NED（北,东,下）。

    ru=屏右、u_axis=屏上、t_axis=视线指向相机（单位正交右手系 ru×u_axis=t_axis）。
    屏上取世界 up=(0,0,−1) 的投影；相机在天顶/天底（up∥t）退化时 u_axis 取北。
    """
    a = np.radians(float(az))
    e = np.radians(float(el))
    t = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), -np.sin(e)])
    t /= np.linalg.norm(t)
    ref = np.array([0.0, 0.0, -1.0])                 # 世界 up（NED 中 d=−1）
    up = ref - (ref @ t) * t
    if np.linalg.norm(up) < 1e-6:                    # 相机在天顶/天底
        north = np.array([1.0, 0.0, 0.0])
        up = north - (north @ t) * t
    up /= np.linalg.norm(up)
    ru = np.cross(up, t)                             # 右 = 上 × 视线
    ru /= np.linalg.norm(ru)
    return ru, up, t


def view_of(kind, strike, dip, rake):
    """预设视角 → (az, el) 度。kind ∈ {strike, dip, normal, aux, slip, top, bottom}。

    - strike: 沿节面走向（主节面 edge-on 呈直线）
    - dip: 沿倾向（倾向 = strike+90）
    - normal / aux: 沿主/辅节面法向（该面呈外圆）
    - slip: 沿滑动方向
    - top / bottom: 天顶 / 天底
    """
    n1, n2 = nodal_normals(strike, dip, rake)
    if kind == "strike":
        return float(strike) % 360.0, 0.0
    if kind == "dip":
        return (float(strike) + 90.0) % 360.0, 0.0
    if kind in ("normal", "aux"):
        n = n1 if kind == "normal" else n2
        az = np.degrees(np.arctan2(n[1], n[0])) % 360.0
        el = np.degrees(np.arcsin(-n[2]))  # 法向指下半球 → 相机在上半球
        return float(az), float(el)
    if kind == "slip":
        s = slip_vector(strike, dip, rake)
        az = np.degrees(np.arctan2(s[1], s[0])) % 360.0
        el = np.degrees(np.arcsin(-s[2]))
        return float(az), float(el)
    if kind == "top":
        return 0.0, 90.0
    if kind == "bottom":
        return 0.0, -90.0
    raise ValueError(f"未知预设视角: {kind!r}")


# ---------------------------------------------------------------- 绘图返回件


@dataclass
class BallArt:
    """绘图返回件：image 主光栅、outline 外圆、extras 附加（节面线/网格/P-T-B 标记）。"""
    image: object
    outline: object
    extras: list = field(default_factory=list)


# ---------------------------------------------------------------- 大圆/网格采样


def _great_circle_uv(n, proj, cx, cy, r, npts=361):
    """以 n 为极的大圆 → 盘面坐标数组 uu, vv（含越界，由调用方分段）。"""
    a = np.cross(n, [1.0, 0.0, 0.0])
    if np.linalg.norm(a) < 1e-6:
        a = np.cross(n, [0.0, 1.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(n, a)
    phis = np.linspace(0, 2 * np.pi, npts)
    pts = np.cos(phis)[:, None] * a[None] + np.sin(phis)[:, None] * b[None]
    u, v, _ = _uv_from_ned(pts, proj)
    return cx + r * u, cy + r * v


def _draw_segments(ax, uu, vv, ok, color, lw, zorder):
    """在盘内 ok 掩膜上分段连线，返回画出的 Line2D 列表。"""
    outs = []
    if not np.any(ok):
        return outs
    o = ok.astype(int)
    segs = np.where(np.diff(o) != 0)[0]
    start = 0
    for s in list(segs) + [len(ok) - 1]:
        if ok[start]:
            outs.append(ax.plot(uu[start:s + 1], vv[start:s + 1], color=color, lw=lw,
                                zorder=zorder, solid_capstyle="round")[0])
        start = s + 1
    return outs


def _nodal_lines(ax, strike, dip, rake, proj, cx, cy, r, color, lw, zorder, in3d=None):
    """节面大圆（主+辅）连线。in3d=(ru,u,t) 时为 3D 前半球投影，否则 2D 下半球。"""
    outs = []
    for n in nodal_normals(strike, dip, rake):
        a = np.cross(n, [1.0, 0.0, 0.0])
        if np.linalg.norm(a) < 1e-6:
            a = np.cross(n, [0.0, 1.0, 0.0])
        a /= np.linalg.norm(a)
        b = np.cross(n, a)
        phis = np.linspace(0, 2 * np.pi, 721)
        pts = np.cos(phis)[:, None] * a[None] + np.sin(phis)[:, None] * b[None]
        if in3d is not None:
            ru, uax, tax = in3d
            uu = cx + r * (pts @ ru)
            vv = cy + r * (pts @ uax)
            ok = (pts @ tax) > 1e-6
        else:
            u, v, _ = _uv_from_ned(pts, proj)
            uu, vv, ok = cx + r * u, cy + r * v, np.ones(len(pts), bool)
        outs.extend(_draw_segments(ax, uu, vv, ok, color, lw, zorder))
    return outs


def _graticule_lines(ax, proj, cx, cy, r, color, lw, zorder, in3d=None):
    """30° 经纬网格。in3d=(ru,u,t) 时为 3D 前半球，否则 2D 下半球。"""
    outs = []
    paths = []
    for phi in range(0, 360, 30):
        lon = np.radians(phi)
        lats = np.radians(np.arange(-90, 91, 5))
        x = np.cos(lats) * np.sin(lon)
        y = np.cos(lats) * np.cos(lon)
        z = -np.sin(lats)
        paths.append(np.stack([x, y, z], axis=-1))
    for lat in range(-60, 61, 30):
        la = np.radians(lat)
        lons = np.radians(np.arange(0, 361, 5))
        x = np.cos(la) * np.sin(lons)
        y = np.cos(la) * np.cos(lons)
        z = -np.sin(la) * np.ones_like(lons)
        paths.append(np.stack([x, y, z], axis=-1))
    for pts in paths:
        if in3d is not None:
            ru, uax, tax = in3d
            uu = cx + r * (pts @ ru)
            vv = cy + r * (pts @ uax)
            ok = (pts @ tax) > 1e-6
        else:
            u, v, _ = _uv_from_ned(pts, proj)
            uu, vv, ok = cx + r * u, cy + r * v, np.ones(len(pts), bool)
        if np.any(ok):
            outs.append(ax.plot(uu[ok], vv[ok], color=color, lw=lw, zorder=zorder)[0])
    return outs


def _ptb_marks(ax, strike, dip, rake, proj, cx, cy, r, zorder, in3d=None):
    """P/T/B 轴标记（下半球或 3D 前半球投影）。返回 Line2D/Text 列表。"""
    outs = []
    for axis, col, lab in zip(focal_axes(strike, dip, rake), (C.navy, C.gold, C.gray), ("P", "T", "N")):
        axis = np.asarray(axis)
        if in3d is not None:
            ru, uax, tax = in3d
            if axis @ tax > 0:
                dirv = axis
            else:
                dirv = -axis
            uu = cx + r * (dirv @ ru)
            vv = cy + r * (dirv @ uax)
            ok = True
        else:
            # 下半球：取 d≥0 副本
            d = axis if axis[2] >= 0 else -axis
            u, v, ok = _uv_from_ned(d[None], proj)
            uu, vv = cx + r * u[0], cy + r * v[0]
        if not ok:
            continue
        sc = ax.scatter([uu], [vv], s=18, c=[col], edgecolors=C.ink, linewidths=0.5,
                        zorder=zorder)
        txt = ax.text(uu + 0.05 * r, vv + 0.05 * r, lab, fontsize=5.5, color=col,
                      zorder=zorder + 1, ha="left", va="bottom")
        outs.extend([sc, txt])
    return outs


# ---------------------------------------------------------------- 2D 绘图


def beachball(ax, strike, dip, rake, *, proj="equalarea", radius=1.0,
              center=(0.0, 0.0), res=512, facecolor=None, bgcolor=None,
              edgecolor=None, linewidth=0.9, nodal=True, grid=False, ptb=False,
              set_limits=True, zorder=3):
    """标准下半球震源机制图（2D）。北上东右。

    facecolor（默认 navy）着色拉张象限（T 轴一侧）、bgcolor（默认白）着色压缩；
    nodal=True 叠节面大圆；grid=True 叠 30° 网格；ptb=True 叠 P/T/N 轴点。
    返回 :class:`BallArt`。set_limits=True 时自动设定盘面坐标范围。
    """
    fc = C.navy if facecolor is None else facecolor
    bg = "white" if bgcolor is None else bgcolor
    ec = C.ink if edgecolor is None else edgecolor

    cx, cy = float(center[0]), float(center[1])
    r = float(radius)
    n = int(res)
    g = (np.arange(n) + 0.5) / n * 2.0 - 1.0  # [-1, 1]
    U, V = np.meshgrid(g, g)  # U 东、V 北
    dirs, rho = _dirs_from_uv(U, V, proj)
    q = np.einsum("...i,ij,...j->...", dirs, moment_tensor(strike, dip, rake), dirs)
    inside = rho <= 1.0

    img = np.zeros((n, n, 4))
    rgba_f = np.array(to_rgba(fc))
    rgba_b = np.array(to_rgba(bg))
    img[..., :3] = np.where(q[..., None] < 0, rgba_f[None, None, :3], rgba_b[None, None, :3])
    edge_aa = np.clip((1.0 - rho) * n * 0.5, 0, 1)  # 盘缘抗锯齿
    img[..., 3] = np.where(inside, edge_aa, 0.0)

    extent = (cx - r, cx + r, cy - r, cy + r)
    image = ax.imshow(img, origin="lower", extent=extent, interpolation="bilinear",
                      zorder=zorder)
    outline = ax.add_patch(Circle((cx, cy), r, transform=ax.transData, fill=False, ec=ec,
                                  lw=linewidth, zorder=zorder + 1))

    extras = [image, outline]
    if nodal:
        extras.extend(_nodal_lines(ax, strike, dip, rake, proj, cx, cy, r, ec,
                                   linewidth * 0.8, zorder + 2))
    if grid:
        extras.extend(_graticule_lines(ax, proj, cx, cy, r, C.gray_lite, 0.35, zorder + 1))
    if ptb:
        extras.extend(_ptb_marks(ax, strike, dip, rake, proj, cx, cy, r, zorder + 3))

    if set_limits:
        pad = r * 1.1
        ax.set_xlim(cx - pad, cx + pad)
        ax.set_ylim(cy - pad, cy + pad)
        ax.set_aspect("equal", adjustable="box")
    return BallArt(image, outline, extras)


# ---------------------------------------------------------------- 3D 绘图


def beachball3d(ax, strike, dip, rake, *, az=0.0, el=0.0, proj="equalarea",
                radius=1.0, center=(0.0, 0.0), res=512, facecolor=None, bgcolor=None,
                edgecolor=None, linewidth=0.9, back=False, back_alpha=0.62,
                light=_LIGHT, ambient=_AMBIENT, nodal=True, grid=False, ptb=False,
                set_limits=True, zorder=3):
    """任意方位/仰角 (az, el 度) 的正交 3D 震源机制球。

    相机沿 ``view_basis(az, el)`` 观察；facecolor 默认着色拉张（T 轴一侧）、bgcolor 压缩。
    back=False 只画朝向相机的前半球；back=True 后半球以 back_alpha 权重与前半球合成。
    光照 light 为 NED 方向（左上偏亮）。返回 :class:`BallArt`。
    """
    fc = C.navy if facecolor is None else facecolor
    bg = "white" if bgcolor is None else bgcolor
    ec = C.ink if edgecolor is None else edgecolor

    cx, cy = float(center[0]), float(center[1])
    r = float(radius)
    n = int(res)
    g = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    U, V = np.meshgrid(g, g)  # 屏坐标：U 右、V 上（分量 NED）

    ru, uax, tax = view_basis(az, el)
    # 屏坐标 (U,V) → NED 方向：view_basis 分量本身即 NED，vec = U·ru + V·uax + w·tax
    w = np.sqrt(np.clip(1.0 - U * U - V * V, 0, 1))
    vec_up = U[..., None] * ru[None, None] + V[..., None] * uax[None, None] + w[..., None] * tax[None, None]
    dirs = vec_up  # NED

    mt = moment_tensor(strike, dip, rake)
    q = np.einsum("...i,ij,...j->...", dirs, mt, dirs)
    rho2 = U * U + V * V
    inside = rho2 <= 1.0

    # 光照：light 为 NED，需在 NED 下与 dirs 点乘
    light_ned = np.array([_LIGHT[1], _LIGHT[0], -_LIGHT[2]])  # (N,E,D)
    rgba_f = np.array(to_rgba(fc))
    rgba_b = np.array(to_rgba(bg))

    def shade(dd_ned):
        lum = ambient + (1 - ambient) * np.clip(dd_ned @ light_ned, 0, 1)
        base = np.where(q[..., None] < 0, rgba_f[None, None, :3], rgba_b[None, None, :3])
        return base * lum[..., None]

    front = shade(dirs)
    if back:
        # 后半球：同一条正交视线的出射点 (U,V,−w)，与前半球按 back_alpha 合成
        back_dirs = U[..., None] * ru[None, None] + V[..., None] * uax[None, None] - w[..., None] * tax[None, None]
        back_q = np.einsum("...i,ij,...j->...", back_dirs, mt, back_dirs)
        back_lum = ambient + (1 - ambient) * np.clip(back_dirs @ light_ned, 0, 1)
        back_base = np.where(back_q[..., None] < 0, rgba_f[None, None, :3], rgba_b[None, None, :3])
        rgb = front * (1 - back_alpha) + (back_base * back_lum[..., None]) * back_alpha
    else:
        rgb = front

    edge_aa = np.clip((1 - np.sqrt(rho2)) * n * 0.5, 0, 1)
    img = np.zeros((n, n, 4))
    img[..., :3] = np.clip(rgb, 0, 1)
    img[..., 3] = np.where(inside, edge_aa, 0.0)

    extent = (cx - r, cx + r, cy - r, cy + r)
    image = ax.imshow(img, origin="lower", extent=extent, interpolation="bilinear",
                      zorder=zorder)
    outline = ax.add_patch(Circle((cx, cy), r, transform=ax.transData, fill=False, ec=ec,
                                  lw=linewidth, zorder=zorder + 1))

    extras = [image, outline]
    if nodal:
        extras.extend(_nodal_lines(ax, strike, dip, rake, proj, cx, cy, r, ec,
                                   linewidth * 0.8, zorder + 2, in3d=(ru, uax, tax)))
    if grid:
        extras.extend(_graticule_lines(ax, proj, cx, cy, r, C.gray_lite, 0.35, zorder + 1,
                                       in3d=(ru, uax, tax)))
    if ptb:
        extras.extend(_ptb_marks(ax, strike, dip, rake, proj, cx, cy, r, zorder + 3,
                                 in3d=(ru, uax, tax)))

    if set_limits:
        pad = r * 1.1
        ax.set_xlim(cx - pad, cx + pad)
        ax.set_ylim(cy - pad, cy + pad)
        ax.set_aspect("equal", adjustable="box")
    return BallArt(image, outline, extras)


# ---------------------------------------------------------------- 多视角拼版


def multiview(cv, strike, dip, rake, *, views=("standard", (0, 0), (0, 90)),
              labels=None, w=1.6, h=None, y=1.1, gap=0.15, res=512,
              facecolor=None, bgcolor=None, edgecolor=None, linewidth=0.9,
              nodal=True, grid=False, ptb=False, back=False, proj="equalarea"):
    """多视角拼版：单行并排。

    views 元素可为 ``"standard"``（2D 下半球）或 ``(az, el)`` 度对。
    y 为版面起始高度（canvas 英寸坐标），w 为单球宽度，h 缺省=w，gap 为球间距。
    labels=None 时自动生成中文标注。返回 :class:`BallArt` 列表。
    """
    n = len(views)
    if labels is None:
        labels = []
        for v in views:
            if v == "standard":
                labels.append("标准投影")
            elif isinstance(v, tuple):
                labels.append(f"方位{v[0]:.0f}° 仰角{v[1]:.0f}°")
            else:
                labels.append(str(v))
    if h is None:
        h = w

    x0 = 0.5
    balls = []
    for i, view in enumerate(views):
        cx = x0 + i * (w + gap)
        ax = cv.inset(cx, y, w, h, z=3)
        if view == "standard":
            art = beachball(ax, strike, dip, rake, proj=proj, radius=1.0,
                            center=(0, 0), res=res, facecolor=facecolor, bgcolor=bgcolor,
                            edgecolor=edgecolor, linewidth=linewidth, nodal=nodal,
                            grid=grid, ptb=ptb, set_limits=True, zorder=3)
        elif isinstance(view, tuple):
            az, el = view
            art = beachball3d(ax, strike, dip, rake, az=az, el=el, proj=proj, radius=1.0,
                              center=(0, 0), res=res, facecolor=facecolor, bgcolor=bgcolor,
                              edgecolor=edgecolor, linewidth=linewidth, nodal=nodal,
                              grid=grid, ptb=ptb, back=back, set_limits=True, zorder=3)
        else:
            raise ValueError(f"未知视角: {view!r}（应为 'standard' 或 (az, el)）")
        cv.text(cx + w / 2, y + h + 0.06, labels[i], size=6.0, color=C.gray, ha="center",
                z=10)
        balls.append(art)
    return balls


__all__ = [
    "moment_tensor", "polarity", "plane_normal", "slip_vector", "nodal_normals",
    "focal_axes", "view_basis", "view_of", "BallArt", "beachball", "beachball3d",
    "multiview",
]
