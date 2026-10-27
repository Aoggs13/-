"""Skin image -> idle / fly / attack frames posed like the black reaper."""
import time
from dataclasses import dataclass

import cv2
import numpy as np

from . import animate, imageio, layers as lay, segment

GIF_MS = {"idle": 110, "fly": 80, "attack": 75}


@dataclass
class Result:
    frames: list          # [(filename, BGRA)] in animation order
    gifs: dict            # anim -> GIF bytes
    zip_bytes: bytes
    sheet: bytes          # PNG contact sheet
    seconds: float
    info: dict


def _prepare(data):
    img = imageio.decode(data)
    rgba = imageio.remove_background(img)
    rgba = imageio.crop_to_content(rgba, 8)
    # tiny skins segment badly; bring the skull to a workable size
    h = rgba.shape[0]
    if h < 300:
        f = 300.0 / h
        rgba = cv2.resize(rgba, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    return rgba


def contact_sheet(named, cols=8, bg=(255, 255, 255)):
    tiles = []
    for _, fr in named:
        a = fr[..., 3:4].astype(np.float32) / 255
        tiles.append((fr[..., :3].astype(np.float32) * a + np.array(bg, np.float32) * (1 - a)).astype(np.uint8))
    h, w = tiles[0].shape[:2]
    sc = min(1.0, 240.0 / h)
    tiles = [cv2.resize(t, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA) for t in tiles]
    h, w = tiles[0].shape[:2]
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * h, cols * w, 3), bg, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = t
        cv2.putText(sheet, named[i][0][:-4], (c * w + 4, r * h + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 90, 90), 1)
    ok, enc = cv2.imencode(".png", sheet)
    return enc.tobytes()


def run(data: bytes) -> Result:
    t0 = time.time()
    rgba = _prepare(data)
    seg = segment.segment(rgba)
    L = lay.build(rgba, seg)
    H, W = rgba.shape[:2]
    pad = int(0.5 * max(H, W))
    frames = animate.render(L, seg, (H + 2 * pad, W + 2 * pad), (pad, pad))
    frames = animate.crop_frames(frames, 6)
    seqs = animate.sequences()
    named = []
    gifs = {}
    for anim in ("idle", "fly", "attack"):
        seq = seqs[anim]
        for i, src in enumerate(seq):
            named.append(("%s_%d.png" % (anim, i + 1), frames[src]))
        order = [frames[s] for s in seq]
        if anim in ("idle", "fly"):
            order = order + order[-2:0:-1]      # ping-pong loop
        gifs[anim] = animate.gif_bytes(order, GIF_MS[anim])
    files = [("frames/" + n, animate.png_bytes(f)) for n, f in named]
    for p in animate.PARTS:
        files.append(("layers/%s.png" % p, animate.png_bytes(L.get(p))))
    for anim, g in gifs.items():
        files.append(("preview/%s.gif" % anim, g))
    info = dict(scale=round(seg.scale, 3), scythe_in_front=seg.scythe_in_front, skull_found=seg.skull is not None,
                ref_frame=animate.pick_ref_frame(seg), size=list(named[0][1].shape[1::-1]))
    return Result(frames=named, gifs=gifs, zip_bytes=animate.make_zip(files),
                  sheet=contact_sheet(named), seconds=time.time() - t0, info=info)
