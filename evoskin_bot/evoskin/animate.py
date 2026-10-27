"""Pose the layers like the black reaper frames and write PNG frames, GIF previews and a ZIP."""
import io
import zipfile
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from . import reference as ref
from .layers import sleeve_sprite

PARTS = ["scythe", "body", "head", "back_hand", "front_hand"]


def rot(theta, pivot, dst):
    R = cv2.getRotationMatrix2D((float(pivot[0]), float(pivot[1])), float(theta), 1.0)
    R[:, 2] += np.asarray(dst, float) - np.asarray(pivot, float)
    return np.vstack([R, [0, 0, 1]])


def h3(A):
    return np.vstack([A, [0, 0, 1]])


def br_transform(frame, part):
    """BR rig transform (3x3) for `part` in `frame`, mapping the idle_6 pose to the frame."""
    rig = ref.rig()
    f = rig["frames"][frame]
    if part == "front_hand" and f["front_hand"] is None:
        part = "scythe"
    th, x, y = f[part]
    pv = rig["pivots"][part]
    return rot(th, pv, (x, y))


def pick_ref_frame(seg):
    """BR frame whose scythe angle matches the skin's pose best."""
    rig = ref.rig()
    ang_skin = np.degrees(np.arctan2(seg.axis_d[1], seg.axis_d[0]))
    bot = np.array(rig["pivots"]["scythe"]); top = np.array(rig["handle_top"])
    ang_br = np.degrees(np.arctan2(top[1] - bot[1], top[0] - bot[0]))
    want = -(ang_skin - ang_br)
    cands = [n for n in rig["frames"] if rig["frames"][n]["order"] == "ref"]
    return min(cands, key=lambda n: abs(rig["frames"][n]["scythe"][0] - want))


def hand_rel(frame):
    """Rotation of the front hand relative to the scythe in a BR frame (0 when it just follows)."""
    f = ref.rig()["frames"][frame]
    return 0.0 if f["front_hand"] is None else f["front_hand"][0] - f["scythe"][0]


@lru_cache(maxsize=1)
def calibration():
    """Anchors measured on the black reaper itself with the same segmentation as skins,
    so systematic measuring offsets cancel out."""
    from . import segment
    seg = segment.segment(ref.ref_image())
    return dict(bottom=np.asarray(seg.axis_p, float), top=np.asarray(seg.axis_p + 100 * seg.axis_d, float),
                **{k: np.asarray(v, float) for k, v in seg.anchors.items()})


def part_G(seg, part, ref_frame):
    """3x3 similarity: black reaper coordinates in the `ref_frame` pose -> skin pixels."""
    rig = ref.rig()
    s = seg.scale
    Tr = br_transform(ref_frame, part)
    if part == "head":
        return h3(seg.S_head) @ np.linalg.inv(Tr)
    cal = calibration()
    if part == "scythe":
        b = (Tr @ np.array([*cal["bottom"], 1.0]))[:2]
        t = (Tr @ np.array([*cal["top"], 1.0]))[:2]
        ang_br = np.degrees(np.arctan2(t[1] - b[1], t[0] - b[0]))
        ang_s = np.degrees(np.arctan2(seg.axis_d[1], seg.axis_d[0]))
        R = cv2.getRotationMatrix2D((0.0, 0.0), -(ang_s - ang_br), s)
        R[:, 2] = np.asarray(seg.axis_p, float) - R[:, :2] @ b
        return h3(R)
    a = (Tr @ np.array([*cal[part], 1.0]))[:2]
    c = np.asarray(seg.anchors[part], float)
    return np.array([[s, 0, c[0] - s * a[0]], [0, s, c[1] - s * a[1]], [0, 0, 1.0]])


def frame_matrices(seg, frame, ref_frame):
    """Per-part 3x3 matrices taking skin input pixels to their place in `frame`.

    G maps the black reaper (posed as `ref_frame`) onto the skin, so a skin pixel x of
    part p goes to G . T_frame . T_ref^-1 . G^-1 (x).  The front hand stays on the handle:
    it moves with the scythe plus the hand's own extra turn about its centre."""
    out = {}
    for p in ("scythe", "body", "head", "back_hand"):
        G = part_G(seg, p, ref_frame)
        out[p] = G @ br_transform(frame, p) @ np.linalg.inv(br_transform(ref_frame, p)) @ np.linalg.inv(G)
    c = seg.anchors["front_hand"]
    turn = h3(cv2.getRotationMatrix2D((float(c[0]), float(c[1])), hand_rel(frame) - hand_rel(ref_frame), 1.0))
    out["front_hand"] = out["scythe"] @ turn
    return out


def to_pm(img):
    f = img.astype(np.float32) / 255
    return np.dstack([f[..., :3] * f[..., 3:4], f[..., 3:4]])


def from_pm(pm):
    a = pm[..., 3:4]
    rgb = np.where(a > 1e-4, pm[..., :3] / np.maximum(a, 1e-4), 0)
    return (np.clip(np.dstack([rgb, a]), 0, 1) * 255 + 0.5).astype(np.uint8)


def render(layers, seg, out_shape, offset, scale_out=1.0):
    """Render all 19 frames. Returns dict frame_name -> BGRA (uncropped canvas)."""
    rig = ref.rig()
    ref_frame = pick_ref_frame(seg)
    pms = {p: to_pm(layers.get(p)) for p in PARTS}
    H, W = out_shape
    O = np.array([[scale_out, 0, offset[0]], [0, scale_out, offset[1]], [0, 0, 1]])
    sl = rig["sleeve"]
    frames = {}
    for name, f in rig["frames"].items():
        M = frame_matrices(seg, name, ref_frame)
        warped = {}
        for p in PARTS:
            A = (O @ M[p])[:2]
            warped[p] = cv2.warpAffine(pms[p], A, (W, H), flags=cv2.INTER_CUBIC, borderValue=0)
            warped[p] = np.clip(warped[p], 0, 1)
            warped[p][..., :3] = np.minimum(warped[p][..., :3], warped[p][..., 3:4])
        order = f["order"]
        if order == "ref":
            order = (["body", "scythe"] if seg.scythe_in_front else ["scythe", "body"]) + ["head", "back_hand", "front_hand"]
        if "sleeve" in order:
            Gb = part_G(seg, "body", ref_frame)
            sh = (O @ Gb @ br_transform(name, "body") @ np.array([*sl["shoulder"], 1.0]))[:2]
            wr0 = np.asarray(seg.anchors["front_hand"], float) + seg.scale * np.array(sl["wrist_offset"])
            wr = (O @ M["front_hand"] @ np.array([*wr0, 1.0]))[:2]
            sp = sleeve_sprite(layers.body, seg, sh, wr, sl["radius"] * seg.scale * scale_out, (H, W))
            warped["sleeve"] = to_pm(sp)
        acc = np.zeros((H, W, 4), np.float32)
        for p in order:
            l = warped[p]
            acc = l + acc * (1 - l[..., 3:4])
        frames[name] = from_pm(acc)
    return frames


def crop_frames(frames, margin):
    alpha = np.zeros(next(iter(frames.values())).shape[:2], bool)
    for fr in frames.values():
        alpha |= fr[..., 3] > 0
    ys, xs = np.nonzero(alpha)
    x0, y0 = max(xs.min() - margin, 0), max(ys.min() - margin, 0)
    x1, y1 = xs.max() + margin + 1, ys.max() + margin + 1
    return {k: v[y0:y1, x0:x1] for k, v in frames.items()}


def sequences():
    return ref.rig()["sequences"]


def to_pil(bgra):
    return Image.fromarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA))


def gif_bytes(frames_bgra, durations, bg=(255, 255, 255)):
    ims = []
    for fr in frames_bgra:
        a = fr[..., 3:4].astype(np.float32) / 255
        rgb = fr[..., :3].astype(np.float32) * a + np.array(bg[::-1], np.float32) * (1 - a)
        ims.append(Image.fromarray(cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_BGR2RGB)).convert("P", palette=Image.ADAPTIVE, colors=255))
    buf = io.BytesIO()
    ims[0].save(buf, format="GIF", save_all=True, append_images=ims[1:], duration=durations, loop=0, disposal=2)
    return buf.getvalue()


def png_bytes(bgra):
    ok, enc = cv2.imencode(".png", bgra)
    return enc.tobytes()


def make_zip(named_pngs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in named_pngs:
            z.writestr(name, data)
    return buf.getvalue()
