#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2

ROOT = Path(r"c:\Users\root\d\tools")
sys.path.insert(0, str(ROOT))

from bake_clean_stamps import CLEAN_DIR, STAMPED_DIR, load_bgr  # noqa: E402
from stamp_draw import analyze_red_mark, draw_mark, extract_user_mark_mask  # noqa: E402

OUT = ROOT / "_mark_debug"
OUT.mkdir(exist_ok=True)


def main() -> None:
    pairs = json.loads((ROOT / "scene_pairs.json").read_text(encoding="utf-8"))["pairs"]
    found = 0
    arrows = 0
    for p in pairs:
        sn = p.get("stamped")
        cn = p.get("clean")
        if not sn or not cn:
            continue
        sp, cp = STAMPED_DIR / sn, CLEAN_DIR / cn
        if not sp.exists() or not cp.exists():
            continue
        stamped = load_bgr(sp)
        clean = load_bgr(cp)
        mask = extract_user_mark_mask(stamped, clean)
        a = analyze_red_mark(mask)
        if a.get("found"):
            found += 1
            if a.get("kind") == "arrow":
                arrows += 1
        n = int(sn.split("_")[1])
        if n in {1, 4, 5, 6, 16, 21, 24, 25, 47, 50} or True:
            vis = stamped.copy()
            vis[mask > 0] = (0, 255, 255)
            if a.get("found"):
                vis = draw_mark(vis, a)
            h, w = vis.shape[:2]
            scale = 720 / max(h, w)
            small = cv2.resize(vis, (int(w * scale), int(h * scale)))
            tag = a.get("kind") if a.get("found") else "none"
            cv2.imencode(".jpg", small)[1].tofile(
                str(OUT / f"{n}_{tag}_pix{a.get('pixels') or 0}_r{a.get('ring') or 0:.2f}.jpg")
            )
        print(
            f"{sn}: found={a.get('found')} kind={a.get('kind')} "
            f"pix={a.get('pixels')} elong={a.get('elong')} ring={a.get('ring')}"
        )
    print(f"TOTAL found={found}/{len(pairs)} arrows={arrows}")


if __name__ == "__main__":
    main()
