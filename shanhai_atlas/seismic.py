# -*- coding: utf-8 -*-
"""区域地震学常用流程：震源目录、震中图、剖面、震级–频度与震源机制。

目录采用常见正深度（km）约定；区域剖面用局部等距圆柱近似，适合小范围图件。
震源机制球使用 ObsPy 的成熟实现（可选依赖 ``pip install shanhai-atlas[seismo]``），不复制其算法。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from matplotlib import colors as mpl_colors
from matplotlib.lines import Line2D

from .charts import style_axes
from .theme import C, CMAPS, resolve_cmap

USGS_COMCAT_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USGS_CITATION = "U.S. Geological Survey, Earthquake Catalog (ComCat)"


@dataclass
class EventCatalog:
    """简洁、可复现的震源目录结构；经纬度以度计、深度以 km 计且向下为正。"""

    lon: np.ndarray
    lat: np.ndarray
    depth_km: np.ndarray | None = None
    magnitude: np.ndarray | None = None
    time: np.ndarray | None = None
    event_id: np.ndarray | None = None
    source: str = "user-provided catalog"
    citation: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.lon = np.asarray(self.lon, dtype=float).reshape(-1)
        self.lat = np.asarray(self.lat, dtype=float).reshape(-1)
        n = len(self.lon)
        if len(self.lat) != n:
            raise ValueError("lon 和 lat 长度必须一致")
        if not np.isfinite(self.lon).all() or not np.isfinite(self.lat).all():
            raise ValueError("震源目录的经纬度不能缺失或为非有限值")
        if np.any(np.abs(self.lon) > 360) or np.any((self.lat < -90) | (self.lat > 90)):
            raise ValueError("经度需在 [-360, 360]、纬度需在 [-90, 90] 范围内")
        self.depth_km = self._numeric_column(self.depth_km, n, "depth_km")
        self.magnitude = self._numeric_column(self.magnitude, n, "magnitude")
        self.time = self._text_column(self.time, n, "time")
        self.event_id = self._text_column(self.event_id, n, "event_id")
        self.metadata = dict(self.metadata or {})

    @staticmethod
    def _numeric_column(values, n, name):
        if values is None:
            return np.full(n, np.nan, dtype=float)
        arr = np.asarray(values, dtype=float).reshape(-1)
        if len(arr) != n:
            raise ValueError(f"{name} 长度必须等于事件数 {n}")
        return arr

    @staticmethod
    def _text_column(values, n, name):
        if values is None:
            return None
        arr = np.asarray(values, dtype=object).reshape(-1)
        if len(arr) != n:
            raise ValueError(f"{name} 长度必须等于事件数 {n}")
        return arr

    def __len__(self):
        return len(self.lon)

    @property
    def longitude(self):
        return self.lon

    @property
    def latitude(self):
        return self.lat

    @property
    def mag(self):
        return self.magnitude

    def to_csv(self, path):
        """写出通用目录 CSV，并写 ``<文件名>.meta.json`` 保留查询、来源和引用。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("event_id", "time", "longitude", "latitude", "depth_km", "magnitude"))
            for i in range(len(self)):
                writer.writerow((
                    self._text_at(self.event_id, i), self._text_at(self.time, i),
                    self._number_at(self.lon[i]), self._number_at(self.lat[i]),
                    self._number_at(self.depth_km[i]), self._number_at(self.magnitude[i]),
                ))
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        meta_path.write_text(json.dumps({
            "source": self.source,
            "citation": self.citation,
            "metadata": self.metadata,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _text_at(values, i):
        return "" if values is None or values[i] is None else str(values[i])

    @staticmethod
    def _number_at(value):
        return "" if not np.isfinite(value) else f"{float(value):.10g}"


_COLUMN_ALIASES = {
    "lon": ("longitude", "lon", "long", "longitude_deg", "x"),
    "lat": ("latitude", "lat", "latitude_deg", "y"),
    "depth_km": ("depth_km", "depthkm", "depth", "dep", "z"),
    "magnitude": ("magnitude", "mag", "mw", "ml", "mb", "ms"),
    "time": ("time", "time_utc", "origin_time", "datetime", "timestamp", "date"),
    "event_id": ("event_id", "eventid", "id", "publicid", "resource_id"),
}


def _norm_name(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _as_float(value, *, row, field_name, required=False):
    text = "" if value is None else str(value).strip()
    if not text:
        if required:
            raise ValueError(f"CSV 第 {row} 行缺少必需字段 {field_name!r}")
        return np.nan
    try:
        return float(text)
    except ValueError as exc:
        if required:
            raise ValueError(f"CSV 第 {row} 行字段 {field_name!r} 不是数字：{text!r}") from exc
        return np.nan


def _catalog_from_csv_text(text, *, columns=None, source="CSV catalog", citation="", metadata=None,
                           delimiter=","):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("目录 CSV 为空或缺少表头")
    names = {_norm_name(name): name for name in reader.fieldnames}
    columns = dict(columns or {})
    selected = {}
    for field_name, aliases in _COLUMN_ALIASES.items():
        explicit = columns.get(field_name)
        if explicit is not None:
            key = _norm_name(explicit)
            if key not in names:
                raise ValueError(f"找不到 {field_name!r} 对应列 {explicit!r}; CSV 列为 {reader.fieldnames}")
            selected[field_name] = names[key]
            continue
        selected[field_name] = next((names[_norm_name(a)] for a in aliases
                                     if _norm_name(a) in names), None)
    missing = [k for k in ("lon", "lat") if selected[k] is None]
    if missing:
        raise ValueError(f"目录 CSV 缺少必需列 {missing}; 可识别列名：{reader.fieldnames}")

    out = {k: [] for k in _COLUMN_ALIASES}
    for row_number, row in enumerate(reader, start=2):
        for field_name in ("lon", "lat", "depth_km", "magnitude"):
            col = selected[field_name]
            out[field_name].append(_as_float(row.get(col) if col else None, row=row_number,
                                              field_name=col or field_name,
                                              required=field_name in ("lon", "lat")))
        for field_name in ("time", "event_id"):
            col = selected[field_name]
            out[field_name].append(str(row.get(col, "") or "").strip() if col else "")
    return EventCatalog(
        lon=out["lon"], lat=out["lat"], depth_km=out["depth_km"], magnitude=out["magnitude"],
        time=out["time"] if selected["time"] else None,
        event_id=out["event_id"] if selected["event_id"] else None,
        source=source, citation=citation, metadata=metadata or {},
    )


def read_catalog(path, *, columns=None, delimiter=None, source=None, citation=""):
    """读取带表头的 CSV / TSV 震源目录。

    自动识别 ``lon/longitude``、``lat/latitude``、``depth/depth_km``、``mag/magnitude``、
    时间和事件 ID 常用列名。其他格式可用 ``columns={"lon": "xcoord", ...}`` 映射。
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    delimiter = delimiter or ("\t" if path.suffix.lower() in (".tsv", ".tab") else ",")
    if len(delimiter) != 1:
        raise ValueError("delimiter 必须是单个字符")
    return _catalog_from_csv_text(text, columns=columns, source=source or path.name,
                                  citation=citation, delimiter=delimiter)


def _download(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "shanhai-atlas/0.1 (+scientific figure toolkit)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_usgs_catalog(extent, starttime, endtime, *, min_magnitude=None, max_magnitude=None,
                       min_depth_km=None, max_depth_km=None, cache_dir=None, use_cache=True,
                       timeout=30, fetcher=None):
    """从 USGS ComCat 下载区域震源目录（CSV），离线缓存并保留引用信息。

    ``extent=(W,E,S,N)``，区域应为单个常规经度范围（不跨 ±180°）。可用 ``fetcher(url)``
    注入测试或自定义镜像；缺省请求 USGS FDSN Event Web Service。返回 :class:`EventCatalog`。
    """
    west, east, south, north = map(float, extent)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("extent 应为 (W,E,S,N)，且 -180≤W<E≤180、-90≤S<N≤90；不支持跨日期变更线范围")
    if not starttime or not endtime:
        raise ValueError("USGS 查询必须指定 starttime 和 endtime")
    params = {
        "format": "csv", "starttime": str(starttime), "endtime": str(endtime),
        "minlongitude": west, "maxlongitude": east,
        "minlatitude": south, "maxlatitude": north, "orderby": "time-asc",
    }
    for key, value in (("minmagnitude", min_magnitude), ("maxmagnitude", max_magnitude),
                       ("mindepth", min_depth_km), ("maxdepth", max_depth_km)):
        if value is not None:
            params[key] = float(value)
    query = urllib.parse.urlencode(params)
    url = f"{USGS_COMCAT_URL}?{query}"
    cache = Path(cache_dir or Path.home() / ".cache" / "shanhai_atlas" / "comcat")
    cache_path = cache / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:20] + ".csv")
    if use_cache and cache_path.exists():
        payload = cache_path.read_bytes()
        cached = True
    else:
        payload = (fetcher(url) if fetcher is not None else _download(url, timeout))
        cached = False
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if use_cache:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(payload)
    queried = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = {"url": url, "query": params, "retrieved_utc": queried, "cache_hit": cached}
    try:
        return _catalog_from_csv_text(
            payload.decode("utf-8-sig"), source="USGS ComCat", citation=f"{USGS_CITATION}; queried {queried}.",
            metadata=metadata,
        )
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise ValueError(f"无法解析 USGS 返回的目录 CSV ({url}): {exc}") from exc


def magnitude_sizes(magnitudes, size_range=(10.0, 82.0), magnitude_range=None, levels=8):
    """把震级映射为可读、分档的散点面积（pt²）；仅作视觉编码，不表示物理面积。"""
    mags = np.asarray(magnitudes, dtype=float)
    lo_size, hi_size = map(float, size_range)
    if lo_size < 0 or hi_size < lo_size or levels < 1:
        raise ValueError("size_range 需非负递增，levels ≥ 1")
    finite = np.isfinite(mags)
    if not finite.any() or levels == 1 or hi_size == lo_size:
        return np.full(mags.shape, lo_size, dtype=float)
    lo, hi = (np.nanmin(mags[finite]), np.nanmax(mags[finite])) if magnitude_range is None \
        else tuple(map(float, magnitude_range))
    if hi <= lo:
        return np.full(mags.shape, (lo_size + hi_size) / 2.0, dtype=float)
    scaled = np.clip((np.where(finite, mags, lo) - lo) / (hi - lo), 0.0, 1.0)
    index = np.rint(scaled * (levels - 1))
    return lo_size + index * (hi_size - lo_size) / (levels - 1)


def plot_events(ax, catalog, *, color_by="depth_km", cmap=None, size_range=(10, 82),
                magnitude_range=None, levels=8, edgecolor="white", linewidth=0.22,
                alpha=0.9, zorder=4, **scatter_kw):
    """绘制震中；默认颜色表示深度、点面积表示震级。返回可直接传给 ``fig.colorbar`` 的对象。"""
    if not isinstance(catalog, EventCatalog):
        raise TypeError("catalog 必须是 EventCatalog；用 read_catalog() 读取 CSV")
    sizes = magnitude_sizes(catalog.magnitude, size_range, magnitude_range, levels)
    coords = np.isfinite(catalog.lon) & np.isfinite(catalog.lat)
    if color_by is None:
        return ax.scatter(catalog.lon[coords], catalog.lat[coords], s=sizes[coords],
                          color=C.blue, edgecolors=edgecolor, linewidths=linewidth,
                          alpha=alpha, zorder=zorder, **scatter_kw)
    if color_by not in ("depth_km", "magnitude"):
        raise ValueError(f"未知 color_by={color_by!r}; 可用 depth_km、magnitude 或 None")
    values = np.asarray(getattr(catalog, color_by), dtype=float)
    if cmap is None:
        cmap = CMAPS.depth if color_by == "depth_km" else CMAPS.gold
    if isinstance(cmap, str):
        cmap = resolve_cmap(cmap)
        if isinstance(cmap, str):
            import matplotlib as mpl
            cmap = mpl.colormaps[cmap]
    cmap = cmap.with_extremes(bad=C.gray_lite)
    finite = values[np.isfinite(values) & coords]
    vmin, vmax = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
    if math.isclose(vmin, vmax):
        pad = max(abs(vmin) * 0.01, 0.5)
        vmin, vmax = vmin - pad, vmax + pad
    norm = mpl_colors.Normalize(vmin=vmin, vmax=vmax)
    c = np.ma.masked_invalid(values[coords])
    return ax.scatter(catalog.lon[coords], catalog.lat[coords], c=c, s=sizes[coords],
                      cmap=cmap, norm=norm, edgecolors=edgecolor, linewidths=linewidth,
                      alpha=alpha, zorder=zorder, **scatter_kw)


def magnitude_legend(ax, magnitudes=(2, 3, 4), *, magnitude_range=(1.0, 6.0),
                     size_range=(10, 82), levels=8, loc="lower left", color=C.navy,
                     title="震级", **legend_kw):
    """添加与 ``plot_events`` 对应的离散震级图例。"""
    sizes = magnitude_sizes(magnitudes, size_range, magnitude_range, levels)
    handles = [Line2D([], [], linestyle="", marker="o", markersize=math.sqrt(float(s)),
                      markerfacecolor="white", markeredgecolor=color, markeredgewidth=0.7,
                      label=f"M {m:g}") for m, s in zip(magnitudes, sizes)]
    legend_kw.setdefault("frameon", False)
    legend_kw.setdefault("labelspacing", 0.7)
    legend_kw.setdefault("handletextpad", 0.6)
    return ax.legend(handles=handles, title=title, loc=loc, **legend_kw)


@dataclass
class CrossSectionProjection:
    """剖面投影结果：沿线距离、垂线偏移（均 km）及剖面总长。"""

    along_km: np.ndarray
    offset_km: np.ndarray
    length_km: float


def project_cross_section(lon, lat, start, end):
    """把区域震中投影到 A→B 剖面：返回沿线距离、带符号垂线偏移和线长（km）。

    使用剖面中心纬度的局部等距圆柱近似；适用于区域尺度，不用于全球或跨日期变更线分析。
    偏移正号为沿 A→B 方向的左侧。
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if lon.shape != lat.shape:
        raise ValueError("lon 和 lat 的形状必须一致")
    a_lon, a_lat = map(float, start)
    b_lon, b_lat = map(float, end)
    if a_lon == b_lon and a_lat == b_lat:
        raise ValueError("剖面起点和终点不能相同")
    lat0 = math.radians((a_lat + b_lat) / 2.0)
    km_lon = 111.320 * math.cos(lat0)
    km_lat = 110.574
    # 将经度就近展开到起点附近，避免小区域中 179.9° 与 -179.9° 的差值错误。
    lon_a = a_lon
    lon_b = a_lon + ((b_lon - a_lon + 180.0) % 360.0 - 180.0)
    lon_p = a_lon + ((lon - a_lon + 180.0) % 360.0 - 180.0)
    a = np.array([0.0, 0.0])
    b = np.array([(lon_b - lon_a) * km_lon, (b_lat - a_lat) * km_lat])
    p = np.stack([(lon_p - lon_a) * km_lon, (lat - a_lat) * km_lat], axis=-1)
    vector = b - a
    length = float(np.hypot(*vector))
    unit = vector / length
    relative = p - a
    along = relative @ unit
    left = np.array([-unit[1], unit[0]])
    offset = relative @ left
    return CrossSectionProjection(along, offset, length)


def plot_cross_section(ax, catalog, start, end, *, half_width_km=5.0,
                       depth_limits_km=None, color_by="magnitude", cmap=None,
                       size_range=(10, 78), magnitude_range=None, levels=8,
                       grid=True, zorder=3):
    """画正深度向下的地震剖面；只显示 A–B 范围内、距剖面不超过 ``half_width_km`` 的事件。

    返回含 ``selected`` 布尔掩码、投影距离/偏移和散点对象的 :class:`CrossSectionResult`。
    """
    if half_width_km < 0:
        raise ValueError("half_width_km 必须非负")
    proj = project_cross_section(catalog.lon, catalog.lat, start, end)
    selected = ((proj.along_km >= 0) & (proj.along_km <= proj.length_km)
                & (np.abs(proj.offset_km) <= half_width_km)
                & np.isfinite(catalog.depth_km))
    sizes = magnitude_sizes(catalog.magnitude, size_range, magnitude_range, levels)
    if color_by is None:
        artist = ax.scatter(proj.along_km[selected], catalog.depth_km[selected], s=sizes[selected],
                            color=C.blue, edgecolors="white", linewidths=0.2, zorder=zorder)
    else:
        if color_by not in ("depth_km", "magnitude"):
            raise ValueError(f"未知 color_by={color_by!r}; 可用 depth_km、magnitude 或 None")
        values = np.asarray(getattr(catalog, color_by), dtype=float)[selected]
        if cmap is None:
            cmap = CMAPS.depth if color_by == "depth_km" else CMAPS.gold
        if isinstance(cmap, str):
            import matplotlib as mpl
            cmap = resolve_cmap(cmap)
            if isinstance(cmap, str):
                cmap = mpl.colormaps[cmap]
        good = np.isfinite(values)
        artist = ax.scatter(proj.along_km[selected][good], catalog.depth_km[selected][good],
                            c=values[good], s=sizes[selected][good], cmap=cmap,
                            edgecolors="white", linewidths=0.2, zorder=zorder)
        if (~good).any():
            ax.scatter(proj.along_km[selected][~good], catalog.depth_km[selected][~good],
                       s=sizes[selected][~good], color=C.gray_lite, edgecolors="white",
                       linewidths=0.2, zorder=zorder)
    ax.set_xlim(0, proj.length_km)
    if depth_limits_km is None:
        finite_depth = catalog.depth_km[np.isfinite(catalog.depth_km)]
        bottom = max(float(finite_depth.max()) * 1.05, 1.0) if finite_depth.size else 1.0
        depth_limits_km = (0.0, bottom)
    top, bottom = map(float, depth_limits_km)
    if bottom <= top:
        raise ValueError("depth_limits_km 应为 (浅, 深)，且深度上限大于下限")
    ax.set_ylim(bottom, top)
    ax.set_xlabel("沿剖面距离 (km)")
    ax.set_ylabel("深度 (km)")
    style_axes(ax, grid="both" if grid else None)
    return CrossSectionResult(proj, selected, artist)


@dataclass
class CrossSectionResult:
    projection: CrossSectionProjection
    selected: np.ndarray
    artist: object

    @property
    def n_selected(self):
        return int(self.selected.sum())


@dataclass
class MFDResult:
    """震级–频度计算结果（Mc 阈值、Aki 极大似然 b 值和离散频度）。"""

    mc: float
    b_value: float
    sigma_b: float
    n_complete: int
    bin_edges: np.ndarray
    counts: np.ndarray
    cumulative: np.ndarray
    bin_width: float


def estimate_mc_max_curvature(magnitudes, bin_width=0.1, correction=0.2):
    """最大曲率法估计 Mc，可选固定 +0.2 修正；不替代用户对目录完整性的判断。

    此方法实现 Woessner & Wiemer (2005) 常见的 max-curvature + correction 基线。
    """
    mags = np.asarray(magnitudes, dtype=float)
    mags = mags[np.isfinite(mags)]
    if mags.size == 0 or bin_width <= 0:
        raise ValueError("需要非空震级和正的 bin_width")
    edges = np.arange(np.floor(mags.min() / bin_width) * bin_width,
                      np.ceil(mags.max() / bin_width) * bin_width + bin_width * 1.01,
                      bin_width)
    if len(edges) < 2:
        edges = np.array([mags.min() - bin_width / 2, mags.min() + bin_width / 2])
    counts, _ = np.histogram(mags, bins=edges)
    return float(edges[int(np.argmax(counts))] + bin_width / 2 + correction)


def aki_b_value(magnitudes, mc, magnitude_bin=0.1):
    """Aki (1965) b 值极大似然估计；返回 ``(b, b/√N, N)``。

    ``magnitude_bin`` 是震级量化间隔，结果对 Mc 和目录完整性敏感；本函数不自动选择物理合理的 Mc。
    """
    mags = np.asarray(magnitudes, dtype=float)
    mags = mags[np.isfinite(mags) & (mags >= float(mc) - 1e-10)]
    if magnitude_bin <= 0 or len(mags) < 2:
        raise ValueError("Aki b 值估计至少需要 2 个完整事件，且 magnitude_bin > 0")
    denominator = float(mags.mean() - (float(mc) - float(magnitude_bin) / 2.0))
    if denominator <= 0:
        raise ValueError("无法估计 b 值：完整事件均值不高于修正后的 Mc")
    b = math.log10(math.e) / denominator
    return float(b), float(b / math.sqrt(len(mags))), int(len(mags))


def plot_magnitude_frequency(ax, magnitudes, *, mc=None, bin_width=0.1, mc_correction=0.2,
                             magnitude_bin=0.01, color=C.navy, bar_color=C.gold_pale,
                             fit_color=C.clay, annotate=True, grid=True):
    """绘制震级–频度图：直方图 + 累积 N(≥M) + Aki b 值拟合；返回 :class:`MFDResult`。

    未显式给 ``mc`` 时使用最大曲率法 + ``mc_correction``（默认 0.2）。科研终稿应核实目录完整性，
    并在图注标明 Mc 方法、震级量化间隔和所用事件数。
    """
    mags = np.asarray(magnitudes, dtype=float)
    mags = mags[np.isfinite(mags)]
    if mags.size < 2 or bin_width <= 0:
        raise ValueError("震级–频度图至少需要 2 个有限震级和正的 bin_width")
    if mc is None:
        mc = estimate_mc_max_curvature(mags, bin_width, mc_correction)
    b, sigma_b, n_complete = aki_b_value(mags, mc, magnitude_bin)
    lo = np.floor(mags.min() / bin_width) * bin_width
    hi = np.ceil(mags.max() / bin_width) * bin_width + bin_width
    edges = np.arange(lo, hi + bin_width * 0.5, bin_width)
    if len(edges) < 2:
        edges = np.array([lo, lo + bin_width])
    counts, _ = np.histogram(mags, bins=edges)
    cumulative = np.array([np.count_nonzero(mags >= edge - 1e-10) for edge in edges[:-1]])
    centers = (edges[:-1] + edges[1:]) / 2.0
    ax.bar(centers, counts, width=bin_width * 0.82, color=bar_color, edgecolor="none", zorder=2)
    nz = cumulative > 0
    ax.scatter(centers[nz], cumulative[nz], s=9, color=color, edgecolors="white",
               linewidths=0.25, zorder=4)
    fit_x = np.linspace(max(float(mc), float(mags.min())), float(mags.max()), 80)
    fit_y = n_complete * 10.0 ** (-b * (fit_x - float(mc)))
    ax.plot(fit_x, fit_y, color=fit_color, lw=0.9, zorder=3)
    ax.axvline(mc, color=C.gray_lite, lw=0.65, ls=(0, (2.2, 1.6)), zorder=1)
    ax.set_yscale("log")
    ax.set_xlabel("震级 M")
    ax.set_ylabel("事件数")
    style_axes(ax, grid="y" if grid else None)
    if annotate:
        ax.text(0.98, 0.97, f"Mc = {mc:.2f}\nb = {b:.2f} ± {sigma_b:.2f}\nN = {n_complete}",
                transform=ax.transAxes, ha="right", va="top", fontsize=6.2,
                color=C.ink, bbox=dict(boxstyle="round,pad=0.24", fc="white", ec=C.line, lw=0.45))
    return MFDResult(float(mc), b, sigma_b, n_complete, edges, counts, cumulative, float(bin_width))


def focal_mechanism(ax, lon, lat, strike, dip, rake, *, width_km=10.0, facecolor=C.navy,
                    bgcolor="white", edgecolor=C.navy, linewidth=0.55, zorder=8, size=120):
    """在经纬度坐标轴上绘制单个震源机制球（Aki–Richards SDR 约定）。

    由可选依赖 ObsPy 绘制；球宽以 km 给定并分别换算为经、纬度宽度，适用于 GeoMap 区域图。
    ``strike`` 顺时针自北、``dip`` 向下、``rake`` 按 Aki–Richards 约定。返回 ObsPy PatchCollection。
    """
    if width_km <= 0:
        raise ValueError("width_km 必须为正")
    if not (0 <= float(dip) <= 90):
        raise ValueError("dip 应在 0–90°")
    try:
        from obspy.imaging.beachball import beach
    except ImportError as exc:
        raise ImportError("震源机制图需要可选依赖 ObsPy：pip install 'shanhai-atlas[seismo]'") from exc
    phi = math.radians(float(lat))
    km_lon = 111.320 * max(math.cos(phi), 1e-6)
    width = (width_km / km_lon, width_km / 110.574)
    collection = beach([float(strike) % 360.0, float(dip), float(rake)],
                       xy=(float(lon), float(lat)), width=width, size=size,
                       facecolor=facecolor, bgcolor=bgcolor, edgecolor=edgecolor,
                       linewidth=linewidth, zorder=zorder)
    ax.add_collection(collection, autolim=False)
    return collection


def focal_mechanisms(ax, lon, lat, strike, dip, rake, *, width_km=10.0, **kwargs):
    """批量绘制 SDR 震源机制，返回 ObsPy collection 列表。"""
    lon, lat, strike, dip, rake = np.broadcast_arrays(
        np.asarray(lon, float), np.asarray(lat, float), np.asarray(strike, float),
        np.asarray(dip, float), np.asarray(rake, float))
    return [focal_mechanism(ax, x, y, s, d, r, width_km=width_km, **kwargs)
            for x, y, s, d, r in zip(lon.flat, lat.flat, strike.flat, dip.flat, rake.flat)]
