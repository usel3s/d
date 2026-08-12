#!/usr/bin/env python3
"""Отрисовка штампа/круга/стрелки в стиле WebApp (Manrope)."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

TAPE_LABELS = {
    "red": "Красная",
    "blue": "Синяя",
    "yellow": "Жёлтая",
    "white": "Белая",
    "black": "Чёрная",
}
LOC_LABELS = {
    "warehouse_1": "Тайник",
    "warehouse_2": "Подьезд",
    "pickup": "Прикоп",
}

# цвет обводки как в приложении #3dcf7a
MARK_BGR = (61, 207, 61)
FONT_DIR = Path(__file__).resolve().parent / "fonts"


def street_only(addr: str) -> str:
    text = (addr or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    keep = []
    for p in parts:
        low = p.lower()
        if low in {"ru", "россия", "иваново", "ivanovo"}:
            break
        keep.append(p)
    return ", ".join(keep) if keep else parts[0]


def load_font(size: int, weight: str = "bold") -> ImageFont.ImageFont:
    by_weight = {
        "extrabold": FONT_DIR / "Manrope-ExtraBold.ttf",
        "bold": FONT_DIR / "Manrope-Bold.ttf",
        "semibold": FONT_DIR / "Manrope-SemiBold.ttf",
    }
    candidates = [
        by_weight.get(weight),
        FONT_DIR / "Manrope-Bold.ttf",
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    for path in candidates:
        if path and path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def paint_stroke_mask(bgr: np.ndarray) -> np.ndarray:
    """Ярко-красный штрих GPS Camera (не ржавчина / кирпич)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, (0, 115, 85), (11, 255, 255))
    m2 = cv2.inRange(hsv, (169, 115, 85), (180, 255, 255))
    mask = cv2.bitwise_or(m1, m2)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    return mask


def detect_red_mask(bgr: np.ndarray, for_mark: bool = True) -> np.ndarray:
    """Совместимость: одиночный кадр без пары clean."""
    mask = paint_stroke_mask(bgr)
    h, w = mask.shape
    if for_mark:
        mask[: int(h * 0.10), :] = 0
        mask[int(h * 0.88) :, :] = 0
        mask[:, int(w * 0.85) :] = 0
    return _pick_mark_component(mask)


def _blank_ui(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    h, w = out.shape
    out[: int(h * 0.10), :] = 0
    out[int(h * 0.88) :, :] = 0
    out[:, int(w * 0.85) :] = 0
    return out


def _ringness(comp: np.ndarray) -> float:
    """Насколько компонент похож на кольцо (нарисованный круг)."""
    ys, xs = np.where(comp > 0)
    if len(xs) < 40:
        return 0.0
    cx, cy = float(xs.mean()), float(ys.mean())
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    r = float(np.percentile(dist, 70))
    if r < 12:
        return 0.0
    # доля «дырки» внутри ~0.55–0.85 радиуса
    hh, ww = comp.shape
    yy, xx = np.ogrid[:hh, :ww]
    inner = (xx - cx) ** 2 + (yy - cy) ** 2 <= (r * 0.55) ** 2
    mid = ((xx - cx) ** 2 + (yy - cy) ** 2 <= (r * 1.05) ** 2) & ~inner
    inner_fill = float(np.count_nonzero(comp[inner])) / max(int(np.count_nonzero(inner)), 1)
    mid_fill = float(np.count_nonzero(comp[mid])) / max(int(np.count_nonzero(mid)), 1)
    # кольцо: внутри пусто, в кольце плотно
    return max(0.0, (mid_fill - inner_fill) * mid_fill)


def _pick_mark_component(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    clean = np.zeros_like(mask)
    min_area = max(70, int(h * w * 0.00006))
    max_area = int(h * w * 0.045)
    best_i, best_score = 0, 0.0
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area or area > max_area:
            continue
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if bw < 14 or bh < 14:
            continue
        # слишком мелкий «кружок» UI / шум
        if max(bw, bh) < 22 and area < 200:
            continue
        aspect = max(bw, bh) / max(min(bw, bh), 1)
        fill = area / max(bw * bh, 1)
        comp = (labels == i).astype(np.uint8) * 255
        ring = _ringness(comp)
        # крупные сплошные пятна сцены — отбрасываем; мелкие залитые круги после close — ок
        huge = area > int(h * w * 0.01)
        if fill > 0.62 and ring < 0.06 and aspect < 2.2 and huge:
            continue
        score = float(area)
        if ring > 0.08:
            score *= 3.0 + ring * 8.0
        elif 0.8 <= aspect <= 2.4 and fill < 0.75:
            score *= 2.2  # компактный круг/овал
        elif aspect >= 2.8 and fill < 0.45:
            score *= 1.6  # стрелка
        elif fill > 0.55 and not huge:
            score *= 1.8  # замкнутый круг после close
        elif fill > 0.5:
            score *= 0.3
        if score > best_score:
            best_score, best_i = score, i
    if best_i and best_score > 0:
        clean[labels == best_i] = 255
    return clean


def extract_user_mark_mask(stamped: np.ndarray, clean: np.ndarray | None = None) -> np.ndarray:
    """
    Красная метка, которую нарисовали на stamped.
    Если есть clean-пара — вычитаем красное сцены (только штрих остаётся).
    """
    ms = paint_stroke_mask(stamped)
    if clean is not None:
        hs, ws = stamped.shape[:2]
        hc, wc = clean.shape[:2]
        if (hc, wc) != (hs, ws):
            clean = cv2.resize(clean, (ws, hs), interpolation=cv2.INTER_AREA)
        mc = paint_stroke_mask(clean)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
        mc = cv2.dilate(mc, k, iterations=2)
        ms = cv2.bitwise_and(ms, cv2.bitwise_not(mc))
    ms = _blank_ui(ms)
    # склеиваем разорванный контур круга (без чрезмерной заливки)
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    ms = cv2.morphologyEx(ms, cv2.MORPH_CLOSE, k2, iterations=2)
    return _pick_mark_component(ms)


def analyze_red_mark(mask_red: np.ndarray) -> dict:
    ys, xs = np.where(mask_red > 0)
    empty = {
        "found": False,
        "kind": "circle",
        "center": None,
        "radius": None,
        "tip": None,
        "tail": None,
    }
    if len(xs) < 90:
        return empty
    pts = np.column_stack([xs.astype(np.float64), ys.astype(np.float64)])
    (cx_f, cy_f), radius_f = cv2.minEnclosingCircle(pts.astype(np.float32))
    cx, cy = int(cx_f), int(cy_f)
    radius = int(radius_f)
    radius = max(28, min(radius, int(min(mask_red.shape) * 0.32)))

    mean = pts.mean(axis=0)
    centered = pts - mean
    cov = np.cov(centered.T)
    if cov.ndim < 2:
        return empty
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    elong = float(eigvals[-1] / max(eigvals[0], 1e-6))
    main = eigvecs[:, -1]
    proj = centered @ main
    tip = mean + main * proj.max()
    tail = mean + main * proj.min()

    dist = np.sqrt((xs - cx_f) ** 2 + (ys - cy_f) ** 2)
    radial_cv = float(dist.std() / max(dist.mean(), 1e-6))
    ring = _ringness(mask_red)
    # дуга круга: низкий radial_cv даже при большом elong
    looks_circular = radial_cv < 0.45 or ring >= 0.08
    kind = "arrow" if (elong >= 5.0 and not looks_circular) else "circle"
    return {
        "found": True,
        "kind": kind,
        "center": (cx, cy),
        "radius": radius,
        "tip": (int(tip[0]), int(tip[1])),
        "tail": (int(tail[0]), int(tail[1])),
        "elong": elong,
        "ring": ring,
        "radial_cv": radial_cv,
        "pixels": int(len(xs)),
    }


def draw_app_circle(
    bgr: np.ndarray,
    center: tuple[int, int],
    radius: int,
    color_bgr=MARK_BGR,
) -> np.ndarray:
    out = bgr.copy()
    h, w = out.shape[:2]
    thickness = max(3, int(min(w, h) * 0.0065))
    cx, cy = int(center[0]), int(center[1])
    cv2.circle(out, (cx, cy), radius, color_bgr, thickness, lineType=cv2.LINE_AA)
    return out


def draw_app_arrow(
    bgr: np.ndarray,
    tip: tuple[int, int],
    tail: tuple[int, int],
    color_bgr=MARK_BGR,
) -> np.ndarray:
    out = bgr.copy()
    h, w = out.shape[:2]
    thickness = max(3, int(min(w, h) * 0.0065))
    x1, y1 = int(tail[0]), int(tail[1])
    x2, y2 = int(tip[0]), int(tip[1])
    dx, dy = float(x2 - x1), float(y2 - y1)
    length = math.hypot(dx, dy)
    if length < 16:
        return draw_app_circle(out, tip, max(24, int(min(w, h) * 0.06)), color_bgr)

    ux, uy = dx / length, dy / length
    head_len = max(18, min(int(length * 0.28), int(min(w, h) * 0.08)))
    head_w = max(12, int(head_len * 0.62))
    bx = int(x2 - ux * head_len)
    by = int(y2 - uy * head_len)

    cv2.line(out, (x1, y1), (bx, by), color_bgr, thickness, cv2.LINE_AA)

    px, py = -uy, ux
    pts = np.array(
        [
            (x2, y2),
            (int(bx + px * head_w), int(by + py * head_w)),
            (int(bx - px * head_w), int(by - py * head_w)),
        ],
        np.int32,
    )
    cv2.fillConvexPoly(out, pts, color_bgr, cv2.LINE_AA)
    return out


def draw_mark(
    bgr: np.ndarray,
    analysis: dict,
) -> np.ndarray:
    """Рисует метку только если она найдена на исходнике (found=True)."""
    if not analysis or not analysis.get("found"):
        return bgr
    kind = analysis.get("kind") or "circle"
    if kind == "arrow" and analysis.get("tip") and analysis.get("tail"):
        return draw_app_arrow(bgr, analysis["tip"], analysis["tail"])
    center = analysis.get("center")
    radius = analysis.get("radius")
    if not center or not radius:
        return bgr
    return draw_app_circle(bgr, center, int(radius))


def scale_analysis(analysis: dict, src_hw: tuple[int, int], dst_hw: tuple[int, int]) -> dict:
    sh, sw = src_hw
    dh, dw = dst_hw
    sx, sy = dw / sw, dh / sh
    out = dict(analysis)

    def sc_pt(pt):
        if not pt:
            return None
        return (int(pt[0] * sx), int(pt[1] * sy))

    out["center"] = sc_pt(analysis.get("center"))
    out["tip"] = sc_pt(analysis.get("tip"))
    out["tail"] = sc_pt(analysis.get("tail"))
    if analysis.get("radius"):
        out["radius"] = max(20, int(analysis["radius"] * min(sx, sy)))
    return out


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = str(text).split()
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
    """Как index.html → paintStamp."""
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
        lat = float(meta["lat"])
        lon = float(meta["lon"])
        gps = f"{lat:.5f}, {lon:.5f}"
        if meta.get("acc") is not None:
            acc = float(meta["acc"])
            if abs(acc - int(acc)) < 1e-6:
                gps += f"  ±{int(acc)} м"
            else:
                gps += f"  ±{acc:.1f} м"
        rows.append(("#gps", gps))
    addr = street_only(meta.get("addr") or "")
    if addr:
        rows.append(("#addr", addr))

    margin = max(10, round(w * 0.028))
    pad_x = max(12, round(w * 0.03))
    pad_y = max(10, round(w * 0.022))
    font_size = max(11, round(w * 0.024))
    tag_size = max(10, round(font_size * 0.9))
    line_h = round(font_size * 1.42)
    radius = max(14, round(w * 0.032))
    max_text_w = w - margin * 2 - pad_x * 2

    font = load_font(font_size, "extrabold")
    tag_font = load_font(tag_size, "bold")

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

    draw.rounded_rectangle(
        [box_x + 2, box_y + 3, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=(20, 24, 33, 46),
    )
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=(255, 255, 255, 235),
        outline=(17, 17, 20, 26),
        width=max(1, round(w * 0.002)),
    )

    # faint grid only inside card
    grid = max(10, round(font_size * 0.9))
    grid_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid_img)
    for x in range(box_x, box_x + box_w, grid):
        gdraw.line([(x, box_y), (x, box_y + box_h)], fill=(17, 17, 20, 13), width=1)
    for y in range(box_y, box_y + box_h, grid):
        gdraw.line([(box_x, y), (box_x + box_w, y)], fill=(17, 17, 20, 13), width=1)
    clip = Image.new("L", (w, h), 0)
    ImageDraw.Draw(clip).rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h], radius=radius, fill=255
    )
    grid_img.putalpha(ImageChops.multiply(grid_img.split()[-1], clip))
    overlay = Image.alpha_composite(overlay, grid_img)
    draw = ImageDraw.Draw(overlay)

    bar_w = max(22, round(w * 0.05))
    bar_h = max(10, round(font_size * 0.85))
    bx = box_x + box_w - pad_x - bar_w
    by = box_y + pad_y
    for i in range(8):
        tw = 2 if i % 3 == 0 else 1
        draw.rectangle(
            [bx + int(i * 3.2), by, bx + int(i * 3.2) + tw, by + bar_h],
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
