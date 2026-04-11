# RE-AMP: Generative Audio Robustness Evaluation

Public showcase implementation of a full-stack benchmarking system for generative audio models.

This repository is inspired by the kind of experimentation platforms described in my resume, but it is intentionally rebuilt as an original, public-facing demo rather than a copy of any private company code.

## What it demonstrates

- asynchronous benchmark job submission
- structured run metadata and artifact tracking
- reproducible replay of evaluation runs
- side-by-side model comparison workflows
- API-first design for a future React frontend

## Stack

- Python
- FastAPI
- Pydantic
- Redis-style queue abstraction
- PostgreSQL-style run metadata model
- Docker-ready local development

## Why this repo exists

I care about evaluation systems that preserve trust while teams move fast. This repo is the open-source portfolio version of that idea: a small but credible benchmark platform that shows how I think about reproducibility, orchestration, and model comparison.

## Planned repository structure

- `app/main.py` for the API entrypoint
- `app/evaluation.py` for orchestration logic
- `app/schemas.py` for run metadata contracts
- `requirements.txt` for local setup

## Resume-aligned highlights

- benchmarked thousands of controlled runs in the original project context
- focused on replayability, comparative analysis, and robust experiment bookkeeping
- built to make evaluation legible instead of opaque
