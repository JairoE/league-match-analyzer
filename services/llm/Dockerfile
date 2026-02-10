FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY services/llm /workspace/services/llm

RUN pip install -e /workspace/services/llm

WORKDIR /workspace/services/llm

CMD ["python", "main.py"]
