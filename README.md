# Enhance Bot

Telegram bot that returns photos and short videos in much higher quality.

- **Photo:** Real-ESRGAN x4 super-resolution, GPEN face restoration, then a crisp and vivid finish (edge-gated sharpening, halo-free local contrast, vibrance with skin and white protection). Output is up to 4K on the long side and is sent as an uncompressed file, plus a before/after image.
- **Video (≤ `MAX_VIDEO_SECONDS`):** every frame goes through AI upscaling (SPAN x4) and gets the same finish. Motion-compensated interpolation then brings the video to 120 fps. Audio is kept, and the file is kept under Telegram's 50 MB limit.

Everything runs on CPU through onnxruntime. Models (~450 MB) are downloaded on first start from public GitHub release assets into `MODELS_DIR`.

## Run

```bash
pip install -r requirements.txt     # plus ffmpeg on PATH
export BOT_TOKEN=...                # read only from the environment, never logged
python bot.py
```

## Railway

1. Create a service from this folder. It uses the `Dockerfile`.
2. Add these Variables:
   - `BOT_TOKEN` (required)
   - `MAX_VIDEO_SECONDS` (optional, default 15)
   - `VIDEO_SHORT_SIDE` (optional, default 1080)
3. Attach a volume at `/data` so the models are not downloaded again on every deploy.
4. More vCPUs mean faster jobs. One job runs at a time, and other users wait in a queue.

## Limits

- **Telegram Bot API:** bots can download files up to 20 MB and upload up to 50 MB.
- **CPU speed:** a photo takes about 1–2 minutes on 4 vCPU. A 5-second video takes several minutes, mostly for upscaling every frame and interpolating to 120 fps.

## Tests

```bash
python -m pytest -q tests
```
