FROM python:3.11-slim
RUN apt-get update && apt-get install -y chromium chromium-driver && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY kubur_operasyon.py .
# Hemen çalıştır ve çıktıyı göster
CMD ["sh", "-c", "echo '=== Starting bot ===' && python -u kubur_operasyon.py 2>&1"]
