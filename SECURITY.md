# Security policy

AZTDP is a personal reference platform, not a hosted service. Nobody runs it in production on
my behalf, so a vulnerability here affects people who copied its patterns or deployed it
themselves.

## Reporting a vulnerability

Report it privately through GitHub
([Security → Report a vulnerability](https://github.com/Berakhah/aztdp/security/advisories/new))
with a description, steps to reproduce, and impact. Do not open a public issue for a suspected
vulnerability. I aim to acknowledge within 5 business days.

Only `main` is supported. There are no maintained release branches or backports.

## Scope highlights

- A request that reaches business logic without a valid JWT, or with a risk decision the
  engine should have denied.
- A way to bypass token revocation, the OPA policy decision, or the per-request risk score.
- A secret that works outside a local dev stack.

## Known and intended

- `.env.dev` is committed on purpose. It holds dev-only defaults (database role passwords,
  Redis, Keycloak admin and client secret, the platform's signing and HMAC keys) because the base
  `docker-compose.yml` refuses to start without them. Every value is public by being committed,
  and the file's own header says not to use it outside a local stack. Reporting that file is not a finding;
  reporting a value from it that works against something real is.
- `infra/` Kubernetes and Helm manifests are not maintained (see the README).
