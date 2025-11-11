FROM ghcr.io/astral-sh/uv:alpine

ADD . /app
WORKDIR /app

RUN uv sync --locked

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
