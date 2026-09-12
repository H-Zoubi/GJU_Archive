FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# GJU credential verifier drives a real Chromium browser (MyGJU's WAF blocks
# plain headless requests) — install the browser binary and its OS deps.
RUN playwright install --with-deps chromium

COPY . .

# Normalize line endings in case this was checked out with CRLF on Windows,
# then make sure the entrypoint is actually executable in the image.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000

# Lets `docker compose ps` / `depends_on: condition: service_healthy` know
# when the server is actually answering, not just that the process started --
# migrations + the catalog seed run before this can pass. Plain urllib so no
# extra package (curl/wget) is needed in the slim image.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/', timeout=3)" || exit 1

# Invoked via `sh` rather than relying on the executable bit: docker-compose
# bind-mounts ./backend over /app for live reload, and a Windows host's NTFS
# permissions don't reliably carry an exec bit into the container.
ENTRYPOINT ["sh", "docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
