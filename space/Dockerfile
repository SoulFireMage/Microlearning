# Hugging Face Space build: fetches a pinned commit of the GitHub repo, so the
# Space itself only holds this file and README.md. To deploy a new version,
# change REF to the new commit SHA.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860
WORKDIR $HOME/app

ARG REPO=SoulFireMage/Microlearning
ARG REF=97bf85e14b23a40137b000f837faa715771a41cc
RUN python -c "import sys, urllib.request; sys.stdout.buffer.write(urllib.request.urlopen('https://codeload.github.com/${REPO}/tar.gz/${REF}', timeout=120).read())" \
    | tar xz --strip-components=1 \
 && pip install --no-cache-dir --user -r requirements.txt \
 && python scripts/fetch_vendor.py \
 && rm -rf tests docs space

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
