FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# GJU credential verifier drives a real Chromium browser (MyGJU's WAF blocks
# plain headless requests) — install the browser binary and its OS deps.
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
