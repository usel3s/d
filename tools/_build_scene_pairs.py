#!/usr/bin/env python3
"""Crop stamp overlays, OCR GPS, perceptual-match clean↔stamped scenes."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

CLEAN = Path(r"C:\Users\root\Desktop\Без штампа")
STAMP = Path(r"C:\Users\root\Desktop\Со штампом")
ROOT = Path(r"c:\Users\root\d\tools")
CROPS = ROOT / "_stamp_crops"
OCR_DIR = ROOT / "_stamp_ocr"
PS1 = ROOT / "win_ocr.ps1"

GPS_RE = re.compile(r"(?P<lat>5[567]\.\d{3,8})\s*[,;\s]+\s*(?P<lon>40\.\d{3,8})")
# looser: lat and lon may be on separate fragments
LAT_RE = re.compile(r"(?<!\d)(5[567]\.\d{3,8})(?!\d)")
LON_RE = re.compile(r"(?<!\d)(40\.\d{3,8})(?!\d)")
ACC_RE = re.compile(r"[±+\-]?\s*(\d{1,3})\s*[мmM]")
ADDR_RE = re.compile(
    r"((?:улица|ул\.?|проспект|пр\.?|переулок|пер\.?|шоссе|набережная|"
    r"городская|гаражная|советская|ленина|менделеева|ясной|полян\w*|"
    r"куконковых|павла|1-я|2-я|3-я|строителей|фрунзе|ермака|"
    r"посадский|посадская|ташкентская|кузнецова|8\s*марта|"
    r"красных\s*зорь|красных\s*командиров|"
    r"[А-Яа-яA-Za-z\-]+(?:ая|ая|ий|ый|ое|ое)\s+(?:улица|ул\.?))?"
    r"[^\n,]{0,50}?,\s*\d+[А-Яа-яA-Za-z]?"
    r"(?:\s*,\s*Иваново)?(?:\s*,\s*RU)?)",
    re.I,
)


def imread_unicode(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {path}")
    return img


def imwrite_unicode(path: Path, img: np.ndarray) -> None:
    ext = path.suffix or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise RuntimeError(f"encode fail {path}")
    path.write_bytes(buf.tobytes())


def crop_stamps() -> None:
    CROPS.mkdir(exist_ok=True)
    for p in sorted(STAMP.glob("*.jpg"), key=lambda x: int(x.name.split("_")[1])):
        img = imread_unicode(p)
        h, w = img.shape[:2]
        parts = {
            "top": img[0 : int(h * 0.11), :],
            "bot": img[int(h * 0.80) : h, :],
            "mid": img[int(h * 0.55) : int(h * 0.88), int(w * 0.05) : int(w * 0.95)],
        }
        for name, crop in parts.items():
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            up = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
            up = cv2.convertScaleAbs(up, alpha=1.8, beta=25)
            # also binary variant
            _, bw = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            imwrite_unicode(CROPS / f"{p.stem}_{name}.png", up)
            imwrite_unicode(CROPS / f"{p.stem}_{name}_bw.png", bw)
    print("crops", len(list(CROPS.glob("*.png"))))


def run_ocr_all() -> None:
    OCR_DIR.mkdir(exist_ok=True)
    crops = sorted(CROPS.glob("*.png"))
    for i, crop in enumerate(crops):
        out = OCR_DIR / f"{crop.stem}.txt"
        if out.exists() and out.stat().st_size > 0:
            continue
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1),
            str(crop),
            str(out),
        ]
        subprocess.run(cmd, check=False, capture_output=True)
        if (i + 1) % 20 == 0:
            print(f"ocr {i+1}/{len(crops)}")
    print("ocr done")


def parse_meta_for_stem(stem: str) -> dict:
    texts = []
    for p in OCR_DIR.glob(f"{stem}_*.txt"):
        texts.append(p.read_text(encoding="utf-8", errors="replace"))
    # also original ocr_out
    old = ROOT / "ocr_out" / f"{stem}.txt"
    if old.exists():
        texts.append(old.read_text(encoding="utf-8", errors="replace"))
    joined = "\n".join(texts)
    lat = lon = None
    gm = GPS_RE.search(joined)
    if gm:
        lat = float(gm.group("lat"))
        lon = float(gm.group("lon"))
    else:
        lats = LAT_RE.findall(joined)
        lons = LON_RE.findall(joined)
        if lats and lons:
            lat = float(lats[0])
            lon = float(lons[0])
    am = ACC_RE.search(joined)
    acc = int(am.group(1)) if am else None
    addr = ""
    # prefer lines with Иваново / улица
    for t in texts:
        for line in t.splitlines():
            low = line.lower()
            if "иваново" in low or "улица" in low or "ул." in low or "проспект" in low:
                addr = line.strip()
                break
        if addr:
            break
    if not addr:
        m = ADDR_RE.search(joined)
        if m:
            addr = m.group(1).strip()
    return {"lat": lat, "lon": lon, "acc": acc, "addr": addr, "raw": joined[:500]}


def strip_ui(bgr: np.ndarray) -> np.ndarray:
    """Remove top/bottom stamp bars for scene matching."""
    h, w = bgr.shape[:2]
    out = bgr.copy()
    y0, y1 = int(h * 0.08), int(h * 0.86)
    x0, x1 = int(w * 0.02), int(w * 0.98)
    return out[y0:y1, x0:x1]


def phash(img: np.ndarray, hash_size: int = 16) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (hash_size * 2, hash_size * 2), interpolation=cv2.INTER_AREA)
    # DCT-ish via resize mean
    tiny = cv2.resize(small, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    med = np.median(tiny)
    return (tiny > med).astype(np.uint8).flatten()


def ahash(img: np.ndarray, hash_size: int = 16) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tiny = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    mean = tiny.mean()
    return (tiny > mean).astype(np.uint8).flatten()


def hist_feat(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [24, 32], [0, 180, 0, 256])
    h = cv2.normalize(h, None).flatten()
    return h


def orb_score(a: np.ndarray, b: np.ndarray) -> float:
    orb = cv2.ORB_create(800)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        return 0.0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(da, db, k=2)
    good = 0
    for pair in matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good += 1
    return good / max(len(ka), 1)


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def match_scenes() -> dict:
    cleans = sorted(CLEAN.glob("*.jpg"), key=lambda x: int(x.name.split("_")[1]))
    stamps = sorted(STAMP.glob("*.jpg"), key=lambda x: int(x.name.split("_")[1]))

    stamp_data = []
    for p in stamps:
        img = strip_ui(imread_unicode(p))
        small = cv2.resize(img, (320, 240), interpolation=cv2.INTER_AREA)
        stamp_data.append(
            {
                "name": p.name,
                "stem": p.stem,
                "ph": phash(small),
                "ah": ahash(small),
                "hist": hist_feat(small),
                "small": small,
            }
        )

    pairs = []
    used_scores = []  # for debugging
    for cp in cleans:
        img = strip_ui(imread_unicode(cp))
        small = cv2.resize(img, (320, 240), interpolation=cv2.INTER_AREA)
        cph, cah, ch = phash(small), ahash(small), hist_feat(small)
        scored = []
        for sd in stamp_data:
            ph_d = hamming(cph, sd["ph"])
            ah_d = hamming(cah, sd["ah"])
            hist_s = float(cv2.compareHist(ch.astype(np.float32), sd["hist"].astype(np.float32), cv2.HISTCMP_CORREL))
            # lower hash distance better; higher hist better
            score = -(ph_d * 1.2 + ah_d) + hist_s * 40
            # cheap ORB only for top candidates later
            scored.append((score, ph_d, ah_d, hist_s, sd))
        scored.sort(key=lambda x: -x[0])
        # refine top 8 with ORB
        refined = []
        for score, ph_d, ah_d, hist_s, sd in scored[:8]:
            o = orb_score(small, sd["small"])
            final = score + o * 80
            refined.append((final, ph_d, ah_d, hist_s, o, sd))
        refined.sort(key=lambda x: -x[0])
        best = refined[0]
        second = refined[1] if len(refined) > 1 else None
        pairs.append(
            {
                "clean": cp.name,
                "stamped": best[5]["name"],
                "stem": best[5]["stem"],
                "score": best[0],
                "ph": best[1],
                "ah": best[2],
                "hist": best[3],
                "orb": best[4],
                "second": second[5]["name"] if second else None,
                "second_score": second[0] if second else None,
            }
        )
        used_scores.append(best[0])

    return {"pairs_raw": pairs, "stamp_names": [s.name for s in stamps]}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("crops", "all"):
        crop_stamps()
    if mode in ("ocr", "all"):
        run_ocr_all()
    if mode in ("meta", "all"):
        metas = {}
        for p in sorted(STAMP.glob("*.jpg"), key=lambda x: int(x.name.split("_")[1])):
            metas[p.name] = parse_meta_for_stem(p.stem)
        (ROOT / "_stamp_meta.json").write_text(
            json.dumps(metas, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        ok = sum(1 for v in metas.values() if v["lat"] is not None)
        print(f"meta with gps: {ok}/{len(metas)}")
        missing = [k for k, v in metas.items() if v["lat"] is None]
        print("missing:", missing)
    if mode in ("match", "all"):
        result = match_scenes()
        (ROOT / "_match_raw.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("matched", len(result["pairs_raw"]))


if __name__ == "__main__":
    main()
