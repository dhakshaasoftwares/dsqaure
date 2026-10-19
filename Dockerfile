FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends gettext && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN DEBUG=False SECRET_KEY=build python manage.py collectstatic --noinput \
 && python manage.py compilemessages --ignore=.venv

EXPOSE 8000
CMD ["sh", "docker/entrypoint.sh"]
