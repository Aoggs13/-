"""Loading skins and removing a flat background."""
import cv2
import numpy as np


def decode(data: bytes) -> np.ndarray:
    """Decode image bytes to BGRA uint8. Raises ValueError for non-images."""
    buf = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("not an image")
    if img.dtype != np.uint8:
        img = (img / 257).astype(np.uint8) if img.dtype == np.uint16 else img.astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img


def remove_background(img: np.ndarray) -> np.ndarray:
    """Keep real transparency; otherwise cut away the flat colour touching the borders."""
    if (img[..., 3] < 250).mean() > 0.02:
        out = img.copy()
        out[out[..., 3] < 8] = 0
        return out
    bgr = img[..., :3]
    border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]]).astype(np.float32)
    bgc = np.median(border, 0)
    diff = np.abs(bgr.astype(np.float32) - bgc).max(2)
    cand = (diff < 30).astype(np.uint8)
    n, lab = cv2.connectedComponents(cand, connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge = edge[edge > 0]
    bg = np.isin(lab, edge) & (cand > 0)
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # anti-aliased rim: pixels next to the background get alpha from their distance to the bg colour
    ring = cv2.dilate(bg.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~bg
    soft = np.clip(diff / 90.0, 0.3, 1.0)
    alpha[ring] = (soft[ring] * 255).astype(np.uint8)
    # un-blend the rim colour from the background
    a = alpha[..., None].astype(np.float32) / 255
    col = bgr.astype(np.float32)
    unbl = np.where(a > 0, (col - bgc * (1 - a)) / np.maximum(a, 1e-3), 0)
    col = np.where(ring[..., None], np.clip(unbl, 0, 255), col)
    out = np.dstack([col.astype(np.uint8), alpha])
    out[alpha == 0] = 0
    return out


def crop_to_content(rgba: np.ndarray, pad: int):
    """Crop to the non-transparent bbox and add `pad` empty pixels on every side."""
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    if len(xs) == 0:
        raise ValueError("empty image")
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    out = np.zeros((y1 - y0 + 2 * pad, x1 - x0 + 2 * pad, 4), np.uint8)
    out[pad:pad + y1 - y0, pad:pad + x1 - x0] = rgba[y0:y1, x0:x1]
    return out
