# Shared Package Import Strategy

## Local development
- Install the shared package in editable mode from each service:
  - `cd services/api && pip install -e ../../packages/shared`
  - `cd services/llm && pip install -e ../../packages/shared`
- This keeps imports live while you iterate on `packages/shared`.

## Path dependency
- Each service `pyproject.toml` includes:
  - `league-shared @ file:../../packages/shared`
- This makes the local path the default dependency source during installs.
