"""The pipeline must reproduce the black reaper's own frames when fed the black reaper idle pose."""

import io
import os
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVOSKIN_NO_DOWNLOAD", "1")   # tests never hit the network; LaMa is used only if present

from evoskin import animate, layers, pipeline, reference, segment  # noqa: E402

BR = ROOT / "tools" / "black_reaper"


def _bad_fraction(out, tgt):
    fo = out.astype(np.float32) / 255
    ft = tgt.astype(np.float32) / 255
    po = np.dstack([fo[..., :3] * fo[..., 3:4], fo[..., 3:4]])
    pt = np.dstack([ft[..., :3] * ft[..., 3:4], ft[..., 3:4]])
    bad = np.abs(po - pt).max(2) > 0.25
    union = (fo[..., 3] > 0.5) | (ft[..., 3] > 0.5)
    return bad.sum() / union.sum()


@pytest.fixture(scope="module")
def br_render():
    rgba = reference.ref_image()
    seg = segment.segment(rgba)
    L = layers.build(rgba, seg)
    return seg, animate.render(L, seg, canvas=(0, 0, rgba.shape[1], rgba.shape[0]))


def test_reference_segmentation(br_render):
    seg, _ = br_render
    assert seg.skull is not None
    assert abs(seg.scale - 1.0) < 0.02
    assert not seg.scythe_in_front
    for k in (segment.HEAD, segment.BODY, segment.BACK_HAND, segment.FRONT_HAND, segment.SCYTHE):
        assert (seg.labels == k).sum() > 100


def test_reproduces_black_reaper(br_render):
    _, frames = br_render
    assert len(frames) == 19
    bad = {n: _bad_fraction(frames[n], cv2.imread(str(BR / f"{n}.png"), cv2.IMREAD_UNCHANGED)) for n in frames}
    assert np.mean(list(bad.values())) < 0.05, bad
    for n, v in bad.items():
        limit = 0.12 if n in ("attack_2", "attack_4", "attack_6") else 0.06   # raised-arm frames redraw the sleeve
        assert v < limit, (n, v)


def test_full_run_on_scaled_skin():
    rgba = reference.ref_image()
    big = cv2.resize(rgba, None, fx=1.7, fy=1.7, interpolation=cv2.INTER_CUBIC)
    ok, enc = cv2.imencode(".png", big)
    res = pipeline.run(enc.tobytes())
    assert [n for n, _ in res.frames] == [f"{a}_{i}.png" for a, k in (("idle", 6), ("fly", 5), ("attack", 8))
                                         for i in range(1, k + 1)]
    sizes = {f.shape for _, f in res.frames}
    assert len(sizes) == 1                       # every frame on the same canvas
    assert res.info["skull_found"]
    names = zipfile.ZipFile(io.BytesIO(res.zip_bytes)).namelist()
    assert "frames/attack_8.png" in names and "layers/scythe.png" in names and "layers/sleeve.png" in names
    assert not [n for n in names if n.endswith(".gif")]          # frames only, no animations


def test_white_background_photo():
    rgba = reference.ref_image()
    al = rgba[..., 3:4].astype(np.float32) / 255
    white = (rgba[..., :3] * al + 255 * (1 - al)).astype(np.uint8)
    white = cv2.resize(white, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    ok, enc = cv2.imencode(".jpg", white, [cv2.IMWRITE_JPEG_QUALITY, 85])
    res = pipeline.run(enc.tobytes())
    assert res.info["skull_found"]
    assert len(res.frames) == 19


def test_rejects_garbage():
    with pytest.raises(ValueError):
        pipeline.run(b"not an image")
