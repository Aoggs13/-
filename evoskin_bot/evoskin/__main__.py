"""CLI: python -m evoskin skin.png out_dir"""
import os
import sys

from . import pipeline


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    src, out = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        res = pipeline.run(f.read())
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "skin_frames.zip"), "wb") as f:
        f.write(res.zip_bytes)
    with open(os.path.join(out, "sheet.png"), "wb") as f:
        f.write(res.sheet)
    print("done in %.1fs" % res.seconds, res.info)


if __name__ == "__main__":
    main()
