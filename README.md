# Container Scanning Pipeline

A small DevSecOps project that builds a Flask API container image, scans it for vulnerabilities with [Trivy](https://trivy.dev) in GitHub Actions, and fails the build when there are fixable HIGH or CRITICAL findings. The goal is to find real problems in a Dockerfile, fix them, and show the before and after.

**Shows:** supply chain security, CI gating, Dockerfile hardening.

## Status

- [x] Baseline image built from an unmodified Dockerfile
- [x] Baseline scanned locally and documented ([`docs/baseline-scan.txt`](docs/baseline-scan.txt))
- [x] GitHub Actions workflow that builds the image and scans it with Trivy
- [x] First runs failed on two fixable findings, as expected (the gate works)
- [x] Hardened: `--no-cache-dir`, upgraded `setuptools` and `wheel`, `.dockerignore` (CI went green)
- [x] Hardened: runs as a non-root user (CI green)
- [x] All dependencies pinned to exact versions
- [x] Base image pinned to an exact version tag
- [ ] Pin the trivy-action to a commit SHA
- [ ] Record the unfixed OS findings as accepted risks (see below)

## The app under test

The Dockerfile, `requirements.txt`, and `app/` folder are copied from my [cloud-banking-api](https://github.com/tadiwah-alt/cloud-banking-api) project (Flask, Flask-CORS, psycopg2-binary). I copied only what the image build needs. The database (run by Docker Compose in that project) and the front end are not part of this scan, and the image here is built and scanned but never run against a database.

## Before and after

Scanned with Trivy 0.76.1, severity HIGH and CRITICAL.

| | Baseline | After hardening |
|---|---|---|
| Debian OS packages (all findings) | 44 HIGH (8 unique CVEs, none had a fix available) | Not re-measured without `--ignore-unfixed` |
| Debian OS packages (fixable only, what CI gates on) | 0 | 0 |
| Python packages (fixable) | 2 HIGH (`jaraco.context`, `wheel`) | 0 |
| App dependencies (Flask, Werkzeug, and others) | 0 | 0 |
| Files in the image | included `.env`, `.git`, README, Dockerfile, docs | only `app/` and `requirements.txt` |
| Build context sent to Docker | 197.6 kB | about 21.5 kB |
| Runs as | root | `appuser` (checked with `whoami`) |

Raw baseline output: [`docs/baseline-scan.txt`](docs/baseline-scan.txt).

## What was wrong, and what fixed it

| Problem in the baseline | Why it matters | Fix |
|---|---|---|
| `setuptools` 79.0.1 from the base image bundled vulnerable copies of `jaraco.context` and `wheel` in `setuptools/_vendor/` | Known CVEs, both with fixed versions | `pip install --upgrade setuptools wheel` (setuptools 84.2.1 replaced the whole `_vendor/` folder, which cleared both) |
| `COPY . .` with no `.dockerignore` | The image contained `.env`, `.git`, and other files. A real `.env` would be baked into an image layer. `.gitignore` does not apply to Docker builds. | Added `.dockerignore` |
| `pip install` without `--no-cache-dir` | Leaves download files in the image | Added the flag |
| Container ran as root | A compromised process could modify or delete anything in the container | Created `appuser` and switched with `USER`. App files stay owned by root, so the app can read but not modify them. |
| Unpinned `requirements.txt` | A fresh build installs whatever is newest, so results change without any commit | Pinned every package (including transitive ones) to the exact version |
| Floating base tag `python:3.11-slim` | The OS and Python layers can change between builds | Pinned to an exact version tag (`python:3.11.17-slim`) |

## Pipeline policy

The workflow ([`.github/workflows/scan.yml`](.github/workflows/scan.yml)) runs on every push to `main` and on pull requests. It builds the image, tags it with the commit SHA, and runs Trivy with:

- `severity: HIGH,CRITICAL`
- `ignore-unfixed: true`
- `exit-code: '1'` (a finding fails the build)

**Why `ignore-unfixed`:** all 44 baseline OS findings had no patched package available, so a gate that failed on them could never pass, and people would learn to ignore a permanently red build. The gate blocks on issues I can act on. Unfixed findings stay visible in a full scan.

**Trade-offs:**
- Unfixed issues do not block a merge, so they depend on being reviewed.
- Results can change without any code change, because new CVEs are published every day. A build that passed last week can fail today.
- The check runs after a push, so it marks the commit as failed but does not stop it landing on `main`. Blocking merges would need branch protection with required status checks.
- Pinning makes builds repeatable, but pinned versions do not pick up security fixes by themselves. Something has to prompt updates, such as a scheduled re-scan or Dependabot.

**Permissions:** the job has `contents: read` only.

## Accepted risks (unfixed OS findings)

Not yet recorded. To fill this in, run a full scan without `--ignore-unfixed` and list each remaining finding with the package, the CVE, why it is not fixable yet, and what I did instead:

```bash
trivy image --severity HIGH,CRITICAL banking-api:latest
```

## Reproduce locally

```bash
docker build -t banking-api:latest .
trivy image --severity HIGH,CRITICAL --ignore-unfixed banking-api:latest

# prove it runs as a non-root user and contains only what it needs
docker run --rm banking-api:latest whoami
docker run --rm banking-api:latest ls -la /app

# prove the pins hold (no cache, then compare with requirements.txt)
docker build --no-cache -t banking-api:check .
docker run --rm banking-api:check pip freeze
```

## What I learned

- Most findings in the baseline image came from the operating system packages in the base image, not from my own dependencies.
- The two fixable Python findings were not in my requirements. They were copies bundled inside `setuptools`, which shipped with the base image. Upgrading `setuptools` replaced them.
- Scanner totals inflated count: one vulnerable source package can show up as many rows.
- `--ignore-unfixed` changes what a gate can enforce, so the policy needs a deliberate decision.
- Trivy checks packages for known CVEs. It cannot see configuration problems like running as root, which is what a tool like Checkov is suited for. Different tools answer different questions.
- `.gitignore` does not apply to Docker builds. A separate `.dockerignore` is needed.
- A clean build is not proof. Rebuilding with `--no-cache` and comparing `pip freeze` to `requirements.txt` caught a truncated version pin (`Werkzeug==3.1.` was silently read by pip as `3.1.0`, an older release than the one I had been running).

## Project structure

```
container-scanning-pipeline/
├── .github/workflows/scan.yml   # build and scan on every push
├── app/                         # Flask app copied from cloud-banking-api
├── docs/baseline-scan.txt       # unmodified baseline scan output
├── .dockerignore                # keeps secrets and build-only files out of the image
├── Dockerfile                   # hardened
├── requirements.txt             # every package pinned
└── README.md
```