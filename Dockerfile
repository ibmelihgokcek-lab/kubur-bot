FROM python:3.11-slim

# Sistem güncellemeleri ve Chromium kurulumu (Selenium için)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizini
WORKDIR /app

# Gereksinimleri kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bot kodunu kopyala
COPY kubur_operasyon.py .

# Başlatma komutu
CMD ["python", "kubur_operasyon.py"]
