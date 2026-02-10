FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY services/api /workspace/services/api

RUN pip install -e /workspace/services/api

WORKDIR /workspace/services/api

EXPOSE 8000

RUN chmod +x /workspace/services/api/entrypoint.sh

CMD ["/workspace/services/api/entrypoint.sh"]
