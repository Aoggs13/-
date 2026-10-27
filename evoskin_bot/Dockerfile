FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY evoskin ./evoskin
COPY bot.py .
# the LaMa inpainting model (~90 MB) is downloaded on first start into MODELS_DIR; mount a volume there to keep it
ENV MODELS_DIR=/data/models PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
