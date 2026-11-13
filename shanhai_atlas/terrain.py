# -*- coding: utf-8 -*-
"""地形：DEM 读取 / 在线获取 / 山体阴影 / 分层设色 / 等高线。

DEM 来源
--------
* 本地文件：``load_dem()`` 支持 GeoTIFF（rasterio 或 tifffile）、ESRI ASCII（.asc）、
  NetCDF / GMT grd（需 xarray）、.npz / .npy。
* 示例数据：``sample_dem("jacksboro")``——matplotlib 自带的真实地形样例（3″ ≈ 90 m 网格，
  美国田纳西 Jacksboro 断层一带；matplotlib 未注明原始数据来源），``sample_dem("topobathy")``
  ——含水深的低分辨率地形网格（约 2′ × 1.3′，加拿大温哥华岛一带）。
* 在线：``fetch_terrarium(extent)``——AWS Open Data「Terrain Tiles」（Terrarium 编码 PNG，
  免注册；Mapzen / Tilezen Joerd 汇编 SRTM、GMTED2010、ETOPO1、3DEP 及各国 DEM），自动拼接、
  按纬度重采样为经纬度网格并缓存。**使用须按数据源署名**：``terrarium_credit(extent)``
  按范围给出 tilezen/joerd attribution.md 要求的署名文字。

渲染
----
``hillshade()``：法向量 · 光照方向（Lambert），可选 Mark (1992) 多方向斜向加权；
``shade()``：分层设色（sha.terrain / sha.sea）× 山体阴影（平地亮度保持原色）；
``draw()`` 画到普通坐标轴或 :class:`shanhai_atlas.geo.GeoMap`；``contours()`` 画等高线。
"""

from __future__ import annotations

import io
import math
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import matplotlib as mpl
from matplotlib.colors import Normalize

from .theme import C, CMAPS, resolve_cmap

TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

#: Terrain Tiles 数据源署名（摘自 tilezen/joerd docs/attribution.md，“Required attribution”）。
#: (经度范围, 纬度范围, 署名)；None 表示全球数据源，总是列出。使用前请以官方文档为准。
TERRARIUM_SOURCES = [
    (None, None, "United States 3DEP (formerly NED) and global GMTED2010 and SRTM terrain data "
                 "courtesy of the U.S. Geological Survey"),
    (None, None, "Global ETOPO1 terrain data U.S. National Oceanic and Atmospheric Administration"),
    ((-180, 180), (60, 90), "ArcticDEM terrain data DEM(s) were created from DigitalGlobe, Inc., "
                            "imagery and funded under National Science Foundation awards 1043681, "
                            "1559691, and 1542736"),
    ((112, 154), (-44, -9), "Australia terrain data © Commonwealth of Australia "
                            "(Geoscience Australia) 2017"),
    ((9.5, 17.2), (46.3, 49.1), "Austria terrain data © offene Daten Österreichs – Digitales "
                                "Geländemodell (DGM) Österreich"),
    ((-141, -52), (41.7, 83.5), "Canada terrain data contains information licensed under the Open "
                                "Government Licence – Canada"),
    ((-31, 45), (34, 72), "Europe terrain data produced using Copernicus data and information "
                          "funded by the European Union - EU-DEM layers"),
    ((-118.5, -86.7), (14.5, 32.8), "Mexico terrain data source: INEGI, Continental relief, 2016"),
    ((165, 179), (-48, -34), "New Zealand terrain data Copyright 2011 Crown copyright (c) Land "
                             "Information New Zealand and the New Zealand Government "
                             "(All rights reserved)"),
    ((4, 31.5), (57.9, 71.3), "Norway terrain data © Kartverket"),
    ((-8.7, 1.9), (49.8, 60.9), "United Kingdom terrain data © Environment Agency copyright "
                                "and/or database right 2015. All rights reserved"),
]


def terrarium_credit(extent):
    """按图幅范围列出 Terrain Tiles 需要的署名（全球源 + 与范围相交的区域源）。"""
    lo0, lo1, la0, la1 = extent
    out = []
    for lon_r, lat_r, text in TERRARIUM_SOURCES:
        if lon_r is None or (lo1 >= lon_r[0] and lo0 <= lon_r[1] and la1 >= lat_r[0]
                             and la0 <= lat_r[1]):
            out.append(text)
    return out


# ================================================================ DEM 数据结构
@dataclass
class DEM:
    """规则网格高程：z[行, 列]，第 0 行在北（上）；extent = (x0, x1, y0, y1)。"""

    z: np.ndarray
    extent: tuple
    geographic: bool = True          # True：经纬度；False：投影坐标（米）
    source: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.z.shape

    def spacing_m(self):
        """像元间距（米）：(dx, dy)。"""
        x0, x1, y0, y1 = self.extent
        ny, nx = self.z.shape
        dx, dy = (x1 - x0) / nx, (y1 - y0) / ny
        if self.geographic:
            phi = math.radians((y0 + y1) / 2)
            return dx * 111320.0 * math.cos(phi), dy * 110574.0
        return dx, dy

    def crop(self, extent):
        x0, x1, y0, y1 = self.extent
        ny, nx = self.z.shape
        c0 = int(np.clip(np.floor((extent[0] - x0) / (x1 - x0) * nx), 0, nx - 1))
        c1 = int(np.clip(np.ceil((extent[1] - x0) / (x1 - x0) * nx), c0 + 1, nx))
        r0 = int(np.clip(np.floor((y1 - extent[3]) / (y1 - y0) * ny), 0, ny - 1))
        r1 = int(np.clip(np.ceil((y1 - extent[2]) / (y1 - y0) * ny), r0 + 1, ny))
        ext = (x0 + c0 * (x1 - x0) / nx, x0 + c1 * (x1 - x0) / nx,
               y1 - r1 * (y1 - y0) / ny, y1 - r0 * (y1 - y0) / ny)
        return DEM(self.z[r0:r1, c0:c1].copy(), ext, self.geographic, self.source, dict(self.meta))

    def coarsen(self, max_px=1200):
        """块平均降采样，使最大边 ≤ max_px（SVG 体积控制）。"""
        ny, nx = self.z.shape
        f = int(math.ceil(max(ny, nx) / max_px))
        if f <= 1:
            return self
        ny2, nx2 = ny // f, nx // f
        z = np.nanmean(self.z[:ny2 * f, :nx2 * f].reshape(ny2, f, nx2, f), axis=(1, 3))
        x0, x1, y0, y1 = self.extent
        ext = (x0, x0 + nx2 * f * (x1 - x0) / nx, y1 - ny2 * f * (y1 - y0) / ny, y1)
        return DEM(z, ext, self.geographic, self.source, dict(self.meta))

    def grid(self):
        """像元中心坐标网格 (X, Y)。"""
        x0, x1, y0, y1 = self.extent
        ny, nx = self.z.shape
        xs = x0 + (np.arange(nx) + 0.5) * (x1 - x0) / nx
        ys = y1 - (np.arange(ny) + 0.5) * (y1 - y0) / ny
        return np.meshgrid(xs, ys)


# ================================================================ 读取
def _from_axes(z, xs, ys, **kw):
    z = np.asarray(z, float)
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if ys[0] < ys[-1]:                       # 南 → 北存储：翻转为北在上
        z, ys = z[::-1], ys[::-1]
    dx = (xs[-1] - xs[0]) / max(len(xs) - 1, 1)
    dy = (ys[0] - ys[-1]) / max(len(ys) - 1, 1)
    ext = (xs[0] - dx / 2, xs[-1] + dx / 2, ys[-1] - dy / 2, ys[0] + dy / 2)
    return DEM(z, ext, **kw)


def sample_dem(name="jacksboro"):
    """matplotlib 自带的真实地形样例。

    "jacksboro"：3″（约 90 m）网格，美国田纳西 Jacksboro 断层一带（matplotlib 未注明原始来源）；
    "topobathy"：约 2′ × 1.3′ 地形 + 水深网格，加拿大温哥华岛与乔治亚海峡一带。"""
    from matplotlib import cbook
    if name == "jacksboro":
        d = cbook.get_sample_data("jacksboro_fault_dem.npz")
        z = np.asarray(d["elevation"], float)
        y_hi, y_lo = max(float(d["ymin"]), float(d["ymax"])), min(float(d["ymin"]), float(d["ymax"]))
        return DEM(z, (float(d["xmin"]), float(d["xmax"]), y_lo, y_hi), True,
                   "matplotlib 自带 3″ DEM 样例（Jacksboro 断层，美国田纳西；原始来源未注明）")
    if name == "topobathy":
        d = cbook.get_sample_data("topobathy.npz")
        lon = np.asarray(d["longitude"], float)
        lon = np.where(lon > 180, lon - 360, lon)
        return _from_axes(d["topo"], lon, d["latitude"], geographic=True,
                          source="matplotlib 自带地形–水深样例（温哥华岛一带）")
    raise ValueError(f"unknown sample {name!r}")


def _read_asc(path):
    head = {}
    with open(path) as f:
        for _ in range(6):
            pos = f.tell()
            line = f.readline()
            k, *v = line.split()
            if k.lower() in ("ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter",
                             "cellsize", "nodata_value"):
                head[k.lower()] = float(v[0])
            else:
                f.seek(pos)
                break
        z = np.loadtxt(f)
    nx, ny, cs = int(head["ncols"]), int(head["nrows"]), head["cellsize"]
    x0 = head.get("xllcorner", head.get("xllcenter", 0) - cs / 2)
    y0 = head.get("yllcorner", head.get("yllcenter", 0) - cs / 2)
    z = z.reshape(ny, nx).astype(float)
    if "nodata_value" in head:
        z[z == head["nodata_value"]] = np.nan
    return z, (x0, x0 + nx * cs, y0, y0 + ny * cs)


def _read_tif(path):
    try:
        import rasterio
        with rasterio.open(path) as src:
            z = src.read(1, masked=True).astype(float).filled(np.nan)
            b = src.bounds
            geo = bool(src.crs.is_geographic) if src.crs else True
            return z, (b.left, b.right, b.bottom, b.top), geo
    except ImportError:
        pass
    import tifffile                         # pip install tifffile
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        z = page.asarray().astype(float)
        tags = page.tags
        scale = tags["ModelPixelScaleTag"].value
        tie = tags["ModelTiepointTag"].value
        nod = tags.get("GDAL_NODATA")
        if nod is not None:
            z[z == float(str(nod.value).strip("\x00"))] = np.nan
        geo, point = True, False
        gk = tags.get("GeoKeyDirectoryTag")
        if gk is not None:
            v = list(gk.value)
            for i in range(4, len(v), 4):
                if v[i] == 1024:
                    geo = v[i + 3] == 2
                if v[i] == 1025:
                    point = v[i + 3] == 2
        ny, nx = z.shape[:2]
        x0 = tie[3] - tie[0] * scale[0] - (scale[0] / 2 if point else 0)
        y1 = tie[4] + tie[1] * scale[1] + (scale[1] / 2 if point else 0)
        return z, (x0, x0 + nx * scale[0], y1 - ny * scale[1], y1), geo


def load_dem(path, extent=None, geographic=None, var=None):
    """读取 DEM 文件 → :class:`DEM`。.npy 需给 extent；其他格式自带地理参照。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".tif", ".tiff"):
        z, e, geo = _read_tif(p)
        dem = DEM(z, e, geo, p.name)
    elif ext == ".asc":
        z, e = _read_asc(p)
        dem = DEM(z, e, True, p.name)
    elif ext == ".npy":
        if extent is None:
            raise ValueError(".npy 需要 extent=(x0, x1, y0, y1)")
        dem = DEM(np.load(p).astype(float), tuple(extent), True, p.name)
    elif ext == ".npz":
        d = np.load(p)
        key = next(k for k in ("elevation", "z", "topo", "data", "dem") if k in d)
        if "longitude" in d and "latitude" in d:
            dem = _from_axes(d[key], d["longitude"], d["latitude"], geographic=True, source=p.name)
        elif "lon" in d and "lat" in d:
            dem = _from_axes(d[key], d["lon"], d["lat"], geographic=True, source=p.name)
        else:
            e = extent or (float(d["xmin"]), float(d["xmax"]),
                           min(float(d["ymin"]), float(d["ymax"])),
                           max(float(d["ymin"]), float(d["ymax"])))
            dem = DEM(np.asarray(d[key], float), tuple(e), True, p.name)
    elif ext in (".nc", ".grd", ".nc4", ".cdf"):
        import xarray as xr                  # pip install xarray netCDF4
        ds = xr.open_dataset(p)
        da = ds[var] if var else next(v for v in ds.data_vars.values() if v.ndim == 2)
        xn = next(n for n in da.dims if n.lower() in ("lon", "longitude", "x"))
        yn = next(n for n in da.dims if n.lower() in ("lat", "latitude", "y"))
        da = da.transpose(yn, xn)
        dem = _from_axes(da.values, da[xn].values, da[yn].values, geographic=True, source=p.name)
    else:
        raise ValueError(f"不支持的 DEM 格式：{ext}")
    if geographic is not None:
        dem.geographic = geographic
    return dem


# ================================================================ 在线：Terrarium 瓦片
def _tile_x(lon, n):
    return (lon + 180.0) / 360.0 * n


def _tile_y(lat, n):
    return (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n


def decode_terrarium(rgb):
    """Terrarium 编码：高程 = R·256 + G + B/256 − 32768（米）。"""
    rgb = np.asarray(rgb, float)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


def _http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "shanhai-atlas/0.1 (+matplotlib)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_terrarium(extent, zoom=None, target_px=1200, cache_dir=None, getter=None,
                    url=TERRARIUM_URL, max_tiles=120, timeout=30, verbose=True):
    """下载并拼接 Terrarium 瓦片，返回经纬度规则网格 DEM（米）。

    zoom 缺省按 target_px 自动选择（z12 ≈ 30 m，z10 ≈ 120 m @ 赤道）。瓦片缓存在
    ``~/.cache/shanhai_atlas/terrarium``；getter(z, x, y) → PNG 字节，可替换为自建镜像。
    """
    from PIL import Image
    lo0, lo1, la0, la1 = extent
    if zoom is None:
        zoom = int(np.clip(math.ceil(math.log2(target_px * 360.0 / ((lo1 - lo0) * 256.0))), 1, 14))
    n = 2 ** zoom
    x0, x1 = int(math.floor(_tile_x(lo0, n))), int(math.floor(_tile_x(lo1, n)))
    y0, y1 = int(math.floor(_tile_y(la1, n))), int(math.floor(_tile_y(la0, n)))
    ntiles = (x1 - x0 + 1) * (y1 - y0 + 1)
    if ntiles > max_tiles:
        raise ValueError(f"需要 {ntiles} 块瓦片（z{zoom}），超过 max_tiles={max_tiles}；请降低 zoom")
    cache = Path(cache_dir or os.environ.get("SHANHAI_TILE_DIR")
                 or Path.home() / ".cache" / "shanhai_atlas" / "terrarium")
    if getter is None:
        def getter(z, x, y):
            f = cache / str(z) / str(x) / f"{y}.png"
            if f.exists():
                return f.read_bytes()
            b = _http_get(url.format(z=z, x=x, y=y), timeout)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b)
            return b
    if verbose:
        print(f"terrarium: z{zoom}, {ntiles} tile(s)")
    M = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            img = Image.open(io.BytesIO(getter(zoom, tx, ty))).convert("RGB")
            M[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = \
                decode_terrarium(np.asarray(img))
    # 目标网格：经度线性；纬度按墨卡托反算后逐行插值（列方向墨卡托与经度同为线性）
    W = max(2, int(round((_tile_x(lo1, n) - _tile_x(lo0, n)) * 256)))
    phi = math.radians((la0 + la1) / 2)
    H = max(2, int(round(W * (la1 - la0) / ((lo1 - lo0) * math.cos(phi)))))
    lons = lo0 + (np.arange(W) + 0.5) * (lo1 - lo0) / W
    lats = la1 - (np.arange(H) + 0.5) * (la1 - la0) / H
    px = np.array([_tile_x(v, n) for v in lons]) * 256 - x0 * 256 - 0.5
    py = np.array([_tile_y(v, n) for v in lats]) * 256 - y0 * 256 - 0.5
    px = np.clip(px, 0, M.shape[1] - 1.001)
    py = np.clip(py, 0, M.shape[0] - 1.001)
    iy, fy = np.floor(py).astype(int), py - np.floor(py)
    rows = M[iy] * (1 - fy)[:, None] + M[iy + 1] * fy[:, None]
    ix, fx = np.floor(px).astype(int), px - np.floor(px)
    z = rows[:, ix] * (1 - fx)[None, :] + rows[:, ix + 1] * fx[None, :]
    return DEM(z, tuple(extent), True, f"AWS Terrain Tiles（Terrarium，z{zoom}）",
               dict(zoom=zoom, tiles=ntiles, credit=terrarium_credit(extent)))


# ================================================================ 渲染
def _gradients(dem, vert_exag=1.0):
    z = np.array(dem.z, float)
    if np.isnan(z).any():
        z = np.where(np.isnan(z), np.nanmean(z), z)
    dx, dy = dem.spacing_m()
    gy, gx = np.gradient(z, dy, dx)          # gy：沿行（向南）；gx：沿列（向东）
    return gx * vert_exag, -gy * vert_exag   # (∂z/∂x 东, ∂z/∂y 北)


def slope_deg(dem, vert_exag=1.0):
    p, q = _gradients(dem, vert_exag)
    return np.degrees(np.arctan(np.hypot(p, q)))


def hillshade(dem, azimuth=315.0, altitude=45.0, vert_exag=1.0, multidirectional=True):
    """山体阴影 ∈ [0, 1]：I = max(0, n̂ · ℓ̂)，n̂ = (−∂z/∂x, −∂z/∂y, 1)/‖·‖。

    multidirectional=True 时按 Mark (1992) 对 225°/270°/315°/360° 四个方位加权：
    w = cos²(坡向 − 方位)，Σw = 2，平地亮度 = sin(高度角)（与单光源一致）。
    """
    p, q = _gradients(dem, vert_exag)
    nrm = np.sqrt(p * p + q * q + 1.0)
    e = math.radians(altitude)

    def lam(az):
        a = math.radians(az)
        return np.clip((-p * math.sin(a) * math.cos(e) - q * math.cos(a) * math.cos(e)
                        + math.sin(e)) / nrm, 0.0, 1.0)

    if not multidirectional:
        return lam(azimuth)
    aspect = np.arctan2(-p, -q)                         # 下坡方向方位角（自北顺时针）
    flat = (p * p + q * q) < 1e-12
    hs = np.zeros_like(p)
    for az in (225.0, 270.0, 315.0, 360.0):
        w = np.cos(aspect - math.radians(az)) ** 2
        w = np.where(flat, 0.5, w)
        hs += w * lam(az)
    return np.clip(hs / 2.0, 0.0, 1.0)


def _cm(c):
    if c is None:
        return None
    if isinstance(c, str):
        c = resolve_cmap(c)
        if isinstance(c, str):
            c = mpl.colormaps[c]
    return c


def shade(dem, cmap="sha.terrain", vmin=None, vmax=None, sea_level=0.0, sea=True,
          sea_cmap="sha.sea", sea_vmin=None, azimuth=315.0, altitude=45.0, vert_exag=1.0,
          multidirectional=True, strength=0.62, sea_strength=0.25, flat_color=None, wash=0.0):
    """分层设色 × 山体阴影 → RGB 数组（行, 列, 3）。

    平地（hs = sin 高度角）保持色带原色；向光坡提亮、背光坡压暗，strength 控制强度。
    sea=True 时低于 sea_level 的像元用水深色带、弱阴影。flat_color 给定时不设色（单色晕渲）。
    wash ∈ [0, 1]：整体向白色淡化，作数据底图时常用 0.3–0.45，让上层数据更突出。
    """
    z = np.array(dem.z, float)
    nan = np.isnan(z)
    zf = np.where(nan, np.nanmin(z), z)
    land = (zf > sea_level) if sea else np.ones_like(zf, bool)
    hs = hillshade(dem, azimuth, altitude, vert_exag, multidirectional)
    hsn = np.clip(hs / math.sin(math.radians(altitude)), 0.0, 1.4)
    rgb = np.zeros(z.shape + (3,))
    if flat_color is not None:
        tint_l = np.broadcast_to(mpl.colors.to_rgb(flat_color), z.shape + (3,))
    else:
        lv = zf[land] if land.any() else zf
        lo = np.percentile(lv, 1) if vmin is None else vmin
        hi = np.percentile(lv, 99.5) if vmax is None else vmax
        tint_l = _cm(cmap)(Normalize(lo, hi, clip=True)(zf))[..., :3]
    f = 1.0 - strength + strength * hsn
    lit = np.where(f[..., None] <= 1.0, tint_l * f[..., None],
                   tint_l + (1.0 - tint_l) * (f[..., None] - 1.0) * 0.9)
    rgb[:] = lit
    if sea and (~land).any():
        sv = zf[~land]
        slo = np.percentile(sv, 1) if sea_vmin is None else sea_vmin
        tint_s = _cm(sea_cmap)(Normalize(slo, sea_level, clip=True)(zf))[..., :3]
        fs = 1.0 - sea_strength + sea_strength * np.clip(hsn, 0, 1.2)
        rgb[~land] = np.clip(tint_s * fs[..., None], 0, 1)[~land]
    rgb[nan] = mpl.colors.to_rgb(C.white)
    if wash:
        rgb = rgb + (1.0 - rgb) * float(wash)
    return np.clip(rgb, 0.0, 1.0)


def draw(ax, dem, rgb=None, z=0.5, interpolation="bilinear", **shade_kw):
    """把 DEM（或已渲染的 rgb）画到坐标轴，保持原有视窗与纵横比。"""
    if rgb is None:
        rgb = shade(dem, **shade_kw)
    xl, yl, asp = ax.get_xlim(), ax.get_ylim(), ax.get_aspect()
    im = ax.imshow(rgb, extent=dem.extent, origin="upper", interpolation=interpolation,
                   zorder=z, aspect="auto")
    if not (xl == (0.0, 1.0) and yl == (0.0, 1.0)):
        ax.set_xlim(xl)
        ax.set_ylim(yl)
    else:
        ax.set_xlim(dem.extent[0], dem.extent[1])
        ax.set_ylim(dem.extent[2], dem.extent[3])
    ax.set_aspect(asp if asp != "auto" else (1.0 / math.cos(math.radians(sum(dem.extent[2:]) / 2))
                                             if dem.geographic else 1.0))
    return im


def sample(dem, lon, lat):
    """双线性插值取样：返回 (lon, lat) 处高程。"""
    x0, x1, y0, y1 = dem.extent
    ny, nx = dem.z.shape
    fx = (np.asarray(lon, float) - x0) / (x1 - x0) * nx - 0.5
    fy = (y1 - np.asarray(lat, float)) / (y1 - y0) * ny - 0.5
    fx, fy = np.clip(fx, 0, nx - 1.001), np.clip(fy, 0, ny - 1.001)
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - ix, fy - iy
    z = dem.z
    return ((1 - tx) * (1 - ty) * z[iy, ix] + tx * (1 - ty) * z[iy, ix + 1]
            + (1 - tx) * ty * z[iy + 1, ix] + tx * ty * z[iy + 1, ix + 1])


def profile(dem, p0, p1, n=400):
    """沿 p0 → p1（经纬度或投影坐标）取剖面：返回 (距离 km, 高程, lon, lat)。"""
    t = np.linspace(0.0, 1.0, n)
    lon = p0[0] + (p1[0] - p0[0]) * t
    lat = p0[1] + (p1[1] - p0[1]) * t
    if dem.geographic:
        phi = math.radians((p0[1] + p1[1]) / 2)
        dx = (p1[0] - p0[0]) * 111.320 * math.cos(phi)
        dy = (p1[1] - p0[1]) * 110.574
    else:
        dx, dy = (p1[0] - p0[0]) / 1000.0, (p1[1] - p0[1]) / 1000.0
    return t * math.hypot(dx, dy), sample(dem, lon, lat), lon, lat


def _blur(z, sigma):
    """可分离高斯平滑（纯 NumPy）。"""
    if sigma <= 0:
        return z
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    zp = np.pad(z, r, mode="edge")
    zp = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, zp)
    zp = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, zp)
    return zp


def _axes_size_in(ax):
    ax.apply_aspect()
    pos = ax.get_position()
    fw, fh = ax.figure.get_size_inches()
    return pos.width * fw, pos.height * fh


def contours(ax, dem, interval=100.0, color=C.ink, lw=0.25, alpha=0.45, index_every=5,
             index_lw=0.5, labels=False, label_size=4.8, z=0.8, smooth=0.8, tol_in=0.003,
             min_len_in=0.05, max_labels=14):
    """等高线：每 index_every 条加粗为计曲线，可选沿线标注（白色描边、随线旋转）。

    先轻度高斯平滑（smooth，像元）→ contourpy 追踪 → RDP 化简（tol_in 英寸）→
    丢弃过短碎线（min_len_in）→ LineCollection 绘制。SVG 体积比直接 ax.contour 小一个量级。
    """
    import contourpy
    from matplotlib.collections import LineCollection
    from .geo import simplify
    zz = np.array(dem.z, float)
    if np.isnan(zz).any():
        zz = np.where(np.isnan(zz), np.nanmean(zz), zz)
    zs = _blur(zz, smooth)
    X, Y = dem.grid()
    gen = contourpy.contour_generator(X, Y, zs, line_type=contourpy.LineType.Separate)
    lo = math.ceil(np.nanmin(zs) / interval) * interval
    hi = math.floor(np.nanmax(zs) / interval) * interval
    levels = np.arange(lo, hi + interval / 2, interval)
    w_in, h_in = _axes_size_in(ax)
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    sx, sy = abs(x1 - x0) / w_in, abs(y1 - y0) / h_in            # 每英寸对应的数据单位
    reg, idx, cand = [], [], []
    for lev in levels:
        is_idx = np.isclose(np.mod(lev, interval * index_every), 0) or \
            np.isclose(np.mod(lev, interval * index_every), interval * index_every)
        for seg in gen.lines(lev):
            seg = np.asarray(seg, float)
            if len(seg) < 2:
                continue
            L = np.hypot(np.diff(seg[:, 0]) / sx, np.diff(seg[:, 1]) / sy).sum()
            if L < min_len_in:
                continue
            seg = simplify(seg, tol_in, scale=(sx, sy))
            (idx if is_idx else reg).append(seg)
            if is_idx and labels:
                cand.append((L, lev, seg))
    if reg:
        ax.add_collection(LineCollection(reg, colors=[color], linewidths=lw, alpha=alpha,
                                         zorder=z, capstyle="round"))
    if idx:
        ax.add_collection(LineCollection(idx, colors=[color], linewidths=index_lw,
                                         alpha=min(1.0, alpha * 1.5), zorder=z, capstyle="round"))
    if labels and cand:
        import matplotlib.patheffects as pe
        halo = [pe.withStroke(linewidth=1.6, foreground="white")]
        placed = []
        for L, lev, seg in sorted(cand, key=lambda t: -t[0]):
            if len(placed) >= max_labels:
                break
            k = len(seg) // 2
            px, py = seg[k]
            if any(math.hypot((px - qx) / sx, (py - qy) / sy) < 0.45 for qx, qy in placed):
                continue
            a, b = seg[max(k - 2, 0)], seg[min(k + 2, len(seg) - 1)]
            p0, p1 = ax.transData.transform([a, b])
            ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            ang = ang + 180 if ang > 90 else (ang - 180 if ang < -90 else ang)
            ax.text(px, py, f"{lev:.0f}", fontsize=label_size, color=color, alpha=0.9,
                    rotation=ang, rotation_mode="anchor", ha="center", va="center",
                    zorder=z + 0.05, path_effects=halo)
            placed.append((px, py))
    return len(reg) + len(idx)
