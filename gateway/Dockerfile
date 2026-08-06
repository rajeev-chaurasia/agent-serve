FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml .

RUN uv sync --frozen

COPY src/ src/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "agent_serve.gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
