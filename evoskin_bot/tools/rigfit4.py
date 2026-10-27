import cv2, numpy as np, glob, os, json, time
from fitcore import *

ra = load('black_reaper/idle_6.png'); rimg = on_bg(ra); P = ref_parts(ra); c = classes(ra)
masks = {
    'head': P['head'],
    'body': P['body'] & ~dil(c['wood'] | c['darkbrown'], 4),
    'back_hand': P['back_hand'],
    'handle': P['handle'],
    'blade': P['blade'],
    'front_hand': P['front_hand'],
}
parts = {k: Part(rimg, m) for k, m in masks.items()}
m0, d0, t0a, t0b = handle_geom(ra, prefer_dir=np.array([1.0, -0.6]))
L = t0b - t0a; bot_ref = m0 + d0 * t0a; ang_ref = np.degrees(np.arctan2(d0[1], d0[0]))
piv_blade = m0 + d0 * ((parts['blade'].center - m0) @ d0)
grip_ref = parts['front_hand'].center
piv = {'head': np.array([195.0, 160.0]), 'body': np.array([188.0, 205.0]), 'back_hand': parts['back_hand'].center}

def fit_frame(fp):
    t0 = time.time()
    name = os.path.basename(fp)[:-4]
    fa = load(fp); fimg = on_bg(fa); fal = fa[..., 3].astype(np.float32)
    rec = {}
    for k in ('head', 'body', 'back_hand'):
        lim = {'head': 25, 'body': 15, 'back_hand': 45}[k]
        b = search3(parts[k], fimg, fal, piv[k], piv[k], np.arange(-lim, lim + 0.1, 2.5), 32)
        rec[k] = dict(theta=b[1], dst=list(b[2]), inl=b[0])
    cands = []
    for sign in (1, -1):
        m, d, ta, tb = handle_geom(fa, prefer_dir=sign * d0)
        bot = m + d * ta; top = m + d * tb; vis = tb - ta
        if vis < L - 6:
            br_ = end_is_real(fa, bot, d, -1); tr_ = end_is_real(fa, top, d, +1)
            if tr_ and not br_: bot = top - d * L
        ang = np.degrees(np.arctan2(d[1], d[0]))
        th = -(ang - ang_ref)
        b = refine(parts['handle'], fimg, fal, bot_ref, th, tuple(bot), th_rng=3, th_step=0.5, sh_rng=4, sh_step=1)
        b = refine(parts['handle'], fimg, fal, bot_ref, b[1], b[2])
        A_h = rotmat(b[1], bot_ref, b[2]); pf = A_h @ np.array([*piv_blade, 1])
        bb = search3(parts['blade'], fimg, fal, piv_blade, pf, b[1] + np.arange(-35, 35.1, 2.0), 8, coarse_step=2)
        cands.append((b[0] + bb[0], b, bb, vis))
    cands.sort(key=lambda x: -x[0])
    _, b, bb, vis = cands[0]
    rec['handle'] = dict(theta=b[1], dst=list(b[2]), inl=b[0], vis=float(vis))
    rec['blade'] = dict(theta=bb[1], dst=list(bb[2]), inl=bb[0], rel=bb[1] - b[1])
    A_h = rotmat(b[1], bot_ref, b[2]); gf = A_h @ np.array([*grip_ref, 1])
    fb = search3(parts['front_hand'], fimg, fal, grip_ref, gf, b[1] + np.arange(-60, 60.1, 3), 14, coarse_step=2)
    rec['front_hand'] = dict(theta=fb[1], dst=list(fb[2]), inl=fb[0], rel=fb[1] - b[1], off=(np.array(fb[2]) - gf).tolist())
    print('%-9s ' % name + ' '.join('%s:%.1f(%.0f,%.0f)%.2f' % (k[:5], v['theta'], v['dst'][0], v['dst'][1], v['inl']) for k, v in rec.items()),
          'blade_rel=%.1f hand_rel=%.1f hand_off=(%.0f,%.0f) vis=%.0f  %.1fs' % (rec['blade']['rel'], rec['front_hand']['rel'], *rec['front_hand']['off'], vis, time.time() - t0), flush=True)
    return name, rec

if __name__ == '__main__':
    from multiprocessing import Pool
    out = dict(ref='idle_6', pivots=dict(handle=bot_ref.tolist(), blade=piv_blade.tolist(), front_hand=grip_ref.tolist(),
               head=piv['head'].tolist(), body=piv['body'].tolist(), back_hand=piv['back_hand'].tolist()), handle_len=L, frames={})
    with Pool(4) as pool:
        for name, rec in pool.imap_unordered(fit_frame, sorted(glob.glob('black_reaper/*.png'))):
            out['frames'][name] = rec
    json.dump(out, open('rig4.json', 'w'), indent=1)
    print('done')
