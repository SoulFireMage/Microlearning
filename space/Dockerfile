# Hugging Face Space build: fetches a pinned commit of the GitHub repo, so the
# Space itself only holds this file and README.md. To deploy a new version,
# change REF to the new commit SHA.
#
# Dev Mode compatible (HF Pro): bash/curl/wget/procps/git/git-lfs present,
# code in /app owned by uid 1000, CMD defined.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends bash curl wget procps git git-lfs \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 user \
 && mkdir /app && chown user:user /app
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860
WORKDIR /app

ARG REPO=SoulFireMage/Microlearning
ARG REF=4009a7932ab26a1560258b992d397612494b5bb7
RUN curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/${REF}" | tar xz --strip-components=1 \
 && pip install --no-cache-dir --user -r requirements.txt \
 && python scripts/fetch_vendor.py \
 && rm -rf tests docs space

EXPOSE 7860
# `exec` makes uvicorn the CMD process itself, so a stop signal reaches it.
# Without it, Dev Mode's restarts orphan the old server, which keeps port
# 7860 and makes every restart fail with "address already in use".
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
