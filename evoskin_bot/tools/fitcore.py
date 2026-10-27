import cv2, numpy as np
from brseg import load, classes, ref_parts, dil
BG = np.array([255, 0, 255], np.float32)
def on_bg(a):
    al = a[..., 3:4].astype(np.float32) / 255
    return (a[..., :3].astype(np.float32) * al + BG * (1 - al)).astype(np.float32)

def rotmat(theta_deg, pivot, dst):
    R = cv2.getRotationMatrix2D((float(pivot[0]), float(pivot[1])), float(theta_deg), 1.0)
    R[:, 2] += np.array(dst, float) - np.array(pivot, float)
    return R

class Part:
    def __init__(self, img, mask):
        ys, xs = np.nonzero(mask)
        self.n = len(xs)
        self.pts = np.stack([xs, ys, np.ones_like(xs)], 0).astype(np.float64)
        self.col = img[ys, xs].astype(np.float32)
        self.center = np.array([xs.mean(), ys.mean()])
    def score(self, A, fimg, falpha, tol=40):
        q = A @ self.pts
        xi = np.rint(q[0]).astype(np.int32); yi = np.rint(q[1]).astype(np.int32)
        H, W = falpha.shape
        v = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        xi, yi = xi[v], yi[v]
        d = np.abs(fimg[yi, xi] - self.col[v]).max(1)
        ok = (d < tol) & (falpha[yi, xi] > 128)
        return ok.sum() / self.n

def search(part, fimg, falpha, pivot, dst0, thetas, shifts):
    best = (-1, None, None)
    for th in thetas:
        for dx in shifts:
            for dy in shifts:
                dst = (dst0[0] + dx, dst0[1] + dy)
                A = rotmat(th, pivot, dst)
                s = part.score(A, fimg, falpha)
                if s > best[0]: best = (s, th, dst)
    return best

def refine(part, fimg, falpha, pivot, th, dst, th_rng=2.0, th_step=0.25, sh_rng=2.0, sh_step=0.5):
    best = (part.score(rotmat(th, pivot, dst), fimg, falpha), th, dst)
    for _ in range(3):
        s0, th0, d0 = best
        for t in np.arange(th0 - th_rng, th0 + th_rng + 1e-6, th_step):
            for dx in np.arange(-sh_rng, sh_rng + 1e-6, sh_step):
                for dy in np.arange(-sh_rng, sh_rng + 1e-6, sh_step):
                    dst = (d0[0] + dx, d0[1] + dy)
                    s = part.score(rotmat(t, pivot, dst), fimg, falpha)
                    if s > best[0] + 1e-9: best = (s, t, dst)
        if best[1] == th0 and best[2] == d0: break
    return best

def subsample(part, k):
    import copy
    p = copy.copy(part)
    idx = np.arange(0, part.n, k)
    p.pts = part.pts[:, idx]; p.col = part.col[idx]; p.n = len(idx)
    return p

def search2(part, fimg, falpha, pivot, dst0, thetas, shift_rng, coarse_step=4, sub=6):
    """coarse search on subsampled points, then full refine"""
    ps = subsample(part, sub)
    shifts = np.arange(-shift_rng, shift_rng + 1e-6, coarse_step)
    cand = []
    for th in thetas:
        Rb = None
        for dx in shifts:
            for dy in shifts:
                dst = (dst0[0] + dx, dst0[1] + dy)
                s = ps.score(rotmat(th, pivot, dst), fimg, falpha)
                cand.append((s, th, dst))
    cand.sort(key=lambda x: -x[0])
    best = None
    for s, th, dst in cand[:5]:
        r = refine(part, fimg, falpha, pivot, th, dst, th_rng=max(1.5, (thetas[1]-thetas[0]) if len(thetas) > 1 else 1.5), th_step=0.5, sh_rng=coarse_step, sh_step=1.0)
        r = refine(part, fimg, falpha, pivot, r[1], r[2])
        if best is None or r[0] > best[0]: best = r
    return best

def search3(part, fimg, falpha, pivot, dst0, thetas, shift_rng, coarse_step=4):
    ps6 = subsample(part, 6); ps2 = subsample(part, 2)
    shifts = np.arange(-shift_rng, shift_rng + 1e-6, coarse_step)
    cand = []
    for th in thetas:
        for dx in shifts:
            for dy in shifts:
                dst = (dst0[0] + dx, dst0[1] + dy)
                cand.append((ps6.score(rotmat(th, pivot, dst), fimg, falpha), th, dst))
    cand.sort(key=lambda x: -x[0])
    tstep = (thetas[1] - thetas[0]) if len(thetas) > 1 else 1.0
    mids = []
    for s, th, dst in cand[:3]:
        mids.append(refine(ps2, fimg, falpha, pivot, th, dst, th_rng=tstep, th_step=0.5, sh_rng=coarse_step, sh_step=1.0))
    mids.sort(key=lambda x: -x[0])
    return refine(part, fimg, falpha, pivot, mids[0][1], mids[0][2], th_rng=1.0, th_step=0.25, sh_rng=1.5, sh_step=0.5)

def handle_geom(a, prefer_dir=None):
    c = classes(a)
    ys, xs = np.nonzero(c['wood'])
    P = np.stack([xs, ys], 1).astype(float); m = P.mean(0)
    w, v = np.linalg.eigh(np.cov((P - m).T)); d = v[:, 1]
    if prefer_dir is not None and d @ prefer_dir < 0: d = -d
    t = (P - m) @ d
    return m, d, t.min(), t.max()

def end_is_real(a, p, d, sign):
    """True if the pixels just beyond end point p (along sign*d) are background."""
    H, W = a.shape[:2]; al = a[..., 3]
    hits = 0; tot = 0
    for k in range(4, 9):
        q = p + sign * d * k
        x, y = int(round(q[0])), int(round(q[1]))
        if 0 <= x < W and 0 <= y < H:
            tot += 1; hits += al[y, x] < 20
    return tot > 0 and hits / tot > 0.6
