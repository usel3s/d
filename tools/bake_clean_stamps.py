#!/usr/bin/env python3
"""Штампует чистые фото в стиле приложения → папки 1..20."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(r"c:\Users\root\d\tools")
sys.path.insert(0, str(ROOT))

from stamp_draw import (  # noqa: E402
    analyze_red_mark,
    draw_mark,
    extract_user_mark_mask,
    paint_stamp,
    scale_analysis,
    street_only,
)

CLEAN_DIR = Path(r"C:\Users\root\Desktop\Без штампа")
STAMPED_DIR = Path(r"C:\Users\root\Desktop\Со штампом")
OUT_DIR = Path(r"C:\Users\root\Desktop\Готово штампы")

ANSWERS = json.loads((ROOT / "location_answers.json").read_text(encoding="utf-8"))
CLUSTERS = json.loads((ROOT / "gps_clusters.json").read_text(encoding="utf-8"))
PAIRS = json.loads((ROOT / "scene_pairs.json").read_text(encoding="utf-8"))


def stamped_num(name: str) -> int:
    m = re.search(r"photo_(\d+)", name)
    return int(m.group(1)) if m else 0


def hav(a, b) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def build_maps():
    loc_by_id = {int(x["id"]): x for x in ANSWERS["locations"]}
    # stamped num → location id (from answers stamped_nums, fallback clusters)
    num_to_loc: dict[int, int] = {}
    for loc in ANSWERS["locations"]:
        for n in loc["stamped_nums"]:
            num_to_loc[int(n)] = int(loc["id"])
    for c in CLUSTERS:
        lid = int(c["id"])
        for n in c["stamped_nums"]:
            num_to_loc.setdefault(int(n), lid)

    cluster_by_id = {int(c["id"]): c for c in CLUSTERS}
    return loc_by_id, num_to_loc, cluster_by_id


def looks_like_blue_bottle(bgr: np.ndarray) -> bool:
    """Грубая эвристика: много синего в кадре (бутылка)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (95, 80, 60), (130, 255, 255))
    ratio = float(np.count_nonzero(blue)) / float(blue.size)
    return ratio > 0.04


def load_bgr(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {path}")
    return img


def mark_from_pair(stamped: np.ndarray, clean: np.ndarray) -> dict:
    """Метка только если на stamped есть красный штрих (после вычитания сцены)."""
    mask = extract_user_mark_mask(stamped, clean)
    return analyze_red_mark(mask)


def bake_one(
    clean_path: Path,
    stamped_path: Path | None,
    loc: dict,
    cluster: dict,
    dest: Path,
) -> dict:
    clean = load_bgr(clean_path)
    marked = clean
    mark_info = {"drawn": False, "kind": None}

    # Метку ставим ТОЛЬКО если на парном фото со штампом ты её рисовал.
    if stamped_path and stamped_path.exists():
        stamped = load_bgr(stamped_path)
        analysis = mark_from_pair(stamped, clean)
        if analysis.get("found"):
            analysis = scale_analysis(analysis, stamped.shape[:2], clean.shape[:2])
            marked = draw_mark(clean, analysis)
            mark_info = {
                "drawn": True,
                "kind": analysis.get("kind"),
                "center": analysis.get("center"),
                "radius": analysis.get("radius"),
                "tip": analysis.get("tip"),
                "tail": analysis.get("tail"),
            }

    meta = {
        "tape": "black",
        "location": loc["type"],
        "note": loc["note"],
        "lat": cluster.get("lat"),
        "lon": cluster.get("lon"),
        "acc": cluster.get("acc"),
        "addr": street_only(cluster.get("addr") or ""),
    }
    rgb = cv2.cvtColor(marked, cv2.COLOR_BGR2RGB)
    stamped_img = paint_stamp(Image.fromarray(rgb), meta)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stamped_img.save(dest, quality=92, optimize=True)
    return mark_info


def main() -> int:
    loc_by_id, num_to_loc, cluster_by_id = build_maps()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # group outputs per location
    counters: dict[int, int] = {i: 0 for i in loc_by_id}
    report = {"baked": [], "skipped_blue": [], "skipped_no_loc": [], "unmatched": []}

    for pair in PAIRS.get("pairs") or []:
        clean_name = pair["clean"]
        stamped_name = pair.get("stamped")
        clean_path = CLEAN_DIR / clean_name
        if not clean_path.exists():
            report["skipped_no_loc"].append(clean_name)
            continue

        sn = stamped_num(stamped_name or "")
        loc_id = num_to_loc.get(sn)
        if loc_id is None and pair.get("lat") is not None:
            # nearest cluster by GPS
            best, best_d = None, 1e18
            for cid, c in cluster_by_id.items():
                d = hav((pair["lat"], pair["lon"]), (c["lat"], c["lon"]))
                if d < best_d:
                    best, best_d = cid, d
            if best is not None and best_d < 25:
                loc_id = best

        if loc_id is None:
            report["skipped_no_loc"].append(clean_name)
            continue

        loc = loc_by_id[loc_id]
        cluster = cluster_by_id.get(loc_id) or {
            "lat": pair.get("lat"),
            "lon": pair.get("lon"),
            "acc": pair.get("acc"),
            "addr": pair.get("addr"),
        }

        # override cluster GPS with pair GPS when available (more precise frame)
        if pair.get("lat") is not None:
            cluster = {
                **cluster,
                "lat": pair["lat"],
                "lon": pair["lon"],
                "acc": pair.get("acc") or cluster.get("acc"),
                "addr": pair.get("addr") or cluster.get("addr"),
            }

        clean_bgr = load_bgr(clean_path)
        if loc.get("skip_blue_bottle") and looks_like_blue_bottle(clean_bgr):
            report["skipped_blue"].append(clean_name)
            # copy original without stamp into _skip
            skip_dir = OUT_DIR / str(loc_id) / "_skip_blue_bottle"
            skip_dir.mkdir(parents=True, exist_ok=True)
            Image.open(clean_path).save(skip_dir / clean_name, quality=92)
            continue

        counters[loc_id] += 1
        dest = OUT_DIR / str(loc_id) / f"{counters[loc_id]}.jpg"
        stamped_path = STAMPED_DIR / stamped_name if stamped_name else None
        mark_info = bake_one(clean_path, stamped_path, loc, cluster, dest)

        info = {
            "file": f"{loc_id}/{counters[loc_id]}.jpg",
            "clean": clean_name,
            "stamped": stamped_name,
            "type": loc["type_label"],
            "note": loc["note"],
            "gps": f"{cluster.get('lat')}, {cluster.get('lon')}",
            "addr": street_only(cluster.get("addr") or ""),
            "mark": mark_info,
        }
        report["baked"].append(info)

    # info.json per folder
    for loc_id, loc in loc_by_id.items():
        folder = OUT_DIR / str(loc_id)
        folder.mkdir(parents=True, exist_ok=True)
        cluster = cluster_by_id.get(loc_id, {})
        files = sorted(folder.glob("*.jpg"))
        (folder / "info.json").write_text(
            json.dumps(
                {
                    "id": loc_id,
                    "type": loc["type_label"],
                    "note": loc["note"],
                    "tape": "Чёрный",
                    "lat": cluster.get("lat"),
                    "lon": cluster.get("lon"),
                    "addr": street_only(cluster.get("addr") or ""),
                    "photos": [p.name for p in files],
                    "count": len(files),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    for name in PAIRS.get("unmatched_clean") or []:
        report["unmatched"].append(name)

    (OUT_DIR / "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"baked={len(report['baked'])} "
        f"skip_blue={len(report['skipped_blue'])} "
        f"no_loc={len(report['skipped_no_loc'])} "
        f"unmatched={len(report['unmatched'])}"
    )
    print("OUT", OUT_DIR)
    for loc_id in sorted(loc_by_id):
        print(f"  {loc_id}: {counters[loc_id]} photos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
