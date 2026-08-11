#!/usr/bin/env python3
"""20 локаций: кластер 20м + ручные склейки от пользователя."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

META = Path(r"c:\Users\root\d\tools\photo_meta_stamped.json")
OUT = Path(r"c:\Users\root\d\tools\gps_clusters.json")
ANSWERS = Path(r"c:\Users\root\d\tools\location_answers.json")

RADIUS_M = 20.0
# stamped photo numbers that must stay in one location (user merges)
FORCE_MERGES = [
    {17, 18, 19, 20},  # Яблочная 11А + Ломаная / колесо
]


def hav(a, b) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def main() -> None:
    meta = json.loads(META.read_text(encoding="utf-8"))
    items = []
    for name, m in meta.items():
        n = int(name.split("_")[1])
        items.append({"n": n, "name": name, **m})
    items.sort(key=lambda x: x["n"])
    idx_by_n = {it["n"]: i for i, it in enumerate(items)}

    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def uni(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if hav((items[i]["lat"], items[i]["lon"]), (items[j]["lat"], items[j]["lon"])) < RADIUS_M:
                uni(i, j)

    for group in FORCE_MERGES:
        nums = [n for n in group if n in idx_by_n]
        if len(nums) < 2:
            continue
        base = idx_by_n[nums[0]]
        for n in nums[1:]:
            uni(base, idx_by_n[n])

    clusters: dict[int, list] = defaultdict(list)
    for i, it in enumerate(items):
        clusters[find(i)].append(it)

    ordered = sorted(clusters.values(), key=lambda c: min(x["n"] for x in c))
    out = []
    for i, c in enumerate(ordered, 1):
        c = sorted(c, key=lambda x: x["n"])
        lat = sum(x["lat"] for x in c) / len(c)
        lon = sum(x["lon"] for x in c) / len(c)
        acc = max((x.get("acc") or 0) for x in c)
        # prefer addr from photo with median index
        addr = c[len(c) // 2]["addr"]
        out.append(
            {
                "id": i,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "acc": acc,
                "addr": addr,
                "stamped_nums": [x["n"] for x in c],
                "stamped": [x["name"] for x in c],
            }
        )

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"locations={len(out)} radius={RADIUS_M}m")
    for c in out:
        print(f"{c['id']:02d} | #{c['stamped_nums']} | {c['addr']}")


if __name__ == "__main__":
    main()
