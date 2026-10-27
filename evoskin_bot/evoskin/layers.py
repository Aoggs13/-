"""Turn a segmentation into complete layers: everything a moving part used to hide is filled."""
from dataclasses import dataclass

import cv2
import numpy as np

from . import inpaint
from .segment import BODY, HEAD, BACK_HAND, FRONT_HAND, SCYTHE, dilate, erode, dist_to


@dataclass
class Layers:
    head: np.ndarray
    body: np.ndarray           # robe with the front sleeve hanging, as drawn
    body_raised: np.ndarray    # robe without the front sleeve (attack frames that lift the arm)
    back_hand: np.ndarray      # back hand together with its sleeve
    front_hand: np.ndarray
    scythe: np.ndarray
    sleeve: np.ndarray         # the skin's own front sleeve, cut out of the robe
    sleeve_axis: tuple         # (shoulder, wrist) points of that sleeve in skin pixels

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


def outline_cut(layer, mask, cut_side, ow, color):
    """Draw the skin's outline along the part of `mask`'s border that was cut from a neighbour."""
    ring = mask & ~erode(mask, ow) & dilate(cut_side, ow + 1)
    layer[ring, :3] = color
    layer[ring, 3] = 255


def body_holes(seg, remove):
    """Robe pixels that stay, and the holes that moving parts leave in it.

    `remove`: sleeve pixels that leave the robe; the line between sleeve and robe stays and
    becomes the robe's edge.  Hands (and a scythe drawn in front) leave holes to fill."""
    lab = seg.labels
    body = (lab == BODY) & ~remove
    paws = ((lab == FRONT_HAND) | (lab == BACK_HAND)) & ~remove
    over = paws | ((lab == SCYTHE) if seg.scythe_in_front else False)
    head = lab == HEAD
    band = head & dilate(body, 7 * seg.scale) & ~erode(head, 1)
    grow = dilate(over, seg.outline + 2)
    hole = ((grow & ~(lab == SCYTHE)) | band) if not seg.scythe_in_front else (grow | band)
    hole &= ((lab != 0) | dilate(over, 2)) & ~remove
    return body, hole


def complete_body(rgba, seg, remove, filled):
    """Robe layer: kept pixels, holes coloured from `filled`, silhouette closed and outlined."""
    body, hole = body_holes(seg, remove)
    ow = max(int(round(seg.outline)), 1)
    out = np.zeros_like(rgba)
    if hole.any():
        # silhouette inside the holes: diffuse the body's alpha from the hole border, then smooth
        a = np.where(body, 255, 0).astype(np.uint8)
        a_in = cv2.inpaint(a, hole.astype(np.uint8), 3, cv2.INPAINT_TELEA).astype(np.float32)
        sm = cv2.GaussianBlur(a_in, (0, 0), max(1.0, 1.2 * seg.outline))
        ext = (np.where(hole, sm, a_in) > 127) & hole
        new_body = (body & ~hole) | ext
        new_body = cv2.morphologyEx(new_body.astype(np.uint8), cv2.MORPH_OPEN,
                                    np.ones((3, 3), np.uint8)).astype(bool) | (body & ~hole)
    else:
        new_body = body
    # crumbs left over by the cuts (bits of outline) are not part of the robe
    n, cl, st, _ = cv2.connectedComponentsWithStats(new_body.astype(np.uint8), connectivity=8)
    if n > 2:
        big = st[1:, 4].max()
        for i in range(1, n):
            if st[i, 4] < 0.02 * big:
                new_body[cl == i] = False
    keep = body & ~hole & new_body
    out[..., :3] = np.where(keep[..., None], rgba[..., :3], filled)
    out[..., 3] = np.where(keep, rgba[..., 3], np.where(new_body, 255, 0)).astype(np.uint8)
    # redraw the outline along the new silhouette inside the holes and along the sleeve cuts
    edge = new_body & ~erode(new_body, ow)
    redraw = edge & (hole | dilate(remove, ow + 1))
    out[redraw, :3] = seg.outline_color
    out[~new_body] = 0
    return out


def sleeve_axis(mask):
    """Shoulder (upper end) and wrist (lower end) of a sleeve mask along its main axis."""
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    m = pts.mean(0)
    w, v = np.linalg.eigh(np.cov((pts - m).T)) if len(pts) > 2 else (None, np.eye(2))
    d = v[:, -1]
    if d[1] < 0:
        d = -d                       # point downwards: shoulder first
    t = (pts - m) @ d
    return m + d * np.percentile(t, 4), m + d * np.percentile(t, 96)


def build(rgba, seg):
    lab = seg.labels
    ow = max(int(round(seg.outline)), 1)
    scythe = complete_handle(cut(rgba, lab == SCYTHE), seg)
    empty = np.zeros(lab.shape, bool)
    front = seg.front_band if seg.front_band is not None else empty
    back = seg.back_band if seg.back_band is not None else empty
    # one LaMa pass colours the holes of both robe variants
    body_n, hole_n = body_holes(seg, back)
    _, hole_r = body_holes(seg, back | front)
    med = np.median(rgba[..., :3][body_n & (dist_to(~body_n) > 3)], 0) if body_n.sum() > 50 else np.array([128, 128, 128])
    base = np.where(body_n[..., None], rgba[..., :3], med.astype(np.uint8)).astype(np.uint8)
    filled = inpaint.fill(base, hole_n | hole_r)
    body = complete_body(rgba, seg, back, filled)
    body_raised = complete_body(rgba, seg, back | front, filled) if front.any() else body
    rest = (lab == BODY) & ~front & ~back
    back_hand = cut(rgba, lab == BACK_HAND)
    outline_cut(back_hand, lab == BACK_HAND, rest, ow, seg.outline_color)
    sleeve = cut(rgba, front)
    if front.any():
        outline_cut(sleeve, front, rest, ow, seg.outline_color)
        axis = sleeve_axis(front)
    else:
        axis = None
    return Layers(head=cut(rgba, lab == HEAD), body=body, body_raised=body_raised, back_hand=back_hand,
                  front_hand=cut(rgba, lab == FRONT_HAND), scythe=scythe, sleeve=sleeve, sleeve_axis=axis)


def sleeve_tube(body_layer, seg, sleeve_axis, shoulder, wrist, radius, shape):
    """Lifted front sleeve, shaped like the black reaper's (a thick tube from shoulder to wrist)
    and dressed in the skin's own robe: the fur next to the hanging sleeve is copied onto
    it unstretched, then the skin's outline goes round it."""
    H, W = shape[:2]
    out = np.zeros((H, W, 4), np.uint8)
    shoulder = np.asarray(shoulder, float)
    wrist = np.asarray(wrist, float)
    v = wrist - shoulder
    length = float(np.linalg.norm(v))
    if length < 1:
        return out
    ow = max(int(round(seg.outline)), 1)
    r = max(int(round(radius)), ow + 2)
    mask = np.zeros((H, W), np.uint8)
    p0 = tuple(int(round(c)) for c in shoulder)
    p1 = tuple(int(round(c)) for c in wrist)
    cv2.line(mask, p0, p1, 1, 2 * r)
    cv2.circle(mask, p0, r, 1, -1)
    cv2.circle(mask, p1, r, 1, -1)
    mask = mask.astype(bool)
    inner = erode(mask, ow)
    # texture source: robe just inside the hanging sleeve, running down from the shoulder
    body_a = body_layer[..., 3] > 200
    deep = body_a & (dist_to(~body_a) > ow + 2)
    if sleeve_axis is not None and deep.any():
        s0, s1 = (np.asarray(p, float) for p in sleeve_axis)
        ys, xs = np.nonzero(deep)
        pts = np.stack([xs, ys], 1).astype(float)
        mid = (s0 + s1) / 2
        src = pts[np.argmin(((pts - mid) ** 2).sum(1))]          # nearest robe pixel to the sleeve
        dn = s1 - s0
        dn = dn / (np.linalg.norm(dn) + 1e-6)
    elif deep.any():
        ys, xs = np.nonzero(deep)
        src = np.array([np.median(xs), np.median(ys)], float)
        dn = np.array([0.0, 1.0])
    else:
        out[inner, :3] = seg.outline_color
        out[mask, 3] = 255
        return out
    e = v / length
    ne = np.array([-e[1], e[0]])
    nd = np.array([-dn[1], dn[0]])
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    rx, ry = gx - shoulder[0], gy - shoulder[1]
    along = rx * e[0] + ry * e[1] - length / 2
    across = rx * ne[0] + ry * ne[1]
    mx = (src[0] + along * dn[0] + across * nd[0]).astype(np.float32)
    my = (src[1] + along * dn[1] + across * nd[1]).astype(np.float32)
    tex = body_layer.copy()
    tex[..., :3][~body_a] = np.median(body_layer[..., :3][deep], 0).astype(np.uint8)
    smp = cv2.remap(tex, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    out[inner, :3] = smp[inner, :3]
    out[mask & ~inner, :3] = seg.outline_color
    out[mask, 3] = 255
    return out

