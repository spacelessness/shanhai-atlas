# -*- coding: utf-8 -*-
"""命令行：python -m shanhai_atlas <doctor | fonts | preview | gallery | fetch-usgs>

    doctor                         环境自检：版本、字体、可选依赖、海岸线数据
    fonts [--dest DIR]             下载默认字体（思源黑体 Noto Sans SC + Source Serif 4，SIL OFL）
    preview PPTX [DIR]             PPT 版面预览（每页一张 PNG + 文本溢出报告；无需 Office）
    gallery [--out DIR]            运行 examples/ 全部示例（仓库内使用）
    fetch-usgs --extent W E S N    下载 USGS ComCat 区域震源目录 CSV，并保存来源元数据
"""

from __future__ import annotations

import argparse
import importlib
import platform
import subprocess
import sys
from pathlib import Path


def doctor():
    import matplotlib
    import numpy
    from . import __version__, fonts, geo
    print(f"Shanhai Atlas {__version__} · Python {platform.python_version()} · numpy {numpy.__version__}"
          f" · matplotlib {matplotlib.__version__}")
    try:
        f = fonts.setup(quiet=True)
        print(f"  fonts   CJK={f.cjk} | serif={f.serif} | mono={f.mono}"
              + ("" if f.cjk == "Noto Sans SC" else "   （推荐：python -m shanhai_atlas fonts）"))
    except RuntimeError as e:
        print("  fonts   ✗", e)
    for mod, pip_name, use in (("pptx", "python-pptx", "PPT 生成"),
                               ("tifffile", "tifffile", "GeoTIFF 读取"),
                               ("xarray", "shanhai-atlas[netcdf]", "NetCDF / GMT grd 读取"),
                               ("shapefile", "shanhai-atlas[shapefile]", "Shapefile 叠加"),
                               ("obspy", "shanhai-atlas[seismo]", "震源机制球")):
        try:
            m = importlib.import_module(mod)
            print(f"  ✓ {mod:<10} {getattr(m, '__version__', '')}  {use}")
        except ImportError:
            print(f"  · {mod:<10} 未安装（pip install {pip_name}）  {use}")
    for res, pkg in (("f", "basemap-data-hires"), ("h", "basemap-data-hires"),
                     ("i", "basemap-data")):
        ok = geo.gshhs_available(res)
        print(f"  {'✓' if ok else '·'} GSHHG {res}   " + ("可用" if ok else f"未安装（pip install {pkg}）"))
    print(f"  font cache: {fonts.font_cache_dir()}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m shanhai_atlas", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("doctor")
    f = sub.add_parser("fonts")
    f.add_argument("--dest")
    p = sub.add_parser("preview")
    p.add_argument("pptx")
    p.add_argument("out", nargs="?")
    p.add_argument("--dpi", type=int, default=110)
    g = sub.add_parser("gallery")
    g.add_argument("--out")
    u = sub.add_parser("fetch-usgs", help="从 USGS ComCat 下载一个区域的震源目录 CSV")
    u.add_argument("--extent", nargs=4, type=float, required=True, metavar=("W", "E", "S", "N"))
    u.add_argument("--start", required=True, help="起始时间，如 2016-11-13")
    u.add_argument("--end", required=True, help="结束时间，如 2016-12-31")
    u.add_argument("--min-magnitude", type=float)
    u.add_argument("--max-magnitude", type=float)
    u.add_argument("--min-depth", type=float)
    u.add_argument("--max-depth", type=float)
    u.add_argument("--out", required=True, help="输出 CSV 路径；旁边会生成 .meta.json 来源记录")
    u.add_argument("--cache-dir", help="缓存目录（默认 ~/.cache/shanhai_atlas/comcat）")
    u.add_argument("--no-cache", action="store_true", help="本次查询不读写本地缓存")
    a = ap.parse_args(argv)
    if a.cmd == "doctor":
        doctor()
    elif a.cmd == "fonts":
        from .fonts import fetch_fonts
        fetch_fonts(a.dest)
    elif a.cmd == "preview":
        from . import fonts
        from .ppt_preview import preview
        fonts.setup(quiet=True)
        out = a.out or str(Path(a.pptx).with_suffix("")) + "_preview"
        rep = preview(a.pptx, out, a.dpi)
        print(f"preview → {out}")
        for page, items in rep.items():
            for name, need, have in items:
                print(f"  [overflow] p{page:02d} {name}: 需要 {need} in > 文本框 {have} in")
        return 1 if rep else 0
    elif a.cmd == "fetch-usgs":
        from .seismic import fetch_usgs_catalog
        try:
            catalog = fetch_usgs_catalog(
                a.extent, a.start, a.end, min_magnitude=a.min_magnitude,
                max_magnitude=a.max_magnitude, min_depth_km=a.min_depth,
                max_depth_km=a.max_depth, cache_dir=a.cache_dir, use_cache=not a.no_cache,
            )
            catalog.to_csv(a.out)
        except Exception as exc:
            print(f"USGS ComCat 查询失败：{exc}", file=sys.stderr)
            return 1
        print(f"USGS ComCat: {len(catalog)} events → {a.out}")
        print(f"metadata → {a.out}.meta.json")
    elif a.cmd == "gallery":
        ex = Path(__file__).resolve().parents[1] / "examples"
        if not ex.is_dir():
            print("未找到 examples/（gallery 仅在仓库内可用）")
            return 1
        bad = 0
        for script in sorted(ex.glob("ex0*.py")):
            cmd = [sys.executable, str(script)] + (["--out", a.out] if a.out else [])
            print("▶", script.name, flush=True)
            bad += subprocess.call(cmd) != 0
        return 1 if bad else 0
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
