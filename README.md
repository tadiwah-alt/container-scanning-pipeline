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
- [x] A newer vulnerability database found 4 fixable OS findings; fixed with `apt-get upgrade` (local scan: 0 fixable)
- [x] After-hardening scan saved ([`docs/after-scan.txt`](docs/after-scan.txt))
- [ ] Confirm the CI run is green after the `apt-get upgrade` change
- [ ] Pin the trivy-action to a commit SHA

## The app under test

The Dockerfile, `requirements.txt`, and `app/` folder are copied from my [cloud-banking-api](https://github.com/tadiwah-alt/cloud-banking-api) project (Flask, Flask-CORS, psycopg2-binary). I copied only what the image build needs. The database (run by Docker Compose in that project) and the front end are not part of this scan, and the image here is built and scanned but never run against a database.

## Before and after

Scanned with Trivy 0.76.1, severity HIGH and CRITICAL. The vulnerability database changes daily, so numbers from different days are not directly comparable.

| | Baseline | After hardening |
|---|---|---|
| Debian OS packages, all findings | 44 HIGH (8 unique CVEs), none had a fix | 47 HIGH (11 unique CVEs), none has a fix. Higher than the baseline because the database is newer. |
| Debian OS packages, fixable (what CI gates on) | 0 | 0 (the newer database first showed 4, fixed by `apt-get upgrade`) |
| Python packages, fixable | 2 HIGH (`jaraco.context`, `wheel`) | 0 |
| App dependencies (Flask, Werkzeug, and others) | 0 | 0 |
| Files in the image | included `.env`, `.git`, README, Dockerfile, docs | only `app/` and `requirements.txt` |
| Build context sent to Docker | 197.6 kB | about 21.5 kB |
| Runs as | root | `appuser` (checked with `whoami`) |

Raw output: [`docs/baseline-scan.txt`](docs/baseline-scan.txt) and [`docs/after-scan.txt`](docs/after-scan.txt).

## What was wrong, and what fixed it

| Problem | Why it matters | Fix |
|---|---|---|
| `setuptools` 79.0.1 from the base image bundled vulnerable copies of `jaraco.context` and `wheel` in `setuptools/_vendor/` | Known CVEs, both with fixed versions | `pip install --upgrade setuptools wheel` (setuptools 84.2.1 replaced the whole `_vendor/` folder, which cleared both) |
| `apt`, `libapt-pkg7.0`, and `zlib1g` had known CVEs with fixes released after the image was built | A newer vulnerability database made them show up with no code change | `apt-get update && apt-get upgrade -y` as root, before the `USER` line, then remove the apt lists |
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

**Why `ignore-unfixed`:** most OS findings have no patched package available, so a gate that failed on them could never pass, and people would learn to ignore a permanently red build. The gate blocks on issues I can act on. Unfixed findings stay visible in a full scan and are listed below.

**Trade-offs:**
- Unfixed issues do not block a merge, so they depend on being reviewed.
- Results can change without any code change, because new CVEs are published every day. This happened here: an image that scanned clean on one day showed 4 fixable findings after the database updated.
- `apt-get upgrade` installs whatever Debian publishes on the day of the build. That trades some repeatability for getting OS patches. The base image tag and every Python package stay pinned.
- The check runs after a push, so it marks the commit as failed but does not stop it landing on `main`. Blocking merges would need branch protection with required status checks.
- Pinning makes builds repeatable, but pinned versions do not pick up security fixes by themselves. Something has to prompt updates, such as a scheduled re-scan or Dependabot.

**Permissions:** the job has `contents: read` only.

## Accepted risks (unfixed OS findings)

47 HIGH findings remain, from 11 unique CVEs. The scan lists none of them as fixable: Debian reports 46 as `affected` (no patch yet) and 1 as `fix_deferred` (Debian chose to patch later). They show up as many rows because the same source package ships as several binary packages.

| Package family | CVEs | Debian status | Why I am accepting it for now |
|---|---|---|---|
| util-linux (`bsdutils`, `libblkid1`, `liblastlog2-2`, `libmount1`, `libsmartcols1`, `libuuid1`, `login`, `mount`, `util-linux`) | CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | affected | No patch exists. These concern mount helpers and `nsenter`, which the app does not use. The app runs as a non-root user. |
| acl (`libacl1`) | CVE-2026-54369 | affected | No patch exists. The app does not call the library directly. |
| ncurses (`libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin`) | CVE-2025-69720 | affected | No patch exists. A terminal library, not used by a web API. |
| sqlite (`libsqlite3-0`) | CVE-2026-119373, CVE-2026-119374, CVE-2026-119379 | affected | No patch exists. The app uses PostgreSQL and does not use SQLite. |
| systemd (`libsystemd0`, `libudev1`) | CVE-2026-16742 | affected | No patch exists. The finding concerns `systemd-homed`, which does not run in a container. |
| perl (`perl-base`) | CVE-2026-9538 | fix_deferred | Debian has deferred the fix. The app does not use Perl. |

"The app does not use it" is my reading of the app and the CVE titles. I have not tested exploitability, and an attacker who already has code execution in the container could still reach these packages. The real mitigations are the non-root user and a smaller base image (planned).

Review this list whenever the scan changes: any row that gains a fixed version becomes a fix, not an accepted risk.

## Planned

- Try a smaller base image or multi-stage build, then compare findings and size
- Pin `trivy-action` to a commit SHA
- Re-scan on a schedule, or use Dependabot, so new CVEs and new fixes are noticed
- Add Checkov for Dockerfile configuration checks (Trivy cannot see problems like running as root)

## Reproduce locally

```bash
docker build -t banking-api:latest .
trivy image --severity HIGH,CRITICAL --ignore-unfixed banking-api:latest   # what CI gates on
trivy image --severity HIGH,CRITICAL banking-api:latest                    # full list, including unfixed

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
- A scan result is only valid for the day it ran. A newer vulnerability database turned a clean image into one with 4 fixable findings, with no change to my code.
- Scanner totals overcount: one vulnerable source package can show up as many rows. The Status column (`fixed`, `affected`, `fix_deferred`) shows which ones I can act on.
- `--ignore-unfixed` changes what a gate can enforce, so the policy needs a deliberate decision.
- Trivy checks packages for known CVEs. It cannot see configuration problems like running as root, which is what a tool like Checkov is for.
- `.gitignore` does not apply to Docker builds. A separate `.dockerignore` is needed.
- A clean build is not proof. Rebuilding with `--no-cache` and comparing `pip freeze` to `requirements.txt` caught a truncated version pin (`Werkzeug==3.1.` was silently read by pip as `3.1.0`, an older release).

## Project structure

```
container-scanning-pipeline/
├── .github/workflows/scan.yml   # build and scan on every push
├── app/                         # Flask app copied from cloud-banking-api
├── docs/baseline-scan.txt       # unmodified baseline scan output
├── docs/after-scan.txt          # full scan after hardening, including unfixed findings
├── .dockerignore                # keeps secrets and build-only files out of the image
├── Dockerfile                   # hardened
├── requirements.txt             # every package pinned
└── README.md
```