FROM ghcr.io/astral-sh/uv:alpine

RUN apk add --no-cache bash

ADD . /app
WORKDIR /app

RUN chmod +x scripts/*.sh && uv sync --locked

EXPOSE 8000

ENTRYPOINT ["bash", "/app/scripts/docker-entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
