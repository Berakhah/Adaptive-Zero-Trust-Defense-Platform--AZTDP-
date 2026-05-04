#!/usr/bin/env bash
# Generate a self-signed TLS certificate for local development.
# In production replace with certs from Let's Encrypt or your CA.
set -euo pipefail

CERTS_DIR="$(dirname "$0")/certs"
mkdir -p "$CERTS_DIR"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$CERTS_DIR/server.key" \
  -out    "$CERTS_DIR/server.crt" \
  -days   365 \
  -subj   "/C=US/ST=Dev/L=Local/O=AZTDP/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "Self-signed cert written to $CERTS_DIR"
echo "NOTE: For production use certificates from a trusted CA (e.g. Let's Encrypt certbot)."
