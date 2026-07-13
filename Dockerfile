FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent data (bot_data.json) should be mounted as a volume so watches
# survive container restarts/rebuilds, e.g.:
#   docker run --env-file .env -v bot_data:/app/data -e DATA_FILE_PATH=/app/data/bot_data.json <image>
VOLUME ["/app/data"]

CMD ["python", "bot.py"]
