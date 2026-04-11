# RE-AMP: Generative Audio Robustness Evaluation

RE-AMP is a full-stack benchmark dashboard for evaluating generative audio
systems under acoustic stress, export degradation, timing shifts, and artifact
pressure. The repo is intentionally public-facing: it shows how an evaluation
platform can be structured end to end without copying private employer code.

This version goes beyond a thin demo. It includes a FastAPI backend, a polished
single-page dashboard, persistent run and workspace storage, replayable
benchmark jobs, scenario-level comparison, generated waveform and spectrogram
artifacts, and a public dataset registry with downloader tooling.

## What the project demonstrates

- benchmark orchestration with queued, running, completed, replayed, and failed
  job states
- deterministic evaluation logic so the same model, scenario mix, dataset, and
  seed produce stable outputs
- persistent JSON-backed run history plus saved workspace lanes for different
  evaluation goals
- benchmark templates, model cards, reusable scenario library, and curated
  public dataset metadata
- generated run artifacts including a JSON report, waveform SVG, spectrogram
  SVG, WAV preview, worker log, and manifest
- side-by-side comparison across runs with scenario deltas and verdicts
- recruiter-friendly frontend that makes the evaluation story easy to inspect

## Product tour

### Dashboard

The frontend at `/` includes:

- a launch form for benchmark composition with workspace and public dataset
  selection
- live metrics for average score, latency, best model, and active queue depth
- a public dataset registry with official source links and local-download status
- saved workspaces with persistent run counts
- a run registry with progress and replay controls
- a detail panel with scenario results, slice scores, inline media previews, and
  downloadable artifacts
- a comparison panel for completed runs
- leaderboard and recent activity sections

### API

Key routes:

- `GET /api/catalog` returns benchmark templates, models, scenarios, and public
  datasets
- `GET /api/public-datasets` returns the dataset registry with local manifest
  status
- `GET /api/workspaces` lists saved workspaces
- `POST /api/workspaces` creates a new workspace
- `GET /api/overview` returns leaderboard and summary metrics
- `GET /api/runs` returns all runs in reverse chronological order
- `POST /api/runs` queues a run and executes it in a background task
- `GET /api/runs/{run_id}` returns full run detail
- `POST /api/runs/{run_id}/replay` re-runs the exact same scenario mix
- `POST /api/compare` compares two completed runs
- `GET /api/runs/{run_id}/artifacts/{filename}` downloads generated artifacts

## Architecture

```mermaid
flowchart LR
    A["Dashboard UI"] --> B["FastAPI routes"]
    B --> C["RunService"]
    C --> D["Deterministic evaluator"]
    C --> E["Run repository"]
    C --> F["Workspace repository"]
    C --> G["Public dataset registry"]
    C --> H["Artifact writer"]
    E --> I["data/runs.json"]
    F --> J["data/workspaces.json"]
    G --> K["data/public_datasets/<dataset_id>/manifest.json"]
    H --> L["data/artifacts/<run_id>/..."]
```

## Repository layout

- `app/main.py` wires the FastAPI app, routes, and static assets
- `app/service.py` coordinates run creation, replay, comparison, overview, and
  workspace persistence
- `app/evaluation.py` scores scenarios and builds run summaries
- `app/artifacts.py` materializes report, SVG, WAV, log, and manifest files
- `app/public_datasets.py` defines the public dataset registry and local
  manifest hydration
- `app/demo_data.py` seeds benchmark templates, scenarios, model cards, and
  default workspaces
- `app/static/` contains the frontend dashboard
- `scripts/download_public_dataset.py` downloads direct-access public datasets
  for smoke tests
- `tests/test_api.py` covers the core API workflow
- `examples/` contains sample payloads for runs and workspaces

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

- dashboard: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`

By default the app seeds a few demo runs so the dashboard has data on first
load. Runtime outputs are written to:

- `data/runs.json`
- `data/workspaces.json`
- `data/artifacts/<run_id>/`
- `data/public_datasets/<dataset_id>/manifest.json`

## Pull a public dataset for testing

RE-AMP now ships with official public audio dataset metadata plus a downloader
for direct-access sources. For a quick smoke test, pull a small slice of Mini
Speech Commands:

```bash
source .venv/bin/activate
python scripts/download_public_dataset.py --dataset mini_speech_commands --max-files 12
```

That writes extracted audio plus a manifest under
`data/public_datasets/mini_speech_commands/`. On the next app load the dataset
card switches from remote to downloaded and shows local sample counts.

## Run tests

```bash
python -m pytest -q
```

## Docker

```bash
docker build -t re-amp .
docker run --rm -p 8000:8000 re-amp
```

## Example run request

```json
{
  "benchmark_name": "audio_robustness_suite",
  "model_name": "reamp-studio-beta",
  "workspace_id": "core-audio-lab",
  "public_dataset_id": "mini_speech_commands",
  "dataset_name": "Mini Speech Commands",
  "seed": 17,
  "notes": "Candidate model under dialogue overlap and pitch drift stress.",
  "scenarios": [
    {
      "name": "speaker_overlap",
      "difficulty": "hard"
    },
    {
      "name": "pitch_drift",
      "difficulty": "medium"
    }
  ]
}
```

## Why this is portfolio-grade

This project is framed the way strong ML infrastructure work is framed in real
teams: not just model quality, but observability, repeatability, dataset ops,
and decision support. It connects backend orchestration, evaluation design,
public-data ingestion, reporting, and frontend presentation in one coherent
story.
