# Container Scanning Pipeline (S/M)

Build a small app image, scan with Trivy in GitHub Actions, fail the build on high-severity findings, harden the Dockerfile (non-root user, minimal base image, pinned versions). 

Shows: supply chain security, CI gating