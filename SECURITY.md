# Security policy

## Supported versions

Security fixes are made on the latest release and the `main` branch. Please upgrade before reporting.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub: open the **Security** tab of this repository and click **Report a vulnerability**. Only the maintainer can see the report.

Please include:

- what an attacker could do, and which version or commit you tested
- steps to reproduce (a request, script or sample file helps)
- any suggested fix

What to expect:

- an acknowledgement within 3 days
- an assessment and a plan within 10 days
- a fix and a published advisory crediting you (unless you prefer otherwise) once a patched version is released

## Scope

In scope: the API server, search engines integration, MCP server, CLI and the Docker image built from this repository.

Out of scope: problems in the third-party services this project talks to, attacks that need shell or file access on the machine running it, and deployments that ignore the README's advice (for example exposing an admin interface publicly without protection).

## Running it safely

- Put it behind HTTPS when it is reachable from the internet.
- Keep it updated (`docker compose pull && docker compose up -d`, or `pip install -U`).
- Treat anything it returns from outside sources as untrusted data.
