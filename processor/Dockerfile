FROM python:3.12-slim

WORKDIR /app

# ffmpeg for audio/video conversion + audio extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PORT=8080

CMD ["functions-framework", "--target=process_track", "--signature-type=cloudevent"]
