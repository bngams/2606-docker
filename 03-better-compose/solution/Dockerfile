# syntax=docker/dockerfile:1
FROM python:3.12-alpine

WORKDIR /code
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

RUN apk add --no-cache gcc musl-dev linux-headers

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Bonne pratique : ne PAS tourner en root. On crée un utilisateur dédié et on bascule dessus.
# (USER dans le Dockerfile = plus propre qu'un user: dans compose, et survit aux overrides.)
RUN adduser -D -u 10001 appuser && chown -R appuser:appuser /code
USER appuser

EXPOSE 5000
CMD ["flask", "run"]
