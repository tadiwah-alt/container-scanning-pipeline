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
- [x] Confirm the CI run is green after the `apt-get upgrade` change
- [x] Pin the trivy-action to a commit SHA

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

## Secrets scanning (pre-commit hook + CI)

A committed secret stays in git history after the file is edited, so anyone with a clone or a fork still has it. The only real fix for a leaked key is to rotate it. This section adds two layers that try to stop a secret before it reaches GitHub, using [gitleaks](https://github.com/gitleaks/gitleaks).

### How it works

| Layer | Where it runs | What it does | Weakness it covers |
|---|---|---|---|
| Pre-commit hook (`hooks/pre-commit`) | My machine, before each commit | Scans only the staged changes and blocks the commit if a secret is found. If the scanner cannot run (Docker down), the commit is also blocked ("fail closed"). | Catches a secret before it is ever committed, let alone pushed. |
| CI job (`.github/workflows/secrets-scan.yml`) | GitHub Actions, on every push and pull request | Scans the full git history (`fetch-depth: 0`) and fails the run if a secret is found. | Covers a skipped or missing local hook (`git commit --no-verify`, a fresh clone). |

Supply-chain choices, using the same reasoning as the Trivy pipeline:
- `actions/checkout` pinned to a full commit SHA (v4.4.0) in both workflows, not the moving `v4` tag.
- The gitleaks image pinned by digest, not `latest`. Trade-off: I update the digest by hand when I want a newer gitleaks.
- `permissions: contents: read`, so the job can only read the repo.
- `--redact` on every scan, so a real secret is never printed to a terminal or a log.
- The scanner mounts the repo read-only (`:ro`).

### Enable the hook after cloning

```bash
git config core.hooksPath hooks
```

Git does not copy this setting on clone, so each clone has to run it once. CI is the backstop for anyone who forgets.

### Evidence

| Test | Result |
|---|---|
| Full-history scan of this repo before any changes | 22 commits, no leaks |
| Same scan across my other local repos | 7 more folders checked, no leaks (one had no git history, so its files were scanned directly) |
| Staged scan with a random fake token (`ghp_` plus 36 random characters, not a real token) | `github-pat` finding, exit code 1 |
| Commit with the fake token staged | Blocked by the hook, no commit created |
| Commit with only a harmless file staged | Passed |
| Push of the fake token with `--no-verify` to a test branch | CI run failed (red) with a `github-pat` finding |
| Push to `main` with no secret | CI run passed (green), 24 commits scanned (full history) |

Screenshots: `docs/secrets-scan-red-green.png` (red run on the test branch, green runs on `main`) and `docs/secrets-scan-finding.png` (the redacted finding in the CI log). The test branch was deleted afterwards.

### Problems I hit and what they taught me

| Problem | Cause | Lesson |
|---|---|---|
| The first CI design would have scanned one commit | `actions/checkout` fetches only the latest commit by default | Set `fetch-depth: 0` so the scan sees full history. The log showed 24 commits scanned. |
| `actions/checkout` was `@v4` in both workflows | Tags can be moved; I had pinned the Trivy action but not this one | Pin every third-party action to a commit SHA and note the version in a comment. |
| One of my repos was rooted in my home folder, with no `.gitignore` | A `git add .` from there could have staged `~/.aws` and `~/.ssh` | Check where a repo actually starts (`git rev-parse --show-toplevel`). I moved it into its own folder. |
| An early scan reported "1 commit" for the wrong folder | I ran it from the wrong directory | A clean result only means something if I know which repo it scanned. Check the commit count. |
| Docker Hub pulls timed out | Slow connection (same as the Trivy database download) | Retry the pull on its own before debugging anything else. |

### Limits

- Gitleaks matches known patterns. "No leaks found" means no match against those patterns, not proof that nothing sensitive is committed.
- The hook can be skipped with `--no-verify`, and a new clone needs the one-time `core.hooksPath` setting. CI is the backstop, but it runs after the push, so the secret is already on GitHub when it fails.
- GitHub's own push protection did not block my random fake token, so I have not tested it here.
- If a real secret ever leaks, the response is to **revoke and rotate it**, then clean history. Deleting the file is not enough.

### Planned

- Branch protection that requires the secrets-scan check before merging.
- A scheduled scan, so rule updates are applied to old history.
- A `.gitleaks.toml` with a custom rule and an allowlist for known-safe test values.
