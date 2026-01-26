"""LLM worker service entry point.

This module provides the ARQ worker configuration for running
background LLM jobs such as embeddings, summarization, and analysis.
"""

from arq import run_worker

from app.worker import WorkerSettings


if __name__ == "__main__":
    run_worker(WorkerSettings)
