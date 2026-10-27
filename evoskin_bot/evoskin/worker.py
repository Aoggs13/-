"""Run one skin job in its own process:  python -m evoskin.worker skin.bin out_dir

The bot keeps only the Telegram side in memory; a job that runs out of memory kills this
process, not the bot. Exit codes: 0 ok, 3 not an image."""
import json
import os
import sys


def main():
    threads = os.environ.get("EVOSKIN_THREADS", "2")
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[k] = threads
    import cv2
    cv2.setNumThreads(int(threads))
    from . import pipeline

    src, out = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        data = f.read()
    try:
        res = pipeline.run(data)
    except ValueError:
        sys.exit(3)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "frames.zip"), "wb") as f:
        f.write(res.zip_bytes)
    with open(os.path.join(out, "sheet.png"), "wb") as f:
        f.write(res.sheet)
    h, w = res.frames[0][1].shape[:2]
    with open(os.path.join(out, "info.json"), "w") as f:
        json.dump(dict(res.info, seconds=round(res.seconds, 1), width=w, height=h), f)


if __name__ == "__main__":
    main()
