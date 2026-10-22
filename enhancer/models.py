"""Model registry: where each ONNX model comes from, and lazy, cached onnxruntime sessions.

Weights are downloaded on first use from public GitHub release assets (the FaceFusion asset mirror of the
original Real-ESRGAN / SPAN / GFPGAN / YOLO-face weights) into MODELS_DIR, so the repository stays small."""

from __future__ import annotations

import logging
import os
import threading
import urllib.request
from pathlib import Path

import onnxruntime as ort

log = logging.getLogger(__name__)

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parent.parent / "models"))
_BASE = "https://github.com/facefusion/facefusion-assets/releases/download"
URLS = {
    "clear_reality_x4": f"{_BASE}/models-3.0.0/clear_reality_x4.onnx",
    "span_kendata_x4": f"{_BASE}/models-3.0.0/span_kendata_x4.onnx",
    "real_esrgan_x4": f"{_BASE}/models-3.0.0/real_esrgan_x4.onnx",
    "real_esrgan_x2": f"{_BASE}/models-3.0.0/real_esrgan_x2.onnx",
    "gfpgan_1.4": f"{_BASE}/models-3.0.0/gfpgan_1.4.onnx",
    "gpen_bfr_512": f"{_BASE}/models-3.0.0/gpen_bfr_512.onnx",
    "yoloface_8n": f"{_BASE}/models-3.0.0/yoloface_8n.onnx",
}

_lock = threading.Lock()
_sessions: dict[str, ort.InferenceSession] = {}


def threads() -> int:
    return int(os.environ.get("ORT_THREADS", os.cpu_count() or 2))


def path(name: str) -> Path:
    p = MODELS_DIR / f"{name}.onnx"
    if not p.exists():
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        log.info("downloading model %s", name)
        urllib.request.urlretrieve(URLS[name], tmp)
        tmp.rename(p)
    return p


def session(name: str) -> ort.InferenceSession:
    with _lock:
        s = _sessions.get(name)
        if s is None:
            o = ort.SessionOptions()
            o.intra_op_num_threads = threads()
            o.inter_op_num_threads = 1
            o.log_severity_level = 3
            o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            s = ort.InferenceSession(str(path(name)), o, providers=["CPUExecutionProvider"])
            _sessions[name] = s
        return s


def warm(names=("clear_reality_x4", "gfpgan_1.4", "yoloface_8n")) -> None:
    for n in names:
        session(n)
