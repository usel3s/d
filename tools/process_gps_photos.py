#!/usr/bin/env python3
"""Переразметка фото GPS Camera 55 → стиль нашего WebApp."""

from __future__ import annotations

import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC = Path(r"C:\Users\root\Desktop\Новая папка (4)")
OUT = Path(r"C:\Users\root\Desktop\Новая папка (4) — готово")
META_CACHE = OUT / "_meta.json"

TAPE_LABELS = {
    "yellow": "Жёлтый",
    "red": "Красный",
    "white": "Белый",
    "blue": "Синий",
    "black": "Чёрный",
    "green": "Зелёный",
    "orange": "Оранжевый",
    "gray": "Серый",
    "brown": "Коричневый",
    "purple": "Фиолетовый",
    "pink": "Розовый",
    "transparent": "Прозрачный",
}
LOC_LABELS = {
    "warehouse_1": "Тайник",
    "warehouse_2": "Подьезд",
    "pickup": "Прикоп",
}
TAPE_CYCLE = ["yellow", "red", "white", "blue", "black", "green", "orange", "gray"]

GPS_RE = re.compile(
    r"(?P<lat>5[56]\.\d{3,8})\s*[,;\s]\s*(?P<lon>40\.\d{3,8})"
)
ACC_RE = re.compile(r"[±\+\-]?\s*(\d{1,3})\s*[мmM]")
ADDR_RE = re.compile(
    r"((?:улица|ул\.?|проспект|пр\.?|переулок|пер\.?|городская|гаражная|"
    r"советская|ленина|менделеева|ясной|полян\w*)"
    r"[^\n,]{0,40}?,\s*\d+[А-Яа-яA-Za-z]?(?:\s*,\s*Иваново)?)",
    re.I,
)


def street_only(addr: str) -> str:
    text = (addr or "").strip()
    if not text:
        return ""
    # drop city / country tails
    parts = [p.strip() for p in text.split(",") if p.strip()]
    keep = []
    for p in parts:
        low = p.lower()
        if low in {"ru", "россия", "иваново", "ivanovo"}:
            break
        keep.append(p)
    return ", ".join(keep) if keep else parts[0]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def detect_red_mask(bgr: np.ndarray, for_circle: bool = False) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, (0, 90, 80), (12, 255, 255))
    m2 = cv2.inRange(hsv, (165, 90, 80), (180, 255, 255))
    mask = cv2.bitwise_or(m1, m2)
    h, w = mask.shape
    if for_circle:
        # exclude UI chrome (top/bottom bars + bottom-right pin)
        mask[: int(h * 0.08), :] = 0
        mask[int(h * 0.86) :, :] = 0
        mask[:, int(w * 0.82) :] = 0
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.dilate(mask, k, iterations=1)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    clean = np.zeros_like(mask)
    min_area = max(120, int(h * w * 0.0002))
    best_i, best_area = 0, 0
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        if for_circle:
            # prefer largest stroke blob (the hand circle)
            if area > best_area:
                best_area, best_i = area, i
        else:
            clean[labels == i] = 255
    if for_circle and best_i:
        clean[labels == best_i] = 255
    elif not for_circle:
        pass
    return clean


def fill_horizontal_band(bgr: np.ndarray, y0: int, y1: int, from_below: bool) -> None:
    """Заливка бара копированием соседних строк (чище, чем inpaint на широкой полосе)."""
    h, w = bgr.shape[:2]
    y0 = max(0, y0)
    y1 = min(h, y1)
    if y1 <= y0:
        return
    if from_below:
        src_y = min(h - 1, y1 + 2)
        for y in range(y1 - 1, y0 - 1, -1):
            # slight noise mix of a few rows below
            src = bgr[min(h - 1, src_y + (y1 - 1 - y) % 3)]
            bgr[y] = src
    else:
        src_y = max(0, y0 - 3)
        for y in range(y0, y1):
            src = bgr[max(0, src_y - (y - y0) % 3)]
            bgr[y] = src


def clean_overlays(bgr: np.ndarray) -> tuple[np.ndarray, tuple[tuple[int, int], int] | None]:
    out = bgr.copy()
    h, w = out.shape[:2]

    red_circle = detect_red_mask(out, for_circle=True)
    circle = circle_from_red(red_circle)

    # remove hand circle first via inpaint
    if red_circle.any():
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        red_dil = cv2.dilate(red_circle, k, iterations=2)
        out = cv2.inpaint(out, red_dil, 5, cv2.INPAINT_TELEA)

    # top / bottom bars by row clone
    fill_horizontal_band(out, 0, int(h * 0.072), from_below=True)
    fill_horizontal_band(out, int(h * 0.875), h, from_below=False)

    # watermark + pin: dark translucent panels lower-right / lower-center
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    y0, y1 = int(h * 0.52), int(h * 0.90)
    roi_hsv = hsv[y0:y1, :]
    dark = cv2.inRange(roi_hsv, (0, 0, 0), (180, 90, 100))
    # also faint white/gray watermark text
    pale = cv2.inRange(roi_hsv, (0, 0, 140), (180, 40, 210))
    pale = cv2.bitwise_and(pale, cv2.inRange(roi_hsv, (0, 0, 0), (180, 50, 255)))
    wm = cv2.bitwise_or(dark, pale)
    wm = cv2.morphologyEx(
        wm,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (11, 7)),
        iterations=2,
    )
    num, labels, stats, _ = cv2.connectedComponentsWithStats(wm, 8)
    mask = np.zeros((h, w), np.uint8)
    for i in range(1, num):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        if area > 600 and bw > 35 and bh > 16:
            ys = y0 + stats[i, cv2.CC_STAT_TOP]
            xs = stats[i, cv2.CC_STAT_LEFT]
            pad = 4
            mask[
                max(0, ys - pad) : min(h, ys + bh + pad),
                max(0, xs - pad) : min(w, xs + bw + pad),
            ] = 255

    # red pin bottom-right
    pin_roi = out[int(h * 0.80) :, int(w * 0.75) :]
    pin_hsv = cv2.cvtColor(pin_roi, cv2.COLOR_BGR2HSV)
    pin = cv2.bitwise_or(
        cv2.inRange(pin_hsv, (0, 100, 100), (12, 255, 255)),
        cv2.inRange(pin_hsv, (168, 100, 100), (180, 255, 255)),
    )
    pin = cv2.dilate(pin, np.ones((9, 9), np.uint8), iterations=2)
    mask[int(h * 0.80) :, int(w * 0.75) :] = np.maximum(
        mask[int(h * 0.80) :, int(w * 0.75) :], pin
    )

    if mask.any():
        out = cv2.inpaint(out, mask, 4, cv2.INPAINT_TELEA)

    return out, circle


def process_one(path: Path, meta: dict, dest: Path) -> None:
    data = np.fromfile(str(path), dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"cannot read {path}")

    cleaned, circle = clean_overlays(bgr)
    if circle is None:
        h, w = cleaned.shape[:2]
        circle = ((w // 2, int(h * 0.58)), int(min(w, h) * 0.11))

    colors = [
        (70, 210, 80),
        (0, 175, 255),
        (60, 60, 255),
        (255, 160, 10),
    ]
    color = colors[hash(path.name) % len(colors)]
    circled = draw_app_circle(cleaned, circle[0], circle[1], color)

    rgb = cv2.cvtColor(circled, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    stamped = paint_stamp(pil, meta)

    dest.parent.mkdir(parents=True, exist_ok=True)
    stamped.save(dest, quality=92, optimize=True)


def circle_from_red(mask_red: np.ndarray) -> tuple[tuple[int, int], int] | None:
    ys, xs = np.where(mask_red > 0)
    if len(xs) < 40:
        return None
    cx = int(xs.mean())
    cy = int(ys.mean())
    # radius from mean distance of stroke points (approx ring)
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    r = int(np.percentile(dist, 75))
    r = max(28, min(r, int(min(mask_red.shape) * 0.28)))
    return (cx, cy), r


def draw_app_circle(bgr: np.ndarray, center: tuple[int, int], radius: int, color_bgr=(70, 210, 80)) -> np.ndarray:
    """Ручной круг в стиле приложения (чуть неровный)."""
    out = bgr.copy()
    h, w = out.shape[:2]
    cx, cy = center
    thickness = max(3, int(min(w, h) * 0.007))
    rng = random.Random(cx * 10007 + cy)
    pts = []
    steps = 72
    for i in range(steps):
        ang = 2 * math.pi * i / steps
        jitter = 1 + rng.uniform(-0.04, 0.05)
        rr = radius * jitter
        # slight oval
        x = int(cx + rr * math.cos(ang) * (1 + rng.uniform(-0.02, 0.02)))
        y = int(cy + rr * math.sin(ang) * (1 + rng.uniform(-0.03, 0.03)))
        pts.append([x, y])
    pts_arr = np.array(pts, np.int32).reshape(-1, 1, 2)
    # soft shadow
    shadow = out.copy()
    cv2.polylines(shadow, [pts_arr], True, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    out = cv2.addWeighted(shadow, 0.25, out, 0.75, 0)
    cv2.polylines(out, [pts_arr], True, color_bgr, thickness, cv2.LINE_AA)
    return out


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for word in words[1:]:
        trial = cur + " " + word
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines[:2]


def paint_stamp(pil: Image.Image, meta: dict) -> Image.Image:
    img = pil.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    tape = TAPE_LABELS.get(meta.get("tape", "yellow"), "Жёлтый")
    loc = LOC_LABELS.get(meta.get("location", "pickup"), "Прикоп")
    note = (meta.get("note") or "—").strip() or "—"
    rows = [
        ("#tape", tape),
        ("#location", loc),
        ("#note", note),
    ]
    if meta.get("lat") is not None and meta.get("lon") is not None:
        gps = f"{meta['lat']:.5f}, {meta['lon']:.5f}"
        if meta.get("acc") is not None:
            gps += f"  ±{int(meta['acc'])} м"
        rows.append(("#gps", gps))
    addr = street_only(meta.get("addr") or "")
    if addr:
        rows.append(("#addr", addr))

    margin = max(10, round(w * 0.028))
    pad_x = max(12, round(w * 0.03))
    pad_y = max(10, round(w * 0.022))
    font_size = max(14, round(w * 0.028))
    tag_size = max(12, round(font_size * 0.9))
    line_h = round(font_size * 1.42)
    radius = max(14, round(w * 0.032))
    max_text_w = w - margin * 2 - pad_x * 2

    font = load_font(font_size)
    tag_font = load_font(tag_size)

    wrapped: list[tuple[str, str]] = []
    for tag, value in rows:
        prefix = tag + "  "
        prefix_w = draw.textlength(prefix, font=font)
        value_lines = wrap_text(draw, value, font, max(40, max_text_w - prefix_w))
        for i, line in enumerate(value_lines):
            wrapped.append((tag if i == 0 else "", line))

    box_w = w - margin * 2
    box_h = pad_y * 2 + len(wrapped) * line_h + 4
    box_x = margin
    box_y = h - margin - box_h

    # shadow
    draw.rounded_rectangle(
        [box_x + 2, box_y + 3, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=(20, 24, 33, 46),
    )
    # glass
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=(255, 255, 255, 235),
        outline=(17, 17, 20, 26),
        width=max(1, round(w * 0.002)),
    )

    # faint grid
    grid = max(10, round(font_size * 0.9))
    for x in range(box_x, box_x + box_w, grid):
        draw.line([(x, box_y), (x, box_y + box_h)], fill=(17, 17, 20, 12), width=1)
    for y in range(box_y, box_y + box_h, grid):
        draw.line([(box_x, y), (box_x + box_w, y)], fill=(17, 17, 20, 12), width=1)

    # barcode
    bar_w = max(22, round(w * 0.05))
    bar_h = max(10, round(font_size * 0.85))
    bx = box_x + box_w - pad_x - bar_w
    by = box_y + pad_y
    for i in range(8):
        tw = 2 if i % 3 == 0 else 1
        draw.rectangle(
            [bx + i * 3, by, bx + i * 3 + tw, by + bar_h],
            fill=(17, 17, 20, 140),
        )

    text_x = box_x + pad_x
    for i, (tag, value) in enumerate(wrapped):
        y = box_y + pad_y + i * line_h
        if tag:
            draw.text((text_x, y), tag, font=tag_font, fill=(92, 95, 106, 255))
            tag_w = draw.textlength(tag + "  ", font=tag_font)
            draw.text((text_x + tag_w, y), value, font=font, fill=(17, 17, 20, 255))
        else:
            draw.text((text_x, y), value, font=font, fill=(17, 17, 20, 255))

    return Image.alpha_composite(img, overlay).convert("RGB")


def ocr_windows(path: Path) -> str:
    """OCR через Windows.Media.Ocr (PowerShell helper)."""
    ps = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  $netTask.Result
}
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$path = $args[0]
$out = $args[1]
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
[System.IO.File]::WriteAllText($out, $result.Text, [System.Text.UTF8Encoding]::new($false))
"""
    out = Path(str(path) + ".ocr.txt")
    import subprocess

    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            ps,
            str(path),
            str(out),
        ],
        check=False,
        capture_output=True,
    )
    if out.exists():
        text = out.read_text(encoding="utf-8", errors="ignore")
        out.unlink(missing_ok=True)
        return text
    return ""


def parse_meta_from_text(text: str) -> dict:
    meta: dict = {}
    m = GPS_RE.search(text.replace(" ", ""))
    if not m:
        m = GPS_RE.search(text)
    if m:
        meta["lat"] = float(m.group("lat"))
        meta["lon"] = float(m.group("lon"))
    accs = ACC_RE.findall(text)
    if accs:
        # first reasonable accuracy
        for a in accs:
            v = int(a)
            if 1 <= v <= 200:
                meta["acc"] = v
                break
    am = ADDR_RE.search(text)
    if am:
        meta["addr"] = am.group(1).strip()
    # fallback: line with Иваново
    if "addr" not in meta:
        for line in text.splitlines():
            if "Иваново" in line or "улица" in line.lower() or "ул." in line.lower():
                cleaned = line.replace("Не мусорите пожалуйста на месте!", "").strip(" !")
                if cleaned:
                    meta["addr"] = cleaned
                    break
    return meta


def extract_meta_cv(path: Path) -> dict:
    """OCR по кропам верха/низа (увеличенным)."""
    bgr = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return {}
    h, w = bgr.shape[:2]
    parts = []
    for y0, y1 in [(0, int(h * 0.1)), (int(h * 0.84), h)]:
        crop = bgr[y0:y1, :]
        big = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        tmp = path.with_suffix(f".crop{y0}.png")
        cv2.imencode(".png", big)[1].tofile(str(tmp))
        parts.append(ocr_windows(tmp))
        tmp.unlink(missing_ok=True)
    text = "\n".join(parts)
    # also full image OCR as backup
    if not GPS_RE.search(text.replace(" ", "")):
        text += "\n" + ocr_windows(path)
    return parse_meta_from_text(text)


def cluster_key(meta: dict) -> str:
    if meta.get("lat") is not None and meta.get("lon") is not None:
        return f"{meta['lat']:.4f},{meta['lon']:.4f}"
    addr = street_only(meta.get("addr") or "")
    if addr:
        return addr.lower()
    return "unknown"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    photos = sorted(SRC.glob("photo_*.jpg"), key=lambda p: int(re.search(r"photo_(\d+)", p.name).group(1)))
    if not photos:
        print("no photos", file=sys.stderr)
        return 1

    # Prefer external meta extracted by vision agent
    external_meta = Path(r"c:\Users\root\d\tools\photo_meta.json")
    metas: dict[str, dict] = {}
    if external_meta.exists():
        metas = json.loads(external_meta.read_text(encoding="utf-8"))
        print(f"loaded external meta: {len(metas)}")
    elif META_CACHE.exists():
        metas = json.loads(META_CACHE.read_text(encoding="utf-8"))

    print(f"photos: {len(photos)}")
    for i, path in enumerate(photos, 1):
        key = path.name
        if key not in metas or not metas[key].get("lat"):
            print(f"[{i}/{len(photos)}] OCR {path.name}")
            meta = extract_meta_cv(path)
            metas[key] = meta
            META_CACHE.write_text(json.dumps(metas, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            print(f"[{i}/{len(photos)}] cache {path.name}")

    # assign location type / tape per cluster
    clusters: dict[str, list[Path]] = defaultdict(list)
    for path in photos:
        clusters[cluster_key(metas.get(path.name, {}))].append(path)

    # sort clusters by first photo number
    ordered = sorted(
        clusters.items(),
        key=lambda kv: min(int(re.search(r"photo_(\d+)", p.name).group(1)) for p in kv[1]),
    )

    print(f"clusters: {len(ordered)}")
    for folder_idx, (ckey, paths) in enumerate(ordered, 1):
        folder = OUT / str(folder_idx)
        folder.mkdir(parents=True, exist_ok=True)
        tape = TAPE_CYCLE[(folder_idx - 1) % len(TAPE_CYCLE)]
        # Прикоп for buried-looking groups alternating with Тайник
        location = "pickup" if folder_idx % 3 != 0 else "warehouse_1"
        for n, path in enumerate(sorted(paths, key=lambda p: int(re.search(r"photo_(\d+)", p.name).group(1))), 1):
            meta = dict(metas.get(path.name, {}))
            meta["tape"] = tape
            meta["location"] = location
            meta["note"] = "—"
            dest = folder / f"{n}.jpg"
            print(f"  -> {folder.name}/{dest.name} ({path.name}) [{ckey}]")
            process_one(path, meta, dest)

        # info file
        sample = metas.get(paths[0].name, {})
        info = {
            "folder": folder_idx,
            "cluster": ckey,
            "count": len(paths),
            "tape": TAPE_LABELS[tape],
            "location": LOC_LABELS[location],
            "gps": sample.get("lat") and f"{sample.get('lat')}, {sample.get('lon')}",
            "addr": street_only(sample.get("addr") or ""),
            "sources": [p.name for p in paths],
        }
        (folder / "info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("DONE", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
