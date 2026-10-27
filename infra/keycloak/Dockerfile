# Optimized Keycloak image for the production profile.
# Build-time options are baked in by `kc.sh build`, so the container starts with
# `start --optimized`. The realm import (aztdp-realm.json) holds only the
# placeholder ${KEYCLOAK_CLIENT_SECRET}; Keycloak resolves it from the container
# environment at import time, so the secret is never written into an image layer.
FROM quay.io/keycloak/keycloak:26.8 AS builder
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.8
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY aztdp-realm.json /opt/keycloak/data/import/aztdp-realm.json
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
