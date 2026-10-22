"""Photo enhancement: AI super-resolution (x4, tiled) + face restoration, all on CPU through onnxruntime.

Pipeline: detect faces on the original -> upscale the whole frame with an x4 model in overlapping tiles ->
restore every face with GFPGAN on an FFHQ-aligned 512px crop and paste it back with a feathered mask ->
resize to the target size (4K on the long side by default) -> a light final sharpen."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import models

FFHQ_512 = np.array([[192.98138, 239.94708], [318.90277, 240.1936], [256.63416, 314.01935],
                     [201.26117, 371.41043], [313.08905, 371.15118]], np.float32)


@dataclass
class Face:
    box: np.ndarray        # x1, y1, x2, y2
    kps: np.ndarray        # 5 x 2: eyes, nose, mouth corners
    score: float


# ------------------------------------------------------------------ super-resolution
def upscale(bgr: np.ndarray, model: str = "clear_reality_x4", tile: int = 192, pad: int = 12) -> np.ndarray:
    """x4 (or x2) super-resolution in overlapping tiles so memory stays flat for any image size."""
    sess = models.session(model)
    scale = 2 if model.endswith("x2") else 4
    h, w = bgr.shape[:2]
    rgb = bgr[:, :, ::-1].astype(np.float32) / 255.0
    src = np.pad(rgb, ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    out = np.zeros((h * scale, w * scale, 3), np.float32)
    name = sess.get_inputs()[0].name
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            th, tw = min(tile, h - y), min(tile, w - x)
            crop = src[y:y + th + 2 * pad, x:x + tw + 2 * pad]
            ch, cw = crop.shape[:2]
            if ch % 4 or cw % 4:                          # pixel-unshuffle models need sizes divisible by 2/4
                crop = np.pad(crop, ((0, -ch % 4), (0, -cw % 4), (0, 0)), mode="reflect")
            inp = np.ascontiguousarray(crop.transpose(2, 0, 1)[None])
            res = sess.run(None, {name: inp})[0][0].transpose(1, 2, 0)
            p = pad * scale
            out[y * scale:(y + th) * scale, x * scale:(x + tw) * scale] = res[p:p + th * scale, p:p + tw * scale]
    return (np.clip(out, 0, 1) * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]


# ------------------------------------------------------------------ face detection (YOLOv8n-face, 5 landmarks)
def _nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    idx = cv2.dnn.NMSBoxes([[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes],
                           scores.tolist(), 0.0, iou)
    return [int(i) for i in np.array(idx).reshape(-1)]


def detect_faces(bgr: np.ndarray, min_score: float = 0.45) -> list[Face]:
    sess = models.session("yoloface_8n")
    h, w = bgr.shape[:2]
    r = min(640 / h, 640 / w)
    small = cv2.resize(bgr, (max(1, round(w * r)), max(1, round(h * r))), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((640, 640, 3), np.float32)
    canvas[:small.shape[0], :small.shape[1]] = small[:, :, ::-1]
    pred = sess.run(None, {sess.get_inputs()[0].name: (canvas / 255.0).transpose(2, 0, 1)[None]})[0][0].T
    keep = pred[:, 4] >= min_score
    pred = pred[keep]
    if not len(pred):
        return []
    cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1) / r
    kps = pred[:, 5:20].reshape(-1, 5, 3)[:, :, :2] / r
    faces = [Face(boxes[i], kps[i], float(pred[i, 4])) for i in _nms(boxes, pred[:, 4], 0.4)]
    return sorted(faces, key=lambda f: -(f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))


# ------------------------------------------------------------------ face restoration (GFPGAN 1.4)
def _restore_crop(crop_bgr: np.ndarray, model: str) -> np.ndarray:
    sess = models.session(model)
    x = (crop_bgr[:, :, ::-1].astype(np.float32) / 255.0 - 0.5) / 0.5
    y = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0]
    y = (np.clip(y, -1, 1) + 1) / 2
    return (y.transpose(1, 2, 0) * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]


def _feather_mask(size: int = 512) -> np.ndarray:
    m = np.zeros((size, size), np.float32)
    b = int(size * 0.06)
    m[b:size - b, b:size - b] = 1.0
    k = int(size * 0.08) | 1
    return cv2.GaussianBlur(m, (k, k), 0)


_MASK = _feather_mask()


def restore_faces(img: np.ndarray, faces: list[Face], scale: float, model: str = "gfpgan_1.4",
                  blend: float = 0.85, min_size: int = 14, max_faces: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """`faces` were found on the original; `scale` maps them onto `img` (the upscaled frame).
    Returns the frame and a soft mask of where faces were restored."""
    out = img.copy()
    H, W = img.shape[:2]
    where = np.zeros((H, W), np.float32)
    for f in faces[:max_faces]:
        if min(f.box[2] - f.box[0], f.box[3] - f.box[1]) < min_size:
            continue
        kps = f.kps * scale
        M, _ = cv2.estimateAffinePartial2D(kps, FFHQ_512, method=cv2.LMEDS)
        if M is None:
            continue
        crop = cv2.warpAffine(out, M, (512, 512), flags=cv2.INTER_AREA if scale > 2 else cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
        fixed = _restore_crop(crop, model)
        if blend < 1.0:
            fixed = cv2.addWeighted(fixed, blend, crop, 1 - blend, 0)
        Mi = cv2.invertAffineTransform(M)
        back = cv2.warpAffine(fixed, Mi, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        mask = cv2.warpAffine(_MASK, Mi, (W, H), flags=cv2.INTER_LINEAR)
        where = np.maximum(where, mask)
        mask = mask[..., None]
        out = (back.astype(np.float32) * mask + out.astype(np.float32) * (1 - mask)).astype(np.uint8)
    return out, where


# ------------------------------------------------------------------ whole pipeline
def target_size(w: int, h: int, long_side: int = 3840, max_scale: float = 4.0) -> tuple[int, int]:
    s = min(max_scale, long_side / max(w, h))
    s = max(s, 1.0)
    return int(round(w * s / 2) * 2), int(round(h * s / 2) * 2)


def sharpen(img: np.ndarray, amount: float = 0.35, sigma: float = 1.2) -> np.ndarray:
    if amount <= 0:
        return img
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


@dataclass
class Look:
    """The '4K' finish: crisp edges, punchy contrast and rich colour, without halos, grain or orange skin.

    detail     edge-gated small-radius sharpening (flat areas and noise below `gate` are left alone)
    clarity    local contrast over an edge-aware (bilateral) base, so bright outlines don't glow
    vibrance   boosts dull colours more than saturated ones; skin hues get only `skin_sat` of it
    contrast   gentle S-curve; `lift` brightens midtones a touch; whites are neutralised"""
    detail: float = 1.1
    gate: float = 4.0          # /255: high-pass below this is treated as noise
    clarity: float = 0.22
    vibrance: float = 0.7
    saturation: float = 0.3
    skin_sat: float = 0.55     # share of the colour boost that skin hues receive
    contrast: float = 0.28
    lift: float = 0.0
    neutral_whites: bool = False
    face_detail: float = 0.45  # share of detail/clarity on restored faces (keeps skin clean)


def _edge_aware_base(Lf: np.ndarray, scale: float = 0.25) -> np.ndarray:
    small = cv2.resize(Lf, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    base = cv2.bilateralFilter(small, d=0, sigmaColor=0.08, sigmaSpace=max(small.shape) / 90)
    return cv2.resize(base, (Lf.shape[1], Lf.shape[0]), interpolation=cv2.INTER_LINEAR)


def grade(img: np.ndarray, look: Look = Look(), faces: np.ndarray | None = None) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    Lf, a, b = lab[..., 0] / 255.0, lab[..., 1] - 128.0, lab[..., 2] - 128.0
    k = 1.0 if faces is None else 1.0 - (1.0 - look.face_detail) * np.clip(faces, 0, 1)

    if look.neutral_whites:                                   # near-white, low-chroma pixels should be white
        chroma = np.hypot(a, b)
        sel = (Lf > np.percentile(Lf, 92)) & (chroma < 14)
        if sel.sum() > 500:
            da, db = np.clip(a[sel].mean(), -6, 6), np.clip(b[sel].mean(), -6, 6)
            w = np.clip((Lf - 0.55) / 0.35, 0, 1)             # correct highlights, leave shadows' colour alone
            a, b = a - 0.85 * da * w, b - 0.85 * db * w
    if look.lift:
        Lf = np.power(np.clip(Lf, 0, 1), 1 - look.lift)
    if look.contrast:
        Lf = Lf + look.contrast * (Lf - 0.5) * (1 - np.abs(2 * Lf - 1)) * 2
    if look.clarity:
        Lf = Lf + look.clarity * k * (Lf - _edge_aware_base(Lf))
    if look.detail:
        hp = Lf - cv2.GaussianBlur(Lf, (0, 0), 0.9)
        g0 = look.gate / 255.0
        gatew = np.clip((np.abs(hp) - g0) / (2 * g0), 0, 1)  # noise-level ripples are not amplified
        Lf = Lf + look.detail * k * gatew * hp
    L = np.clip(Lf, 0, 1) * 255.0

    if look.vibrance or look.saturation:
        chroma = np.hypot(a, b)
        hue = np.degrees(np.arctan2(b, a))
        skin = np.clip(1 - np.abs(hue - 50) / 30, 0, 1) * np.clip(chroma / 8, 0, 1) * np.clip((40 - chroma) / 15, 0, 1)
        gain = (1 + look.saturation) * (1 + look.vibrance * (1 - np.clip(chroma / 60.0, 0, 1))) - 1
        gain = gain * (1 - (1 - look.skin_sat) * skin)
        bright_neutral = np.clip((Lf - 0.7) / 0.2, 0, 1) * np.clip(1 - chroma / 18, 0, 1)
        gain = gain * (1 - 0.8 * bright_neutral)                 # whites stay white, not cream
        a, b = a * (1 + gain), b * (1 + gain)
    out = np.dstack([L, a + 128.0, b + 128.0])
    return cv2.cvtColor(np.clip(out + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def restore(bgr: np.ndarray, long_side: int = 3840, sr_model: str = "real_esrgan_x4",
            face_model: str = "gpen_bfr_512", face_blend: float = 0.85,
            work_side: int = 960) -> tuple[np.ndarray, np.ndarray | None]:
    """Super-resolution + faces. The input is first brought to `work_side` on its long edge: phone screenshots
    and stream grabs carry far less real detail than their pixel count, and an x4 model reconstructs much
    crisper edges from the true-detail size than from a soft, oversized image."""
    h, w = bgr.shape[:2]
    if max(h, w) > work_side:
        r = work_side / max(h, w)
        bgr = cv2.resize(bgr, (round(w * r), round(h * r)), interpolation=cv2.INTER_AREA)
        h, w = bgr.shape[:2]
    faces = detect_faces(bgr) if face_model else []
    up = upscale(bgr, sr_model)
    where = None
    if faces:
        up, where = restore_faces(up, faces, up.shape[1] / w, face_model, face_blend)
    tw, th = target_size(w, h, long_side)
    if (tw, th) != (up.shape[1], up.shape[0]):
        inter = cv2.INTER_AREA if tw < up.shape[1] else cv2.INTER_LANCZOS4
        up = cv2.resize(up, (tw, th), interpolation=inter)
        if where is not None:
            where = cv2.resize(where, (tw, th), interpolation=cv2.INTER_LINEAR)
    return up, where


def softness(bgr: np.ndarray) -> float:
    """Mean error of a half-size round trip: low = the pixels hold little real detail (soft/blurry/upscaled)."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    d = cv2.resize(g, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    return float(np.mean(np.abs(g - cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC))))


def choose(bgr: np.ndarray, long_side: int = 3840) -> dict:
    """Soft or small inputs: shrink to the true-detail size and rebuild with the strong (slow) ESRGAN model.
    Big, already sharp photos: keep up to long_side/2 of real detail and use the fast SPAN model."""
    longest = max(bgr.shape[:2])
    if longest <= long_side // 4 or softness(bgr) < 2.5:
        return {"sr_model": "real_esrgan_x4", "work_side": long_side // 4}
    return {"sr_model": "clear_reality_x4", "work_side": min(longest, long_side // 2)}


def enhance_image(img: np.ndarray, look: Look = Look(), **kw) -> np.ndarray:
    """BGR or BGRA in, same channel count out (alpha is resized alongside)."""
    alpha = img[:, :, 3] if img.ndim == 3 and img.shape[2] == 4 else None
    bgr = img[:, :, :3] if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    kw = {**choose(bgr, kw.get("long_side", 3840)), **kw}
    up, faces = restore(bgr, **kw)
    out = grade(up, look, faces)
    if alpha is not None:
        a = cv2.resize(alpha, (out.shape[1], out.shape[0]), interpolation=cv2.INTER_LANCZOS4)
        out = np.dstack([out, a])
    return out


def before_after(before: np.ndarray, after: np.ndarray, height: int = 1600, label: bool = True,
                 max_sum: int = 9000) -> np.ndarray:
    """Comparison under a label bar ('before' is plain bicubic). Side by side for tall/square images, stacked
    for wide ones, and always within Telegram's sendPhoto limit (width + height <= 10000)."""
    before, after = before[:, :, :3], after[:, :, :3]
    ratio = after.shape[1] / after.shape[0]
    side = ratio <= 1.3
    if side:
        height = int(min(height, (max_sum - 12) / (2 * ratio + 1.06)))
        size = lambda im: (max(1, round(height * ratio)), height)
    else:
        width = int(min(height * 1.25, (max_sum - 12) / (1 + 2.12 / ratio)))
        size = lambda im: (width, max(1, round(width / ratio)))

    def fit(im):
        tw, th = size(im)
        return cv2.resize(im, (tw, th), interpolation=cv2.INTER_CUBIC if tw > im.shape[1] else cv2.INTER_AREA)
    a, b = fit(before), fit(after)
    bar_h = max(36, min(a.shape[:2]) // 18)
    fs = bar_h / 40

    def bar(width, items):
        im = np.full((bar_h, width, 3), 20, np.uint8)
        for text, x0, w in items:
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, fs, 2)
            cv2.putText(im, text, (x0 + (w - tw) // 2, (bar_h + th) // 2), cv2.FONT_HERSHEY_DUPLEX, fs,
                        (255, 255, 255), 2, cv2.LINE_AA)
        return im
    if side:
        out = np.hstack([a, np.full((a.shape[0], 12, 3), 255, np.uint8), b])
        if label:
            out = np.vstack([bar(out.shape[1], [("BEFORE", 0, a.shape[1]), ("AFTER", a.shape[1] + 12, b.shape[1])]),
                             out])
        return out
    gap = np.full((12, a.shape[1], 3), 255, np.uint8)
    if label:
        return np.vstack([bar(a.shape[1], [("BEFORE", 0, a.shape[1])]), a, gap,
                          bar(b.shape[1], [("AFTER", 0, b.shape[1])]), b])
    return np.vstack([a, gap, b])
