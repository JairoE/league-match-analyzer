FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY packages/shared /workspace/packages/shared
COPY services/api /workspace/services/api

RUN pip install -e /workspace/packages/shared
RUN pip install -e /workspace/services/api

WORKDIR /workspace/services/api

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
