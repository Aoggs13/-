"""Pose the layers like the black reaper frames and write PNG frames, GIF previews and a ZIP."""
import io
import zipfile
from functools import lru_cache

import cv2
import numpy as np

from . import reference as ref
from .layers import sleeve_tube

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


def two_point(a0, b0, a1, b1):
    """Affine map taking segment a0-b0 onto a1-b1: rotate, stretch only along the segment."""
    a0, b0, a1, b1 = (np.asarray(v, float) for v in (a0, b0, a1, b1))
    v0, v1 = b0 - a0, b1 - a1
    n0 = np.linalg.norm(v0)
    if n0 < 1e-6:
        return np.array([[1.0, 0, a1[0] - a0[0]], [0, 1.0, a1[1] - a0[1]], [0, 0, 1]])
    ang = np.arctan2(v1[1], v1[0]) - np.arctan2(v0[1], v0[0])
    k = np.linalg.norm(v1) / n0
    c, sn = np.cos(ang), np.sin(ang)
    e = v0 / n0
    B = np.stack([e, [-e[1], e[0]]], 1)
    M = np.array([[c, -sn], [sn, c]]) @ B @ np.diag([k, 1.0]) @ B.T
    return np.vstack([np.hstack([M, (a1 - M @ a0)[:, None]]), [0, 0, 1]])


def frame_plan(layers, seg, name, ref_frame):
    """Draw list for one frame: [(layer name, image, 3x3 matrix)] back to front."""
    f = ref.rig()["frames"][name]
    M = frame_matrices(seg, name, ref_frame)
    order = f["order"]
    if order == "ref":
        order = (["body", "scythe"] if seg.scythe_in_front else ["scythe", "body"]) + ["head", "back_hand", "front_hand"]
    raised = "sleeve" in order
    plan = []
    for p in order:
        if p == "sleeve":
            if layers.sleeve_axis is None:
                continue
            sh, wr = layers.sleeve_axis
            sh_f = (M["body"] @ np.array([*sh, 1.0]))[:2]
            wr_f = (M["front_hand"] @ np.array([*wr, 1.0]))[:2]
            plan.append(("sleeve", None, (sh_f, wr_f)))
        elif p == "body":
            plan.append(("body", layers.body_raised if raised else layers.body, M["body"]))
        else:
            plan.append((p, layers.get(p), M[p]))
    return plan


def _bbox(img):
    ys, xs = np.nonzero(img[..., 3] > 0)
    if len(xs) == 0:
        return None
    return np.array([[xs.min(), ys.min()], [xs.max() + 1, ys.min()], [xs.min(), ys.max() + 1], [xs.max() + 1, ys.max() + 1]], float)


def render(layers, seg, margin=6, canvas=None):
    """Render all 19 frames onto one shared canvas that just fits every pose
    (or onto `canvas` = (x0, y0, width, height) in skin pixels).

    Returns dict frame_name -> BGRA.  Layers are warped and composited one at a time so the
    memory stays a couple of canvases however large the skin is."""
    rig = ref.rig()
    ref_frame = pick_ref_frame(seg)
    plans = {name: frame_plan(layers, seg, name, ref_frame) for name in rig["frames"]}
    boxes = {}
    pts = []
    radius = ref.rig()["sleeve"]["radius"] * seg.scale
    for plan in plans.values():
        for p, img, A in plan:
            if p == "sleeve":
                for c in A:
                    pts.append(np.array([c - radius, c + radius]))
                continue
            if p not in boxes:
                boxes[p] = _bbox(img)
            b = boxes[p]
            if b is not None:
                pts.append((A[:2, :2] @ b.T).T + A[:2, 2])
    if canvas is None:
        pts = np.concatenate(pts)
        x0, y0 = np.floor(pts.min(0)).astype(int) - margin
        x1, y1 = np.ceil(pts.max(0)).astype(int) + margin
        W, H = int(x1 - x0), int(y1 - y0)
    else:
        x0, y0, W, H = canvas
    O = np.array([[1.0, 0, -x0], [0, 1.0, -y0], [0, 0, 1]])
    pms = {}
    frames = {}
    for name, plan in plans.items():
        acc = np.zeros((H, W, 4), np.float32)
        for p, img, A in plan:
            if p == "sleeve":
                sh_f, wr_f = ((O @ np.array([*c, 1.0]))[:2] for c in A)
                tube = _tube_on_canvas(layers, seg, sh_f, wr_f, radius, O, (H, W))
                l = to_pm(tube)
                acc *= 1 - l[..., 3:4]
                acc += l
                continue
            key = (p, id(img))
            if key not in pms:
                pms[key] = to_pm(img)
            l = cv2.warpAffine(pms[key], (O @ A)[:2], (W, H), flags=cv2.INTER_CUBIC, borderValue=0)
            np.clip(l, 0, 1, out=l)
            np.minimum(l[..., :3], l[..., 3:4], out=l[..., :3])
            acc *= 1 - l[..., 3:4]
            acc += l
            del l
        frames[name] = from_pm(acc)
        del acc
    return frames


def _tube_on_canvas(layers, seg, sh_f, wr_f, radius, O, shape):
    """Sleeve tube drawn on the output canvas; its texture comes from the robe layer, which is
    first moved onto the canvas with the plain offset O."""
    H, W = shape
    body = cv2.warpAffine(layers.body, O[:2], (W, H), flags=cv2.INTER_NEAREST, borderValue=0)
    ax = None
    if layers.sleeve_axis is not None:
        ax = tuple((O @ np.array([*c, 1.0]))[:2] for c in layers.sleeve_axis)
    return sleeve_tube(body, seg, ax, sh_f, wr_f, radius, (H, W))


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


def png_bytes(bgra):
    ok, enc = cv2.imencode(".png", bgra)
    return enc.tobytes()


def make_zip(named_pngs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in named_pngs:
            z.writestr(name, data)
    return buf.getvalue()
