FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# gettext: translations · pango/harfbuzz: PDF engine · Noto fonts: Tamil and other scripts in PDFs
RUN apt-get update && apt-get install -y --no-install-recommends \
        gettext libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN DEBUG=False SECRET_KEY=build python manage.py collectstatic --noinput \
 && python manage.py compilemessages --ignore=.venv

EXPOSE 8000
CMD ["sh", "docker/entrypoint.sh"]
