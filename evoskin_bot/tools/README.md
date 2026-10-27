# Rig tools

`black_reaper/` holds the 19 reference frames (idle 6, fly 5, attack 8). The rig in
`../evoskin/assets/rig.json` was produced from them:

```
cd tools
python rigfit4.py     # fits head/body/hands/scythe transforms per frame -> rig4.json (a few minutes, 4 cores)
python make_rig.py    # rig4.json -> ../evoskin/assets/rig.json (+ draw order, sleeve, sequences)
```

`brseg.py` splits the black reaper idle_6 pose into parts by colour; `fitcore.py` holds the
point-sampled rigid fitting used by `rigfit4.py`.
