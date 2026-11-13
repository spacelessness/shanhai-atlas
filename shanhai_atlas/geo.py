# -*- coding: utf-8 -*-
"""地理底图：经纬度地图 + 海岸线 + 经纬网 + 黑白斑马图框 + 比例尺 + 指北针 + 位置图。

投影：经纬度等距圆柱，纵横比 1/cos φ₀（φ₀ = 图幅中纬度）——区域图（跨度 ≲ 15°）
几何误差可忽略，且与常用局部坐标 x = Δlon·111.320·cos φ₀、y = Δlat·110.574 完全一致。
全球 / 洲际尺度请改用 cartopy。

海岸线：GSHHG（Wessel & Smith, 1996；LGPL-3.0）。离线数据来自 PyPI 纯数据包：
    pip install basemap-data-hires   # 分辨率 f（全）/ h（高），~91 MB
    pip install basemap-data         # 分辨率 i / l / c，~31 MB
也可叠加任意 GeoJSON / Shapefile（断层迹线、河流、行政区……）。
"""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import matplotlib.patheffects as pe
from matplotlib.patches import Polygon, Rectangle
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch

from .fonts import FONT
from .theme import C

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320          # 赤道处；乘 cos φ


# ================================================================ GSHHG 读取
def _gshhs_dir(res):
    for mod in ("mpl_toolkits.basemap_data",):
        try:
            s = importlib.util.find_spec(mod)
        except (ImportError, ValueError):
            s = None
        if s is None:
            continue
        for d in s.submodule_search_locations:
            if (Path(d) / f"gshhs_{res}.dat").exists():
                return Path(d)
    return None


def gshhs_available(res="f"):
    return _gshhs_dir(res) is not None


@lru_cache(maxsize=32)
def _read_gshhs(res, bbox, types):
    d = _gshhs_dir(res)
    if d is None:
        hint = "basemap-data-hires" if res in ("f", "h") else "basemap-data"
        raise FileNotFoundError(f"缺少 GSHHG 分辨率 {res!r} 海岸线数据：pip install {hint}")
    out = []
    with open(d / f"gshhsmeta_{res}.dat") as meta, open(d / f"gshhs_{res}.dat", "rb") as dat:
        for ln in meta:
            p = ln.split()
            typ, npts, south, north = int(p[0]), int(p[2]), float(p[3]), float(p[4])
            off, nb = int(p[5]), int(p[6])
            if typ not in types or north < bbox[2] or south > bbox[3]:
                continue
            dat.seek(off)
            b = np.frombuffer(dat.read(nb), dtype="<f4").astype(float).reshape(npts, 2)
            if b[:, 0].max() < bbox[0] or b[:, 0].min() > bbox[1]:
                continue
            out.append((typ, b))
    return out


def read_gshhs(res="f", bbox=(-180, 180, -90, 90), types=(1, 2, 3, 4)):
    """读取 GSHHG 多边形：返回 [(类型, N×2 数组 lon/lat)]；类型 1 陆地 2 湖 3 湖中岛 4 岛中塘。"""
    bbox = tuple(round(float(v), 4) for v in bbox)
    return _read_gshhs(res, bbox, tuple(types))


# ================================================================ 几何工具
def clip_polygon(xy, box):
    """Sutherland–Hodgman：多边形裁剪到矩形 box=(x0, x1, y0, y1)。"""
    x0, x1, y0, y1 = box
    pts = np.asarray(xy, float)
    for axis, val, keep_ge in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        if len(pts) == 0:
            break
        cur = pts
        prev = np.roll(cur, 1, axis=0)
        inside = cur[:, axis] >= val if keep_ge else cur[:, axis] <= val
        pin = np.roll(inside, 1)
        out = []
        for p, q, ip, iq in zip(prev, cur, pin, inside):
            if iq:
                if not ip:
                    t = (val - p[axis]) / (q[axis] - p[axis])
                    out.append(p + t * (q - p))
                out.append(q)
            elif ip:
                t = (val - p[axis]) / (q[axis] - p[axis])
                out.append(p + t * (q - p))
        pts = np.array(out) if out else np.zeros((0, 2))
    return pts


def thin(xy, eps):
    """顶点抽稀：丢弃与上一个保留点距离 < eps 的点（保持首尾）。"""
    xy = np.asarray(xy, float)
    if len(xy) < 4 or eps <= 0:
        return xy
    keep = [0]
    last = xy[0]
    for i in range(1, len(xy) - 1):
        if abs(xy[i, 0] - last[0]) + abs(xy[i, 1] - last[1]) >= eps:
            keep.append(i)
            last = xy[i]
    keep.append(len(xy) - 1)
    return xy[keep]


def simplify(xy, tol, scale=(1.0, 1.0)):
    """Ramer–Douglas–Peucker 折线化简：tol 为容差（按 scale 缩放后的各向同性单位，常用英寸）。"""
    xy = np.asarray(xy, float)
    n = len(xy)
    if n < 3 or tol <= 0:
        return xy
    p = xy / np.asarray(scale, float)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = p[i], p[j]
        dx, dy = b - a
        L = np.hypot(dx, dy)
        q = p[i + 1:j]
        if L == 0:
            d = np.hypot(q[:, 0] - a[0], q[:, 1] - a[1])
        else:
            d = np.abs(dx * (q[:, 1] - a[1]) - dy * (q[:, 0] - a[0])) / L
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return xy[keep]


def nice_step(extent, target=6):
    """经纬网间隔：使较长边约有 target 条网格线。"""
    span = max(extent[1] - extent[0], extent[3] - extent[2])
    for s in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 30):
        if span / s <= target + 1:
            return s
    return 30


def _fmt_deg(v, step, pos, neg):
    s = f"{abs(v):.3f}".rstrip("0").rstrip(".")
    return s + "°" + (pos if v >= 0 else neg) if abs(v) > 1e-12 else s + "°"


# ================================================================ 地图
class GeoMap:
    """在一个 matplotlib Axes 上建立经纬度地图。

    >>> ax = cv.inset(1.0, 1.6, 8.0, 6.6)
    >>> m = GeoMap(ax, (172.4, 173.95, -43.1, -42.15))
    >>> m.coast("f"); m.graticule(0.25); m.ticks(0.25); m.zebra(0.25)
    >>> m.points(lon, lat, s=3, c=colors); m.scale_bar(20); m.north_arrow()
    """

    def __init__(self, ax, extent, phi0=None, sea=C.sea, frame=True):
        self.ax = ax
        self.extent = tuple(float(v) for v in extent)
        lo0, lo1, la0, la1 = self.extent
        self.phi0 = (la0 + la1) / 2.0 if phi0 is None else float(phi0)
        self.aspect = 1.0 / np.cos(np.radians(self.phi0))
        self.km_lon = KM_PER_DEG_LON * np.cos(np.radians(self.phi0))
        self.km_lat = KM_PER_DEG_LAT
        ax.set_xlim(lo0, lo1)
        ax.set_ylim(la0, la1)
        ax.set_aspect(self.aspect)
        ax.set_facecolor(sea)
        ax.patch.set_alpha(1.0)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(frame)
            s.set_color(C.navy)
            s.set_linewidth(0.6)
        self._step = None

    # ---------------------------------------------------------- 尺寸换算
    def size_in(self):
        """坐标轴实际绘制尺寸（英寸，已考虑纵横比约束）。"""
        self.ax.apply_aspect()
        pos = self.ax.get_position()
        fw, fh = self.ax.figure.get_size_inches()
        return pos.width * fw, pos.height * fh

    def in2deg(self, inches):
        """英寸 → (Δlon, Δlat)。"""
        w, h = self.size_in()
        lo0, lo1, la0, la1 = self.extent
        return inches / w * (lo1 - lo0), inches / h * (la1 - la0)

    def km2deg(self, dx_km, dy_km):
        return dx_km / self.km_lon, dy_km / self.km_lat

    def to_km(self, lon, lat):
        lo0, lo1, la0, la1 = self.extent
        return ((np.asarray(lon) - (lo0 + lo1) / 2) * self.km_lon,
                (np.asarray(lat) - (la0 + la1) / 2) * self.km_lat)

    # ---------------------------------------------------------- 底图
    def coast(self, res="f", land=C.land, edge=C.coast, lw=0.6, lake=None, margin=0.15,
              eps_in=0.003, z=1):
        """GSHHG 陆地 / 湖泊填色 + 海岸线（先裁剪到图幅、再按屏幕精度抽稀，SVG 精简）。

        land=None 时只画海岸线（下面已有地形晕渲时使用）。"""
        lo0, lo1, la0, la1 = self.extent
        mx, my = (lo1 - lo0) * margin, (la1 - la0) * margin
        box = (lo0 - mx, lo1 + mx, la0 - my, la1 + my)
        ex, ey = self.in2deg(1.0)                      # 每英寸对应的经 / 纬度
        lake = lake or self.ax.get_facecolor()
        n = 0
        for typ, b in read_gshhs(res, box):
            xy = simplify(clip_polygon(b, box), eps_in, scale=(ex, ey))
            if len(xy) < 3:
                continue
            fc = (land if typ in (1, 3) else lake) if land is not None else "none"
            self.ax.add_patch(Polygon(xy, closed=True, fc=fc, ec=edge, lw=lw, zorder=z + 0.01 * typ))
            n += len(xy)
        return n

    def graticule(self, step=0.25, color=C.graticule, lw=0.45, ls=(0, (3, 2)), z=1.5):
        lo0, lo1, la0, la1 = self.extent
        self._step = step
        for v in np.arange(np.ceil(lo0 / step) * step, lo1 + 1e-9, step):
            if lo0 < v < lo1:
                self.ax.axvline(v, color=color, lw=lw, ls=ls, zorder=z)
        for v in np.arange(np.ceil(la0 / step) * step, la1 + 1e-9, step):
            if la0 < v < la1:
                self.ax.axhline(v, color=color, lw=lw, ls=ls, zorder=z)

    def ticks(self, step=None, sides="lb", size=7.2, color=C.gray, pad=7):
        step = step or self._step or 0.5
        lo0, lo1, la0, la1 = self.extent
        xs = [v for v in np.arange(np.ceil(lo0 / step) * step, lo1 + 1e-9, step) if lo0 < v < lo1]
        ys = [v for v in np.arange(np.ceil(la0 / step) * step, la1 + 1e-9, step) if la0 < v < la1]
        ax = self.ax
        ax.set_xticks(xs)
        ax.set_yticks(ys)
        ax.set_xticklabels([_fmt_deg(v, step, "E", "W") for v in xs])
        ax.set_yticklabels([_fmt_deg(v, step, "N", "S") for v in ys])
        ax.tick_params(labelsize=size, length=0, pad=pad, colors=color,
                       bottom="b" in sides, labelbottom="b" in sides, top="t" in sides,
                       labeltop="t" in sides, left="l" in sides, labelleft="l" in sides,
                       right="r" in sides, labelright="r" in sides)

    def zebra(self, step=None, width_in=0.045, color=C.navy):
        """经典黑白相间图框（与经纬网刻度对齐），画在图框外侧。"""
        step = step or self._step or 0.5
        lo0, lo1, la0, la1 = self.extent
        dx, dy = self.in2deg(width_in)
        xs = np.r_[lo0, [v for v in np.arange(np.ceil(lo0 / step) * step, lo1, step) if v > lo0], lo1]
        ys = np.r_[la0, [v for v in np.arange(np.ceil(la0 / step) * step, la1, step) if v > la0], la1]
        kw = dict(ec=color, lw=0.5, clip_on=False, zorder=20)
        for i in range(len(xs) - 1):
            fc = color if i % 2 == 0 else "white"
            for y in (la0 - dy, la1):
                self.ax.add_patch(Rectangle((xs[i], y), xs[i + 1] - xs[i], dy, fc=fc, **kw))
        for i in range(len(ys) - 1):
            fc = color if i % 2 == 0 else "white"
            for x in (lo0 - dx, lo1):
                self.ax.add_patch(Rectangle((x, ys[i]), dx, ys[i + 1] - ys[i], fc=fc, **kw))
        for x, y in ((lo0 - dx, la0 - dy), (lo1, la0 - dy), (lo0 - dx, la1), (lo1, la1)):
            self.ax.add_patch(Rectangle((x, y), dx, dy, fc=color, **kw))
        for s in self.ax.spines.values():
            s.set_visible(False)

    def scale_bar(self, length_km=20, segments=2, loc=(0.04, 0.05), height_in=0.06, size=7.0,
                  color=C.navy):
        """黑白分段比例尺；loc 为左下角在坐标轴内的相对位置。"""
        lo0, lo1, la0, la1 = self.extent
        x0 = lo0 + loc[0] * (lo1 - lo0)
        y0 = la0 + loc[1] * (la1 - la0)
        _, h = self.in2deg(height_in)
        seg = length_km / segments
        for i in range(segments):
            a = x0 + i * seg / self.km_lon
            self.ax.add_patch(Rectangle((a, y0), seg / self.km_lon, h,
                                        fc=color if i % 2 == 0 else "white", ec=color, lw=0.6,
                                        zorder=12))
        _, ty = self.in2deg(0.05)
        halo = [pe.withStroke(linewidth=2.2, foreground="white")]
        for i in range(segments + 1):
            v = i * seg
            lab = f"{v:g}" + (" km" if i == segments else "")
            self.ax.text(x0 + v / self.km_lon, y0 + h + ty, lab, fontsize=size, color=C.ink,
                         ha="center", va="bottom", zorder=12, path_effects=halo)

    def north_arrow(self, loc=(0.94, 0.86), size_in=0.30, color=C.navy, fontsize=9):
        """双色指北针；loc 为箭头中心在坐标轴内的相对位置。"""
        lo0, lo1, la0, la1 = self.extent
        x = lo0 + loc[0] * (lo1 - lo0)
        y = la0 + loc[1] * (la1 - la0)
        dx, dy = self.in2deg(size_in)
        L, Wd = dy / 2, dx * 0.16
        for side, fc in ((-1, color), (1, "white")):
            self.ax.add_patch(Polygon([[x, y + L], [x + side * Wd, y - L * 0.55], [x, y - L * 0.15]],
                                      closed=True, fc=fc, ec=color, lw=0.6, zorder=12))
        self.ax.text(x, y + L + dy * 0.06, "N", fontsize=fontsize, weight=700, color=color,
                     ha="center", va="bottom", family=FONT.serif, zorder=12,
                     path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])

    # ---------------------------------------------------------- 数据
    def points(self, lon, lat, s=3.0, c=C.blue, alpha=0.85, z=3, **kw):
        """散点。s 为数组时按取值分组、由小到大逐组绘制——同组复用同一标记，SVG 体积小得多
        （建议先把 s 量化为少数几档，如按 0.5 级震级分档）。"""
        lw = kw.pop("lw", 0)
        if np.ndim(s) == 0:
            return self.ax.scatter(lon, lat, s=s, c=c, lw=lw, alpha=alpha, zorder=z, **kw)
        s = np.round(np.asarray(s, float), 3)
        lon, lat = np.asarray(lon), np.asarray(lat)
        carr = np.asarray(c, dtype=object) if not isinstance(c, str) else None
        out = None
        for k, v in enumerate(np.unique(s)):
            sel = s == v
            cc = c if carr is None or carr.ndim == 0 else list(carr[sel])
            out = self.ax.scatter(lon[sel], lat[sel], s=float(v), c=cc, lw=lw, alpha=alpha,
                                  zorder=z + 1e-4 * k, **kw)
        return out

    def vectors(self, lon, lat, east_km, north_km, *, factor=1.0, color=C.clay, width=0.0022,
                key_km=None, key_loc=(0.82, 0.06), key_label=None, z=5, **kw):
        """绘制区域位移 / 速度向量；分量 east_km、north_km 用 km 表示。

        ``factor`` 可把速度（如 mm/yr）换算成指定绘图时段对应的位移；箭头按局部纬度
        分别换算经纬度，``key_km`` 可添加一个东向比例箭头。区域投影近似适用于小范围地图。
        """
        lon, lat, east_km, north_km = np.broadcast_arrays(
            np.asarray(lon, float), np.asarray(lat, float),
            np.asarray(east_km, float), np.asarray(north_km, float))
        valid = np.isfinite(lon) & np.isfinite(lat) & np.isfinite(east_km) & np.isfinite(north_km)
        dlon = east_km[valid] * float(factor) / self.km_lon
        dlat = north_km[valid] * float(factor) / self.km_lat
        q = self.ax.quiver(lon[valid], lat[valid], dlon, dlat, angles="xy", scale_units="xy",
                           scale=1, color=color, width=width, zorder=z, **kw)
        if key_km is not None:
            if key_km <= 0:
                raise ValueError("key_km 必须为正")
            label = key_label or f"{key_km:g} km"
            self.ax.quiverkey(q, key_loc[0], key_loc[1], key_km / self.km_lon,
                              label, coordinates="axes", labelpos="E", color=color,
                              labelcolor=color, fontproperties={"size": 6.5})
        return q

    def text(self, lon, lat, s, size=7.6, color=C.ink, halo=True, z=7, **kw):
        pe_ = [pe.withStroke(linewidth=2.6, foreground="white")] if halo else None
        return self.ax.text(lon, lat, s, fontsize=size, color=color, zorder=z, path_effects=pe_,
                            **kw)

    def place(self, lon, lat, name, side="right", size=7.6, marker="s", ms=3.6, color=C.ink):
        """城镇 / 站点：小方块 + 名称（白色描边）。"""
        self.ax.plot([lon], [lat], marker=marker, ms=ms, color=color, zorder=7)
        dx, _ = self.in2deg(0.07)
        self.text(lon + (dx if side == "right" else -dx), lat, name, size=size, color=color,
                  ha="left" if side == "right" else "right", va="center")

    def label_area(self, lon, lat, text, size=8.0, color=C.sea_label, italic=True, halo=False):
        """海域 / 地区名（斜体、浅色）；底下有地形晕渲时设 halo=True 加白描边。"""
        pe_ = [pe.withStroke(linewidth=2.4, foreground="white")] if halo else None
        return self.ax.text(lon, lat, text, fontsize=size, color=color,
                            style="italic" if italic else "normal", ha="center", va="center",
                            zorder=2 if not halo else 6, linespacing=1.5, path_effects=pe_)

    def box(self, extent, color=C.clay, lw=1.2, z=8, **kw):
        lo0, lo1, la0, la1 = extent
        return self.ax.add_patch(Rectangle((lo0, la0), lo1 - lo0, la1 - la0, fc="none",
                                           ec=color, lw=lw, zorder=z, **kw))

    def geojson(self, data, color=C.ink, lw=0.8, fc="none", ms=3.0, alpha=1.0, z=4, **kw):
        """叠加 GeoJSON（路径 / dict）：线、面、点。返回绘制要素数。"""
        if isinstance(data, (str, Path)):
            data = json.loads(Path(data).read_text(encoding="utf-8"))
        feats = data.get("features", [data]) if data.get("type") == "FeatureCollection" or \
            data.get("type") == "Feature" else [{"geometry": data}]
        n = 0
        for f in feats:
            g = f.get("geometry", f)
            if g is None:
                continue
            t, cs = g["type"], g.get("coordinates")
            if t == "GeometryCollection":
                for gg in g["geometries"]:
                    n += self.geojson(gg, color, lw, fc, ms, alpha, z, **kw)
                continue
            lines = {"LineString": [cs], "MultiLineString": cs}.get(t)
            polys = {"Polygon": [cs], "MultiPolygon": cs}.get(t)
            pts = {"Point": [cs], "MultiPoint": cs}.get(t)
            for ln in lines or []:
                a = np.asarray(ln, float)
                self.ax.plot(a[:, 0], a[:, 1], color=color, lw=lw, alpha=alpha, zorder=z, **kw)
                n += 1
            for poly in polys or []:
                verts, codes = [], []
                for ring in poly:
                    a = np.asarray(ring, float)[:, :2]
                    verts += a.tolist() + [a[0].tolist()]
                    codes += [MPath.MOVETO] + [MPath.LINETO] * (len(a) - 1) + [MPath.CLOSEPOLY]
                self.ax.add_patch(PathPatch(MPath(verts, codes), fc=fc, ec=color, lw=lw,
                                            alpha=alpha, zorder=z))
                n += 1
            if pts:
                a = np.asarray(pts, float)
                self.ax.plot(a[:, 0], a[:, 1], ls="none", marker="o", ms=ms, color=color,
                             zorder=z)
                n += len(a)
        return n

    def shapefile(self, path, **kw):
        """叠加 Shapefile（需 pip install pyshp），样式参数同 geojson()。"""
        import shapefile                        # pyshp
        with shapefile.Reader(str(path)) as r:
            return self.geojson(r.__geo_interface__, **kw)


def locator(ax, extent, highlight, res="h", land="#D5DCE4", edge="#9AA6B3", sea="#EEF2F6",
            color=C.clay, min_pts=20):
    """位置图：小比例尺底图 + 研究区红框。"""
    m = GeoMap(ax, extent, sea=sea)
    lo0, lo1, la0, la1 = extent
    ex, ey = m.in2deg(1.0)
    for typ, b in read_gshhs(res, (lo0 - 1, lo1 + 1, la0 - 1, la1 + 1), types=(1,)):
        if len(b) < min_pts:
            continue
        xy = simplify(b, 0.004, scale=(ex, ey))
        ax.add_patch(Polygon(xy, closed=True, fc=land, ec=edge, lw=0.4, zorder=1))
    m.box(highlight, color=color, lw=1.2)
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color("#C3CCD6")
        s.set_linewidth(0.6)
    return m
