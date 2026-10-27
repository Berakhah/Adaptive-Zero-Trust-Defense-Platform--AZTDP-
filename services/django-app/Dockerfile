FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . .
USER 10001:10001
EXPOSE 8000
# Host + X-Forwarded-Proto satisfy ALLOWED_HOSTS and SECURE_SSL_REDIRECT in production.
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD ["sh", "-c", "curl -sf -H \"Host: ${AZTDP_ALLOWED_HOSTS%%,*}\" -H \"X-Forwarded-Proto: https\" http://localhost:8000/health || exit 1"]
CMD ["gunicorn", "aztdp_django.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "30"]
