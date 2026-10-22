FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY enhancer ./enhancer
COPY bot.py .
# models (~450 MB) are downloaded on first start into MODELS_DIR; mount a volume there to keep them
ENV MODELS_DIR=/data/models PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
