FROM python:3.12-slim
WORKDIR /attack_sim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8090
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8090"]
