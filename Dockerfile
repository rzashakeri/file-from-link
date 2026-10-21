FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates nodejs && rm -rf /var/lib/apt/lists/*
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -U yt-dlp
COPY app ./app
ENV PYTHONUNBUFFERED=1
CMD ["python","-m","app.bot"]
