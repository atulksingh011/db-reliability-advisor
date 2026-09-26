FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY alembic.ini ./
COPY services ./services
COPY contracts ./contracts
COPY migrations ./migrations
COPY scripts ./scripts
RUN pip install --no-cache-dir .

CMD ["uvicorn", "services.analysis_service.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
