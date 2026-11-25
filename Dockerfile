# File: Dockerfile
# Description: Container image for the Roko's Tasks web service.
# Author(s): Tyler Black, Richard Hall

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
# Submit waits on the runner for up to ~30 s, so one request must not
# block the site: threaded workers, and a timeout above RunnerClient's.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", \
    "--threads", "8", "--timeout", "60", "src.app:create_app()"]
