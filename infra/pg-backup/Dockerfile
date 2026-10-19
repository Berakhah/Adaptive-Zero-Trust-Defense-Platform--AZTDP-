# pg-backup: pg_dump -Fc of every AZTDP database + pg_dumpall --globals-only on a
# schedule. Built from the same postgres major/digest as the database so the dump
# tools always match the server. Runs as the unprivileged postgres user (uid 70).
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea

COPY --chmod=0555 backup.sh backup-loop.sh healthcheck.sh /
# /backups is created here so the named volume mounted on it inherits postgres ownership.
RUN mkdir -p /backups && chown postgres:postgres /backups

USER postgres
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 CMD ["/healthcheck.sh"]
ENTRYPOINT ["/backup-loop.sh"]
