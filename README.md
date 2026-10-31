# Container Scanning Pipeline

A small DevSecOps project that builds a Flask API container image, scans it for vulnerabilities with [Trivy](https://trivy.dev) in GitHub Actions, and fails the build when there are fixable HIGH or CRITICAL findings. The goal is to find real problems in a Dockerfile, fix them, and show the before and after.

**Shows:** supply chain security, CI gating, Dockerfile hardening.

## Status

- [x] Baseline image built from an unmodified Dockerfile
- [x] Baseline scanned locally and documented ([`docs/baseline-scan.txt`](docs/baseline-scan.txt))
- [x] GitHub Actions workflow that builds the image and scans it with Trivy
- [x] Harden the Dockerfile and push (first run is expected to fail, the hardened run should pass)
- [ ] Re-scan and record the after-results in this README
- [ ] Add a `.dockerignore`, then pin the action to a commit SHA

## The app under test

The Dockerfile, `requirements.txt`, and `app/` folder are copied from my [cloud-banking-api](https://github.com/tadiwah-alt/cloud-banking-api) project (Flask, Flask-CORS, psycopg2-binary). I copied only what the image build needs. The database and frontend are not part of the scan.

## Baseline results

Scanned with Trivy 0.76.1 on `python:3.11-slim` (Debian 13.7). Severity filter: HIGH and CRITICAL.

| Area | Findings | Notes |
|---|---|---|
| Debian OS packages | 44 HIGH | Only **8 unique CVEs**. The same few CVEs repeat across packages built from the same source (for example, util-linux ships as nine packages). None has a fixed version available yet. |
| Python packages | 2 HIGH | `jaraco.context` 5.3.0 and `wheel` 0.45.1, both bundled inside `setuptools` 79.0.1 (`setuptools/_vendor/`), not my app's dependencies. Both have fixed versions. |
| App dependencies (Flask, Werkzeug, psycopg2-binary, and others) | 0 | Clean at the time of the scan. |

Image size: 240 MB on disk.

Raw output: [`docs/baseline-scan.txt`](docs/baseline-scan.txt).

## Dockerfile problems found in the baseline

| Issue | Why it matters |
|---|---|
| Floating base image tag (`python:3.11-slim`) | The same Dockerfile can build a different image next month. |
| Unpinned dependencies in `requirements.txt` | Builds are not reproducible. A fresh build installs whatever is newest, and a cached layer can silently keep old versions. |
| Container runs as root | A compromised process has root inside the container. |
| `COPY . .` with no `.dockerignore` | The image contained `.env`, `.git`, the README, and the Dockerfile. The `.env` was empty here, but a real one would have been baked into an image layer. `.gitignore` does not protect against this. |
| `pip install` without `--no-cache-dir` | Leaves download files in the image, which adds size and more to scan. |

## Pipeline policy

The workflow ([`.github/workflows/scan.yml`](.github/workflows/scan.yml)) runs on every push to `main` and on pull requests. It builds the image, tags it with the commit SHA, and runs Trivy with:

- `severity: HIGH,CRITICAL`
- `ignore-unfixed: true`
- `exit-code: '1'` (a finding fails the build)

**Why `ignore-unfixed`:** all 44 OS findings currently have no patched package, so a gate that failed on them could never pass and people would learn to ignore a permanently red build. The gate blocks on issues I can act on. Unfixed findings stay visible in the full scan and are listed below as accepted risks, with a reason.

**Trade-off:** unfixed issues do not block a merge, so they depend on being reviewed. The scan results can also change without any code change, because new CVEs are published every day. A build that passed last week can fail today.

**Permissions:** the job has `contents: read` only.

## Accepted risks (unfixed OS findings)

To be completed after hardening. For each remaining finding, I will record the package, the CVE, why it is not fixable yet, and what I did instead.

## Planned hardening

1. Pin the base image to an exact version (and consider the digest)
2. Pin dependencies in `requirements.txt`
3. Upgrade or remove `setuptools` and `wheel` in the final image
4. Create and run as a non-root user
5. Add a `.dockerignore`
6. Use `pip install --no-cache-dir`
7. Try a multi-stage build and a smaller base image, then compare findings and size

## Reproduce locally

```bash
docker build -t banking-api:baseline .
trivy image --severity HIGH,CRITICAL banking-api:baseline
trivy image --severity HIGH,CRITICAL --ignore-unfixed banking-api:baseline
```

## What I learned

- Most findings in the baseline image came from the operating system packages in the base image, not from my own dependencies.
- Scanner totals inflat counts: one vulnerable source package can show up as many rows.
- `--ignore-unfixed` changes what a gate can enforce, so the policy needs a deliberate decision.
- `.gitignore` does not apply to Docker builds. A separate `.dockerignore` is needed.

## Project structure

```
container-scanning-pipeline/
├── .github/workflows/scan.yml   # build and scan on every push
├── app/                         # Flask app copied from cloud-banking-api
├── docs/baseline-scan.txt       # unmodified baseline scan output
├── Dockerfile                   # baseline, to be hardened
├── requirements.txt
└── README.md
```