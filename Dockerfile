FROM python:3.11-slim

# HF Spaces run containers as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860
WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user app ./app
COPY --chown=user static ./static
COPY --chown=user scripts ./scripts
# No-op when static/vendor is present; fills it in when an upload skipped it.
RUN python scripts/fetch_vendor.py

EXPOSE 7860
# One worker: SQLite has a single writer, and the app keeps no other state.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
