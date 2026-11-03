# pg-backup: pg_dump -Fc of every AZTDP database + pg_dumpall --globals-only on a
# schedule. Built from the same postgres major/digest as the database so the dump
# tools always match the server. Runs as the unprivileged postgres user (uid 70).
FROM postgres:18-alpine@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5

COPY --chmod=0555 backup.sh backup-loop.sh healthcheck.sh /
# /backups is created here so the named volume mounted on it inherits postgres ownership.
RUN mkdir -p /backups && chown postgres:postgres /backups

USER postgres
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 CMD ["/healthcheck.sh"]
ENTRYPOINT ["/backup-loop.sh"]
