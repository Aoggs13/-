"""Hole filling with LaMa (ONNX, CPU); falls back to OpenCV Telea when the model is missing."""
import logging
import os
import threading
import urllib.request

import cv2
import numpy as np

log = logging.getLogger(__name__)

LAMA_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
            "inpainting_lama/inpainting_lama_2025jan.onnx")
LAMA_SIZE = 92591623
_lock = threading.Lock()
_session = None


def models_dir():
    return os.environ.get("MODELS_DIR", os.path.join(os.path.dirname(__file__), "..", "models"))


def lama_path():
    return os.path.join(models_dir(), "lama.onnx")


def ensure_model():
    """Download LaMa once; returns the path or None when it cannot be fetched."""
    path = lama_path()
    if os.path.exists(path) and os.path.getsize(path) == LAMA_SIZE:
        return path
    if os.environ.get("EVOSKIN_NO_DOWNLOAD"):
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    try:
        log.info("downloading LaMa model")
        urllib.request.urlretrieve(LAMA_URL, tmp)
        if os.path.getsize(tmp) != LAMA_SIZE:
            raise IOError("unexpected size %d" % os.path.getsize(tmp))
        os.replace(tmp, path)
        return path
    except Exception as e:  # network or disk problem: keep working with the classic fill
        log.warning("LaMa download failed: %s", e)
        if os.path.exists(tmp):
            os.remove(tmp)
        return None


def _get_session():
    global _session
    if os.environ.get("EVOSKIN_LAMA", "1") == "0":   # small hosts (<1 GB RAM): classic fill only
        return None
    with _lock:
        if _session is None:
            path = ensure_model()
            if path is None:
                return None
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.log_severity_level = 3
            _session = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        return _session


def warm():
    """Fetch and load the model before the bot starts taking jobs."""
    return _get_session() is not None


def _lama(bgr, mask):
    """bgr uint8 HxW, mask bool HxW (True = fill). Works on any size by resizing to 512."""
    sess = _get_session()
    if sess is None:
        return None
    H, W = mask.shape
    im = cv2.resize(bgr, (512, 512), interpolation=cv2.INTER_AREA if max(H, W) > 512 else cv2.INTER_CUBIC)
    mk = cv2.resize(mask.astype(np.uint8), (512, 512), interpolation=cv2.INTER_NEAREST)
    mk = cv2.dilate(mk, np.ones((3, 3), np.uint8))
    x = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    m = mk.astype(np.float32)[None, None]
    with _lock:
        out = sess.run(None, {"image": x, "mask": m})[0][0]
    out = np.clip(out.transpose(1, 2, 0), 0, 255).astype(np.uint8)
    out = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    return cv2.resize(out, (W, H), interpolation=cv2.INTER_CUBIC if max(H, W) > 512 else cv2.INTER_AREA)


def fill(bgr, mask, max_side=512):
    """Fill `mask` in `bgr`; LaMa runs on a context crop around the holes."""
    if not mask.any():
        return bgr.copy()
    out = bgr.copy()
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    # group holes into crops that fit the model window well
    boxes = [stats[i, :4] for i in range(1, n)]
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    groups = [(x0, y0, x1, y1)] if max(x1 - x0, y1 - y0) * 1.6 <= max_side else \
        [(b[0], b[1], b[0] + b[2], b[1] + b[3]) for b in boxes]
    H, W = mask.shape
    for gx0, gy0, gx1, gy1 in groups:
        w, h = gx1 - gx0, gy1 - gy0
        side = int(max(w, h) * 1.6) + 16
        cx, cy = (gx0 + gx1) // 2, (gy0 + gy1) // 2
        cx0, cy0 = max(cx - side // 2, 0), max(cy - side // 2, 0)
        cx1, cy1 = min(cx0 + side, W), min(cy0 + side, H)
        sub_m = mask[cy0:cy1, cx0:cx1]
        if not sub_m.any():
            continue
        res = _lama(out[cy0:cy1, cx0:cx1], sub_m)
        if res is None:
            res = cv2.inpaint(out[cy0:cy1, cx0:cx1], sub_m.astype(np.uint8), 5, cv2.INPAINT_TELEA)
        region = out[cy0:cy1, cx0:cx1]
        region[sub_m] = res[sub_m]
    return out
