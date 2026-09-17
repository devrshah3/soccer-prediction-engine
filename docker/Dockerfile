FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --upgrade pip && pip install .
COPY configs ./configs
RUN mkdir -p data/raw data/processed data/features models reports

EXPOSE 8000
CMD ["uvicorn", "soccer_engine.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

