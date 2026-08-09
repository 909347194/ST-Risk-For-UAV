# ST-Risk-For-UAV

This repository is organized as a simple monorepo for TypeScript and Python.

## Structure

- apps/web: frontend application
- apps/server/python-fastapi-backend: Python service
- packages/shared-ts: shared TypeScript code
- packages/shared-py: shared Python code
- docs: project documentation
- scripts: automation scripts

## Shared package layout

- packages/shared-ts/src/types: shared TypeScript types
- packages/shared-ts/src/api: shared API helpers
- packages/shared-ts/src/utils: shared TypeScript utilities
- packages/shared-py/src/shared_py/models: shared Python models
- packages/shared-py/src/shared_py/services: shared Python services
- packages/shared-py/src/shared_py/utils: shared Python utilities

## Quick start

- Python: `python apps/server/python-fastapi-backend/src/main.py`
- TypeScript placeholder: `npm --prefix apps/web run dev`
