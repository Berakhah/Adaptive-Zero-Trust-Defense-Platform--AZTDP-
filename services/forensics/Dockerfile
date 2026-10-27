FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . ./forensics/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD ["curl", "-sf", "http://localhost:8080/health"]
CMD ["uvicorn", "forensics.app:app", "--host", "0.0.0.0", "--port", "8080"]
