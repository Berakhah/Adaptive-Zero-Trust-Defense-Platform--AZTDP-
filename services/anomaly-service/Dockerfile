FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./anomaly_service/
RUN mkdir -p /app/models
EXPOSE 8080
CMD ["uvicorn", "anomaly_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
