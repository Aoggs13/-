"""Turn a segmentation into complete layers: everything a moving part used to hide is filled."""
from dataclasses import dataclass

import cv2
import numpy as np

from . import inpaint
from .segment import BODY, HEAD, BACK_HAND, FRONT_HAND, SCYTHE, dilate, erode, dist_to


@dataclass
class Layers:
    head: np.ndarray
    body: np.ndarray
    back_hand: np.ndarray
    front_hand: np.ndarray
    scythe: np.ndarray

    def get(self, name):
        return getattr(self, name)


def cut(rgba, mask):
    out = np.zeros_like(rgba)
    out[mask] = rgba[mask]
    return out


def complete_handle(layer, seg):
    """Rebuild the handle hidden behind the hand/robe by repeating the visible piece above it.

    Only pixels that another part covered in the input are filled; the filled strip follows
    the line joining the centres of the two visible pieces so the joins line up."""
    g0, g1 = seg.gap
    if g1 - g0 < 2:
        return layer
    p, d = seg.axis_p, seg.axis_d
    n = np.array([-d[1], d[0]])
    hw = seg.handle_hw
    H, W = layer.shape[:2]
    occluded = (seg.labels != SCYTHE) & (seg.labels != 0)
    a = layer[..., 3] > 0
    ys, xs = np.nonzero(a)
    pts = np.stack([xs, ys], 1).astype(np.float64) - p
    t = pts @ d
    u = pts @ n

    def centre(ta, tb, default):
        sel = (t >= ta) & (t <= tb) & (np.abs(u) < 2.5 * hw)
        return float(np.median(u[sel])) if sel.sum() > 5 else default

    # the hand may cover the handle a bit beyond the measured gap
    hy, hx = np.nonzero(seg.labels == FRONT_HAND)
    if len(hx):
        hp = np.stack([hx, hy], 1).astype(np.float64) - p
        ht, hu = hp @ d, hp @ n
        near = np.abs(hu) < 2.5 * hw
        if near.any():
            g1 = max(g1, float(ht[near].max()) + 1)
    lsrc = float(np.clip(6 * hw, 10, 0.3 * seg.handle_len))
    src0 = g1 + max(2.0, 0.3 * hw)
    ucs = centre(src0, src0 + lsrc, 0.0)
    uc1 = centre(g1, g1 + 3 * hw, ucs)
    uc0 = centre(g0 - 3 * hw, g0, uc1) if g0 > 1 else uc1
    sel = (t >= src0) & (t <= src0 + lsrc) & (np.abs(u - ucs) < 4 * hw)
    umax = float(np.percentile(np.abs(u[sel] - ucs), 99)) + 1 if sel.sum() > 10 else 1.5 * hw
    umax = min(umax, 3.5 * hw)
    t_lo, t_hi = g0 - 3 * hw, g1 + 3 * hw
    corners = [p + d * tt + n * (uu + c) for tt in (t_lo, t_hi) for uu in (-umax, umax) for c in (uc0, uc1)]
    cs = np.array(corners)
    bx0, by0 = np.floor(cs.min(0)).astype(int) - 2
    bx1, by1 = np.ceil(cs.max(0)).astype(int) + 3
    bx0, by0 = max(bx0, 0), max(by0, 0)
    bx1, by1 = min(bx1, W), min(by1, H)
    if bx1 <= bx0 or by1 <= by0:
        return layer
    gy, gx = np.mgrid[by0:by1, bx0:bx1].astype(np.float64)
    rel = np.stack([gx - p[0], gy - p[1]], -1)
    tt = rel @ d
    uu = rel @ n
    frac = np.clip((tt - g0) / max(g1 - g0, 1e-3), 0, 1)
    du = uu - (uc0 + (uc1 - uc0) * frac)
    band = (tt >= t_lo) & (tt <= t_hi) & (np.abs(du) <= umax)
    ts = src0 + np.mod(tt - t_lo, lsrc)
    us = ucs + du
    mx = (p[0] + d[0] * ts + n[0] * us).astype(np.float32)
    my = (p[1] + d[1] * ts + n[1] * us).astype(np.float32)
    f = layer.astype(np.float32)
    pm = np.dstack([f[..., :3] * f[..., 3:4] / 255, f[..., 3:4]])
    smp = cv2.remap(pm, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    out = layer.copy()
    region = out[by0:by1, bx0:bx1]
    dst_empty = region[..., 3] < 250
    put = band & dst_empty & occluded[by0:by1, bx0:bx1] & (smp[..., 3] > 8)
    # composite the copied handle under whatever semi-transparent rim is already there
    sa = smp[..., 3:4] / 255
    da = region[..., 3:4].astype(np.float32) / 255
    src_col = smp[..., :3] / np.maximum(sa, 1e-3)
    oa = da + sa * (1 - da)
    oc = (region[..., :3].astype(np.float32) * da + src_col * sa * (1 - da)) / np.maximum(oa, 1e-3)
    region[put, :3] = np.clip(oc[put], 0, 255).astype(np.uint8)
    region[put, 3] = np.clip(oa[put, 0] * 255, 0, 255).astype(np.uint8)
    return out


def complete_body(rgba, seg):
    lab = seg.labels
    s = seg.scale
    body = lab == BODY
    over = (lab == FRONT_HAND) | (lab == BACK_HAND)
    if seg.scythe_in_front:
        over |= lab == SCYTHE
    head = lab == HEAD
    band = head & dilate(body, 7 * s) & ~erode(head, 1)
    grow = dilate(over, seg.outline + 2)
    hole = ((grow & ~(lab == SCYTHE)) | band) if not seg.scythe_in_front else (grow | band)
    hole &= (lab != 0) | dilate(over, 2)
    if not hole.any():
        return cut(rgba, body)
    # silhouette inside the holes: diffuse the body's alpha from the hole border, then smooth
    a = np.where(body, 255, 0).astype(np.uint8)
    a_in = cv2.inpaint(a, hole.astype(np.uint8), 3, cv2.INPAINT_TELEA).astype(np.float32)
    sm = cv2.GaussianBlur(a_in, (0, 0), max(1.0, 1.2 * seg.outline))
    ext = (np.where(hole, sm, a_in) > 127) & hole
    new_body = (body & ~hole) | ext
    new_body = cv2.morphologyEx(new_body.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool) | (body & ~hole)
    # colours: LaMa on the body composited over its own median colour
    med = np.median(rgba[..., :3][body & (dist_to(~body) > 3)], 0) if body.sum() > 50 else np.array([128, 128, 128])
    base = np.where(body[..., None], rgba[..., :3], med.astype(np.uint8)).astype(np.uint8)
    filled = inpaint.fill(base, hole)
    out = np.zeros_like(rgba)
    keep = body & ~hole
    out[..., :3] = np.where(keep[..., None], rgba[..., :3], filled)
    out[..., 3] = np.where(keep, rgba[..., 3], np.where(new_body, 255, 0)).astype(np.uint8)
    # redraw the outline along the new silhouette inside the holes
    ow = max(int(round(seg.outline)), 1)
    edge = new_body & ~erode(new_body, ow)
    redraw = edge & hole
    out[redraw, :3] = seg.outline_color
    out[~new_body] = 0
    return out


def build(rgba, seg):
    lab = seg.labels
    scythe = complete_handle(cut(rgba, lab == SCYTHE), seg)
    return Layers(
        head=cut(rgba, lab == HEAD),
        body=complete_body(rgba, seg),
        back_hand=cut(rgba, lab == BACK_HAND),
        front_hand=cut(rgba, lab == FRONT_HAND),
        scythe=scythe,
    )


def sleeve_sprite(body_layer, seg, shoulder, wrist, radius, shape):
    """Raised front sleeve: a tube from shoulder to wrist textured with the robe and outlined."""
    H, W = shape[:2]
    out = np.zeros((H, W, 4), np.uint8)
    v = np.asarray(wrist, float) - np.asarray(shoulder, float)
    length = float(np.linalg.norm(v))
    if length < 1:
        return out
    ow = max(int(round(seg.outline)), 1)
    r = int(round(radius))
    mask = np.zeros((H, W), np.uint8)
    cv2.line(mask, tuple(int(round(c)) for c in shoulder), tuple(int(round(c)) for c in wrist), 1, 2 * r)
    cv2.circle(mask, tuple(int(round(c)) for c in shoulder), r, 1, -1)
    mask = mask.astype(bool)
    inner = erode(mask, ow)
    # texture: sample the robe along a vertical strip next to the shoulder
    body_a = body_layer[..., 3] > 200
    ys, xs = np.nonzero(body_a & (dist_to(~body_a) > r + 2))
    if len(xs) == 0:
        col = np.median(body_layer[..., :3][body_a], 0) if body_a.any() else np.array([128, 128, 128])
        out[inner, :3] = col.astype(np.uint8)
    else:
        src_c = np.array([np.median(xs), np.median(ys)])
        e = v / length
        nrm = np.array([-e[1], e[0]])
        gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
        rx = gx - shoulder[0]; ry = gy - shoulder[1]
        along = rx * e[0] + ry * e[1]
        across = rx * nrm[0] + ry * nrm[1]
        # map the tube to a vertical strip of the robe centred at src_c
        mx = (src_c[0] + across).astype(np.float32)
        my = (src_c[1] - length / 2 + along).astype(np.float32)
        smp = cv2.remap(body_layer, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        out[inner, :3] = smp[inner, :3]
    out[mask & ~inner, :3] = seg.outline_color
    out[mask, 3] = 255
    return out
