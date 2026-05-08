FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run Jobs はコンテナ終了で完了とみなす
CMD ["python", "main.py", "--report-type", "monthly"]
