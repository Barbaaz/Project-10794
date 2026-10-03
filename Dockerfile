# The web app (and, on request, the scrapers). psycopg's wheel brings PostgreSQL's client library.
# Used by docker-compose.yml; see "Try it with Docker" in README.md.
FROM python:3.12-slim-bookworm

# Log lines appear at once and in order
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 5000
CMD ["sh", "docker/start.sh"]
