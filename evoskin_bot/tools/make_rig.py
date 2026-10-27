"""Turn rig4.json (output of rigfit4.py) into evoskin/assets/rig.json."""
import json, numpy as np
r = json.load(open('rig4.json'))
pv = r['pivots']
REF_LIKE = {'idle_1', 'idle_2', 'idle_3', 'idle_4', 'idle_5', 'idle_6', 'attack_1', 'attack_5'}
RAISED = {'attack_2', 'attack_4', 'attack_6'}
frames = {}
for name, rec in r['frames'].items():
    f = {}
    for k in ('body', 'head', 'back_hand'):
        f[k] = [round(rec[k]['theta'], 3), round(rec[k]['dst'][0], 3), round(rec[k]['dst'][1], 3)]
    f['scythe'] = [round(rec['handle']['theta'], 3), round(rec['handle']['dst'][0], 3), round(rec['handle']['dst'][1], 3)]
    fh = rec['front_hand']
    if name in RAISED or name in REF_LIKE:
        f['front_hand'] = [round(fh['theta'], 3), round(fh['dst'][0], 3), round(fh['dst'][1], 3)]
    else:
        f['front_hand'] = None   # follows the scythe (hand is mostly hidden behind the body)
    if name in REF_LIKE:
        f['order'] = 'ref'
    elif name in RAISED:
        f['order'] = ['scythe', 'body', 'head', 'back_hand', 'sleeve', 'front_hand']
    else:
        f['order'] = ['scythe', 'front_hand', 'body', 'head', 'back_hand']
    frames[name] = f
rig = {
    'source': 'black reaper, 19 frames, 376x312; transforms map the idle_6 pose to each frame',
    'canvas': [376, 312],
    'ref': 'idle_6',
    'pivots': {'body': pv['body'], 'head': pv['head'], 'back_hand': pv['back_hand'], 'scythe': pv['handle'], 'front_hand': pv['front_hand']},
    'handle_len': r['handle_len'],
    'blade_pivot': pv['blade'],
    'handle_top': [326.2, 124.7],   # far end of the wood in idle_6
    'sleeve': {'shoulder': [212.0, 166.0], 'wrist_offset': [-5.0, -7.0], 'radius': 11.0},
    'sequences': {
        'idle': ['idle_1', 'idle_5', 'idle_2', 'idle_3', 'idle_4', 'idle_6'],
        'fly': ['fly_4', 'fly_1', 'fly_5', 'fly_2', 'fly_3'],
        'attack': ['attack_1', 'attack_6', 'attack_4', 'attack_2', 'attack_7', 'attack_8', 'attack_3', 'attack_5'],
    },
    'frames': frames,
}
json.dump(rig, open('../evoskin/assets/rig.json', 'w'), indent=1)
