# -*- coding: utf-8 -*-
"""示例用合成数据发生器 —— 完全离线、固定随机种子、绝不冒充观测目录。

⚠ 本模块生成的经纬度、深度、震级、断层迹线与台站位置**全部是随机示意数据**。
   它们不是任何机构发布的地震目录，不是观测结果，不含任何真实台站坐标，
   不能用于任何科学结论。仅用于演示 API、版式与导出流程。

真实研究请使用自己已获授权的数据：

    from shanhai_atlas import read_catalog
    cat = read_catalog("your_authorized_catalog.csv")
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np

from shanhai_atlas.seismic import EventCatalog

SEED = 20261113
#: 海外示意区域（新西兰 Kaikōura 近海）。示例不加载任何行政边界 / 国界数据。
EXTENT = (172.30, 174.00, -43.10, -42.10)
SOURCE = "SYNTHETIC demo data — not observations"


def catalog(n: int = 420, seed: int = SEED) -> EventCatalog:
    """沿一条假想 NE 向断裂带撒点，返回 EventCatalog。"""
    rng = np.random.default_rng(seed)
    t = rng.uniform(0.0, 1.0, n)
    lon = 172.52 + 1.18 * t + rng.normal(0, 0.040, n)
    lat = -42.96 + 0.56 * t + rng.normal(0, 0.032, n)
    depth_km = np.clip(3.0 + 26.0 * t + rng.normal(0, 2.8, n), 0.5, 40.0)
    magnitude = np.clip(1.6 + rng.exponential(0.78, n), 1.5, 6.4)
    t0 = dt.date(2016, 11, 13)
    days = rng.uniform(0, 60, n)
    time = np.array([(t0 + dt.timedelta(days=float(d))).isoformat() for d in days], dtype=str)
    return EventCatalog(
        lon=lon, lat=lat, depth_km=depth_km, magnitude=magnitude, time=time,
        source=SOURCE, metadata={"synthetic": True, "seed": seed},
    )


def write_csv(path, n: int = 420, seed: int = SEED) -> Path:
    """写出示意 CSV，用于演示 ``read_catalog()`` 的列名自动识别。"""
    c = catalog(n, seed)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        f.write("lon,lat,depth_km,magnitude,time\n")
        for lo, la, de, ma, ti in zip(c.lon, c.lat, c.depth_km, c.magnitude, c.time):
            f.write(f"{lo:.5f},{la:.5f},{de:.2f},{ma:.2f},{ti}\n")
    return p


def fault_traces():
    """三条示意断层迹线：[(lon 数组, lat 数组), ...]。"""
    x = np.linspace(172.55, 173.75, 60)
    u = (x - 172.55) / 1.2
    return [
        (x, -42.95 + 0.48 * u + 0.012 * np.sin(6 * x)),
        (x, -42.86 + 0.44 * u + 0.018 * np.cos(5 * x)),
        (x, -42.62 + 0.30 * u),
    ]


def stations(n: int = 9, seed: int = SEED + 1):
    """示意台站点位（非真实台站）。"""
    rng = np.random.default_rng(seed)
    return (rng.uniform(172.45, 173.85, n), rng.uniform(-43.00, -42.20, n))
