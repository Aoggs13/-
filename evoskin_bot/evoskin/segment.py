"""Split a skin (standard reaper pose) into the rig parts.

Priors come from the black reaper reference pose mapped onto the skin; GrabCut refines
every boundary from the skin's own colours and outlines, so costume extras (tails, ears,
spikes, ornaments) end up in whichever part they are attached to.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import reference as ref
from . import register as reg

BG, HEAD, BODY, BACK_HAND, FRONT_HAND, SCYTHE = 0, 1, 2, 3, 4, 5
NAMES = {HEAD: "head", BODY: "body", BACK_HAND: "back_hand", FRONT_HAND: "front_hand", SCYTHE: "scythe"}


@dataclass
class Segmentation:
    labels: np.ndarray
    S_head: np.ndarray
    S_body: np.ndarray
    scale: float
    grip: np.ndarray
    axis_p: np.ndarray          # handle bottom end (skin coords)
    axis_d: np.ndarray          # unit vector bottom -> top
    handle_len: float
    handle_hw: float            # handle half width
    gap: tuple                  # hidden handle interval (t0, t1) along the axis
    scythe_in_front: bool
    outline: float              # outline thickness in px
    outline_color: np.ndarray
    anchors: dict = field(default_factory=dict)   # skin points matching the rig pivots
    front_band: np.ndarray = field(default=None, repr=False)   # hanging front sleeve (raised in attacks)
    back_band: np.ndarray = field(default=None, repr=False)    # back sleeve (part of the back arm)
    skull: dict = field(default=None, repr=False)


def disk(shape, c, r):
    m = np.zeros(shape, np.uint8)
    cv2.circle(m, (int(round(c[0])), int(round(c[1]))), max(int(round(r)), 1), 1, -1)
    return m.astype(bool)


def dist_to(mask):
    return cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)


def erode(mask, r):
    r = max(int(round(r)), 1)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.erode(mask.astype(np.uint8), k).astype(bool)


def dilate(mask, r):
    r = max(int(round(r)), 1)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(mask.astype(np.uint8), k).astype(bool)


def key_image(rgba):
    al = rgba[..., 3:4].astype(np.float32) / 255
    key = np.array([0, 255, 0], np.float32)
    return (rgba[..., :3].astype(np.float32) * al + key * (1 - al)).astype(np.uint8)


def grabcut(img, fgd, bgd, prf, iters=5):
    gc = np.full(fgd.shape, cv2.GC_PR_BGD, np.uint8)
    gc[prf] = cv2.GC_PR_FGD
    gc[bgd] = cv2.GC_BGD
    gc[fgd] = cv2.GC_FGD
    if not fgd.any() or not (bgd | (gc == cv2.GC_PR_BGD)).any():
        return fgd | prf
    bm = np.zeros((1, 65), np.float64)
    fm = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img, gc, None, bm, fm, iters, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return fgd | prf
    return (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)


def grabcut_roi(img, fgd, bgd, prf, box, iters=5):
    x0, y0, x1, y1 = box
    out = np.zeros(fgd.shape, bool)
    sl = (slice(y0, y1), slice(x0, x1))
    out[sl] = grabcut(np.ascontiguousarray(img[sl]), fgd[sl], bgd[sl], prf[sl], iters)
    return out


def keep_touching(mask, seeds):
    n, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    ids = np.unique(lab[seeds & mask])
    ids = ids[ids > 0]
    return np.isin(lab, ids)


def roi_box(c, r, shape):
    H, W = shape[:2]
    return (max(int(c[0] - r), 0), max(int(c[1] - r), 0), min(int(c[0] + r) + 1, W), min(int(c[1] + r) + 1, H))


def outline_stats(rgba, fg):
    v = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_BGR2HSV)[..., 2]
    dark = fg & (v < 60)
    if dark.sum() < 50:
        return 2.0, np.array([20, 20, 20], np.uint8)
    dt = cv2.distanceTransform(dark.astype(np.uint8), cv2.DIST_L2, 3)
    # local maxima of the distance transform = half line widths
    mx = (dt >= cv2.dilate(dt, np.ones((3, 3), np.uint8))) & (dt > 0.5)
    w = float(np.median(dt[mx]) * 2) if mx.any() else 2.0
    col = np.median(rgba[..., :3][dark], 0).astype(np.uint8)
    return max(w, 1.5), col


def segment(rgba):
    rig = ref.rig()
    H, W = rgba.shape[:2]
    fg = rgba[..., 3] > 127
    img = key_image(rgba)
    skull = reg.skull_features(rgba)
    S_head = reg.from_skull(skull) if skull is not None else reg.from_silhouette(rgba)
    s = float(S_head[0, 0])
    outline_w, outline_col = outline_stats(rgba, fg)
    ink = fg & (cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_BGR2HSV)[..., 2] < 50)

    # ---- scythe vs character -------------------------------------------------------
    P = reg.warp_labels(S_head, rgba.shape)
    sc_prior = (P == ref.L["handle"]) | (P == ref.L["blade"])
    ch_prior = (P >= ref.L["head"]) & (P <= ref.L["front_hand"])
    D_sc, D_ch = dist_to(sc_prior), dist_to(ch_prior)
    far = 12 * s
    fgd = fg & (D_ch > far) & (D_sc < far)
    hb_core = erode((P == ref.L["head"]) | (P == ref.L["body"]), 6 * s)
    bgd = ~fg | (fg & (D_sc > far) & (D_ch < D_sc)) | (fg & hb_core)
    prf = fg & (D_sc < D_ch)
    sc = grabcut(img, fgd & ~bgd, bgd, prf) & fg
    if fgd.any():
        sc = keep_touching(sc, fgd | (sc_prior & fg & ~dilate(ch_prior, 2 * s)))

    # ---- handle axis -----------------------------------------------------------------
    bot_br = np.array(rig["pivots"]["scythe"]); top_br = np.array(rig["handle_top"])
    p0 = reg.apply(S_head, bot_br); p1 = reg.apply(S_head, top_br)
    Lh = float(np.linalg.norm(p1 - p0))
    d = (p1 - p0) / Lh
    ys, xs = np.nonzero(sc)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    for _ in range(3):
        nrm = np.array([-d[1], d[0]])
        t = (pts - p0) @ d
        u = (pts - p0) @ nrm
        sel = (np.abs(u) < 14 * s) & (t > -0.15 * Lh) & (t < 0.72 * Lh)
        if sel.sum() < 20:
            break
        tb = np.round(t[sel] / max(s, 1.0)).astype(int)
        cs = []
        for b in np.unique(tb):
            uu = u[sel][tb == b]
            cs.append((b * max(s, 1.0), float(np.median(uu))))
        cs = np.array(cs)
        line_pts = np.stack([p0[0] + cs[:, 0] * d[0] + cs[:, 1] * nrm[0], p0[1] + cs[:, 0] * d[1] + cs[:, 1] * nrm[1]], 1)
        vx, vy, x0, y0 = cv2.fitLine(line_pts.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        nd = np.array([vx, vy], float)
        if nd @ d < 0:
            nd = -nd
        q = np.array([x0, y0], float)
        p0 = q + ((p0 - q) @ nd) * nd   # keep p0 as the projection of the old bottom end
        d = nd
    nrm = np.array([-d[1], d[0]])
    t = (pts - p0) @ d
    u = (pts - p0) @ nrm
    core = (np.abs(u) < 14 * s) & (t > -0.3 * Lh) & (t < 0.75 * Lh)
    # half width from the clean part of the top run
    mid = core & (t > 0.45 * Lh) & (t < 0.7 * Lh)
    hw = float(np.percentile(np.abs(u[mid]), 60)) if mid.sum() > 10 else 4.0 * s
    hw = float(np.clip(hw, 2.0 * s, 12.0 * s))
    # occupancy along the axis
    ts = np.arange(int(-0.3 * Lh), int(0.75 * Lh))
    occ = np.zeros(len(ts), bool)
    for i, tt in enumerate(ts):
        c = p0 + d * tt
        for uu in np.linspace(-hw * 0.6, hw * 0.6, 5):
            x, y = int(round(c[0] + nrm[0] * uu)), int(round(c[1] + nrm[1] * uu))
            if 0 <= x < W and 0 <= y < H and sc[y, x]:
                occ[i] = True
                break
    runs = []
    i = 0
    while i < len(ts):
        if occ[i]:
            j = i
            while j + 1 < len(ts) and (occ[j + 1] or (j + 3 < len(ts) and occ[j + 3])):
                j += 1
            runs.append((ts[i], ts[j]))
            i = j + 1
        else:
            i += 1
    hand_r = 9.0 * s
    runs = [r for r in runs if r[1] - r[0] >= 3]
    top_run = None
    for r0, r1 in runs:
        if r1 > 0.45 * Lh:
            top_run = (r0, r1)
            break
    if top_run is None:
        top_run = (0.4 * Lh, 0.7 * Lh)
    lower = [r for r in runs if r[1] < top_run[0] - 2 and r[0] < 0.4 * Lh]
    if lower:
        t_bottom = float(min(r[0] for r in lower))
        gap_start = float(min(r[1] for r in lower))   # end of the lowest visible piece
    else:
        t_bottom = 0.0
        gap_start = 0.0
    gap_end = float(top_run[0])
    # hidden length inside the gap (visible ornaments in between do not count)
    in_gap = (ts >= gap_start) & (ts <= gap_end)
    hidden_len = float((~occ[in_gap]).sum())
    # make the bottom end of the axis the true end of the handle
    p_bot = p0 + d * t_bottom
    handle_len = Lh - t_bottom
    gap = (gap_start - t_bottom, gap_end - t_bottom)
    char = fg & ~sc
    # the hand is whatever covers the handle right where the handle comes out again
    gyy, gxx = np.mgrid[0:H, 0:W].astype(np.float32)
    rel_t = (gxx - p0[0]) * d[0] + (gyy - p0[1]) * d[1]
    rel_u = (gxx - p0[0]) * nrm[0] + (gyy - p0[1]) * nrm[1]
    on_line = (np.abs(rel_u) <= max(hw, 3 * s)) & (rel_t >= gap_end - 1.2 * hand_r) & (rel_t <= gap_end + 0.6 * hand_r)
    hand_seed = on_line & char & ~ink
    grip_pred = reg.apply(S_head, rig["pivots"]["front_hand"])
    if hand_seed.sum() >= 4:
        sy, sx = np.nonzero(hand_seed)
        grip = np.array([sx.mean(), sy.mean()])
    else:
        grip = p_bot + d * (gap[1] - 0.9 * hand_r)
    gx, gy = int(round(grip[0])), int(round(grip[1]))
    if np.linalg.norm(grip - grip_pred) > 35 * s or not (0 <= gx < W and 0 <= gy < H):
        grip = grip_pred
        hand_seed = np.zeros_like(fg)

    S_body = reg.sim(s, *(grip - s * np.array(rig["pivots"]["front_hand"])))

    # ---- front hand ---------------------------------------------------------------------
    box = roi_box(grip, 4 * hand_r, rgba.shape)
    fgd = hand_seed if hand_seed.any() else disk(fg.shape, grip, 0.35 * hand_r) & char
    prf = disk(fg.shape, grip, 1.4 * hand_r) & char
    bgd = ~char | ~disk(fg.shape, grip, 2.4 * hand_r)
    fh = grabcut_roi(img, fgd, bgd & ~fgd, prf, box) & char
    fh = trim_to_core(fh, fgd, ink, outline_w, allowed=fg)

    # ---- back hand ----------------------------------------------------------------------
    bh_c = reg.apply(S_body, rig["pivots"]["back_hand"])
    bh_r = 11.0 * s
    char2 = char & ~fh
    box = roi_box(bh_c, 4 * bh_r, rgba.shape)
    fgd = disk(fg.shape, bh_c, 0.35 * bh_r) & char2
    prf = disk(fg.shape, bh_c, 1.3 * bh_r) & char2
    bgd = ~char2 | ~disk(fg.shape, bh_c, 2.2 * bh_r)
    bh = grabcut_roi(img, fgd, bgd & ~fgd, prf, box) & char2
    bh = trim_to_core(bh, fgd, ink, outline_w, allowed=fg & ~fh)

    # ---- head vs body -------------------------------------------------------------------
    region = char & ~fh & ~bh
    Pb = reg.warp_labels(S_body, rgba.shape)
    head_prior = P == ref.L["head"]
    body_prior = (Pb == ref.L["body"]) | (Pb == ref.L["back_hand"]) | (Pb == ref.L["front_hand"])
    skull_m = skull["mask"] if skull is not None else np.zeros_like(fg)
    fgd = (skull_m | erode(head_prior, 5 * s)) & region
    bgd = ~region | (erode(body_prior, 3 * s) & ~fgd)
    prf = region & (dist_to(head_prior) < dist_to(body_prior))
    head = grabcut(img, fgd, bgd, prf) & region
    head = keep_touching(head, fgd) if fgd.any() else head
    # fill small holes in the head (spots, eye details)
    head = fill_holes(head, region)

    labels = np.zeros(fg.shape, np.uint8)
    labels[fg] = BODY
    labels[head] = HEAD
    labels[sc] = SCYTHE
    labels[bh] = BACK_HAND
    labels[fh] = FRONT_HAND

    # is the scythe drawn in front of the robe?  It is behind when the robe covers a
    # stretch of the hidden handle (not just the hand holding it)
    body_cov = 0
    for tt in np.arange(gap_start, gap_end, 1.0):
        hits = 0
        for uu in (-0.5 * hw, 0.0, 0.5 * hw):
            q = p0 + d * tt + nrm * uu
            x, y = int(round(q[0])), int(round(q[1]))
            hits += 0 <= x < W and 0 <= y < H and labels[y, x] == BODY
        body_cov += hits >= 2
    scythe_in_front = body_cov < max(4.0, 0.4 * hand_r)

    # outlines on the scythe/body border belong to whichever part is in front
    if not scythe_in_front:
        v = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_BGR2HSV)[..., 2]
        dark = v < 70
        body_light = (labels == BODY) & ~dark
        near = dist_to(body_light) <= outline_w * 1.1
        move = (labels == SCYTHE) & dark & near & ~dilate(fh, outline_w)
        labels[move] = BODY

    labels = clean_labels(labels, rgba[..., 3] > 0, s)
    anchors = part_anchors(labels, S_body, s, rig)
    # sleeves: the back sleeve swings with the back hand; the front one is lifted in the attacks
    S_arm = reg.sim(s, *(anchors["body"] - s * np.array(rig["pivots"]["body"], float)))
    back_band = arm_band(labels, ink, S_arm, BACK_BAND, outline_w, s)
    labels[back_band] = BACK_HAND
    front_band = arm_band(labels, ink, S_arm, FRONT_BAND, outline_w, s)

    return Segmentation(labels=labels, S_head=S_head, S_body=S_body, scale=s, grip=np.asarray(grip, float),
                        axis_p=p_bot, axis_d=d, handle_len=float(handle_len), handle_hw=hw, gap=gap,
                        scythe_in_front=bool(scythe_in_front), outline=outline_w,
                        outline_color=outline_col, anchors=anchors, front_band=front_band,
                        back_band=back_band, skull=skull)


# hanging sleeves of the black reaper idle pose (outer outline to the line that parts them from the robe)
FRONT_BAND = [(208, 158), (219, 157), (230, 176), (226, 182), (214, 182), (209, 170)]
BACK_BAND = [(150, 161), (171, 161), (171, 189), (152, 189), (141, 190), (143, 178)]


def arm_band(labels, ink, S, poly, outline_w, s):
    """Sleeve pixels of the skin's robe that match a black reaper sleeve.

    Regions of the robe that the skin's own lines separate and that lie mostly inside the
    mapped sleeve outline are taken whole; the line between sleeve and robe stays with
    the robe (it becomes the robe's edge when the arm moves away)."""
    H, W = labels.shape
    pm = np.zeros((H, W), np.uint8)
    cv2.fillPoly(pm, [np.round([reg.apply(S, q) for q in poly]).astype(np.int32)], 1)
    pm = pm.astype(bool)
    body = labels == BODY
    if not (pm & body).any():
        return np.zeros((H, W), bool)
    nonink = body & ~ink
    n, lab = cv2.connectedComponents(nonink.astype(np.uint8), connectivity=4)
    keep = np.zeros((H, W), bool)
    area = (pm & body).sum()
    for i in np.unique(lab[pm & nonink]):
        if i == 0:
            continue
        comp = lab == i
        cs = comp.sum()
        if (comp & pm).sum() / cs > 0.55 and cs < 3 * area:
            keep |= comp
    keep = fill_holes(keep, body)
    # the skin's own sleeve line is used only when it matches the black reaper sleeve well;
    # otherwise cut along the black reaper sleeve outline itself
    cover = (keep & pm).sum() / max(area, 1)
    spill = (keep & ~dilate(pm, 3 * s)).sum() / max(keep.sum(), 1)
    if cover < 0.7 or spill > 0.25:
        keep = fill_holes(pm & nonink, body)
    band = keep | (ink & body & dilate(keep, 1.5 * outline_w))
    # the line towards the rest of the robe stays on the robe (the robe's inside, not its
    # anti-aliased rim: the sleeve's outer outline goes with the sleeve)
    rest = nonink & ~keep & erode(labels > 0, 2)
    inner = band & ink & dilate(rest, 1.2 * outline_w) & ~keep
    return band & ~inner


def part_anchors(labels, S_body, s, rig):
    """Skin points that correspond to the rig pivots of the body and both hands."""
    pv = rig["pivots"]
    fh_br, bh_br, body_br = (np.array(pv[k], float) for k in ("front_hand", "back_hand", "body"))

    def centroid(m, default):
        if m.sum() < 20 * s * s:
            return np.asarray(default, float)
        ys, xs = np.nonzero(m)
        return np.array([xs.mean(), ys.mean()])

    fh_c = centroid(labels == FRONT_HAND, reg.apply(S_body, fh_br))
    bh_c = centroid(labels == BACK_HAND, reg.apply(S_body, bh_br))
    # the robe sits between the hands: place its pivot with the two-hand similarity
    v_br, v_s = fh_br - bh_br, fh_c - bh_c
    k = np.linalg.norm(v_s) / np.linalg.norm(v_br)
    if 0.75 * s < k < 1.33 * s:
        a = np.arctan2(v_s[1], v_s[0]) - np.arctan2(v_br[1], v_br[0])
        R = k * np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        body_c = bh_c + R @ (body_br - bh_br)
    else:
        body_c = reg.apply(S_body, body_br)
    return {"front_hand": fh_c, "back_hand": bh_c, "body": body_c}


def clean_labels(labels, visible, s):
    """Give stray fragments to their neighbours and label the semi-transparent rim."""
    out = labels.copy()
    min_area = max(25, int(40 * s * s))
    for k in (HEAD, BODY, BACK_HAND, FRONT_HAND, SCYTHE):
        m = (out == k).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n <= 2:
            continue
        main = 1 + int(np.argmax(stats[1:, 4]))
        for i in range(1, n):
            if i == main or stats[i, 4] >= min_area:
                continue
            comp = lab == i
            ring = dilate(comp, 2) & ~comp
            neigh = out[ring]
            neigh = neigh[(neigh != k) & (neigh != BG)]
            out[comp] = np.bincount(neigh).argmax() if len(neigh) else BG
    # semi-transparent edge pixels take the nearest part's label
    rim = visible & (out == BG)
    if rim.any():
        best_d = np.full(out.shape, np.inf, np.float32)
        best_k = np.zeros(out.shape, np.uint8)
        for k in (HEAD, BODY, BACK_HAND, FRONT_HAND, SCYTHE):
            if not (out == k).any():
                continue
            dk = dist_to(out == k)
            upd = dk < best_d
            best_d[upd] = dk[upd]
            best_k[upd] = k
        out[rim] = best_k[rim]
    return out


def trim_to_core(mask, seeds, ink, outline_w, allowed=None):
    """Keep the coloured blob around the seeds plus the outline ring that hugs it.

    GrabCut likes to grow hands along neighbouring black outlines; those lines belong to
    the robe, so only ink within ~1.5 line widths of the hand's own colour is kept."""
    if not seeds.any():
        return mask
    nonink = mask & ~ink
    core = keep_touching(nonink, seeds & nonink) if (seeds & nonink).any() else keep_touching(mask, seeds)
    if not core.any():
        return keep_touching(mask, seeds)
    # bridge thin lines inside the hand (finger separations)
    core = core | keep_touching(nonink, dilate(core, 1.2 * outline_w) & nonink)
    core = fill_holes(core, mask)
    # the hand's own outline: ink hugging the hand, even where it was given to a neighbour
    ring = dilate(core, 1.5 * outline_w) & ink & (mask if allowed is None else allowed)
    return core | ring


def fill_holes(mask, allowed):
    inv = (~mask).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    H, W = mask.shape
    out = mask.copy()
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if x == 0 or y == 0 or x + w >= W or y + h >= H:
            continue
        comp = lab == i
        if a < 0.02 * mask.sum() and (comp & allowed).sum() == a:
            out |= comp
    return out
