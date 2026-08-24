FROM python:3.12-slim

# pg_dump uchun kerak (backup funksiyasi ishlashi uchun) — Python versiyasi bilan
# mos PostgreSQL client versiyasini o'rnatamiz
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]