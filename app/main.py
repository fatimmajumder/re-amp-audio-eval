from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .repository import RunRepository, WorkspaceRepository
from .schemas import (
    BenchmarkRun,
    CatalogResponse,
    CompareRequest,
    CompareResponse,
    OverviewResponse,
    PublicDataset,
    RunCreate,
    WorkspaceCreate,
    WorkspaceRecord,
)
from .service import RunService

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = BASE_DIR / "data"
DEFAULT_STORAGE = DATA_DIR / "runs.json"
DEFAULT_WORKSPACE_STORAGE = DATA_DIR / "workspaces.json"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
PUBLIC_DATASETS_DIR = DATA_DIR / "public_datasets"


def get_service(request: Request) -> RunService:
    return request.app.state.run_service


def create_app(storage_path: Path | None = None, *, seed_demo_data: bool = True) -> FastAPI:
    run_storage_path = storage_path or DEFAULT_STORAGE
    workspace_storage_path = run_storage_path.parent / "workspaces.json" if storage_path else DEFAULT_WORKSPACE_STORAGE
    artifacts_root = (run_storage_path.parent / "artifacts") if storage_path else ARTIFACTS_DIR
    datasets_root = (run_storage_path.parent / "public_datasets") if storage_path else PUBLIC_DATASETS_DIR

    repository = RunRepository(run_storage_path)
    workspace_repository = WorkspaceRepository(workspace_storage_path)
    run_service = RunService(repository, workspace_repository, artifacts_root, datasets_root)
    run_service.ensure_seed_workspaces()
    if seed_demo_data:
        run_service.ensure_seed_data()

    app = FastAPI(
        title="RE-AMP",
        version="2.0.0",
        description="Full-stack generative audio robustness evaluation dashboard.",
    )
    app.state.run_service = run_service
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/catalog", response_model=CatalogResponse)
    def get_catalog(service: RunService = Depends(get_service)) -> CatalogResponse:
        return service.get_catalog()

    @app.get("/api/public-datasets", response_model=list[PublicDataset])
    def list_public_datasets(service: RunService = Depends(get_service)) -> list[PublicDataset]:
        return service.list_public_datasets()

    @app.get("/api/workspaces", response_model=list[WorkspaceRecord])
    def list_workspaces(service: RunService = Depends(get_service)) -> list[WorkspaceRecord]:
        return service.list_workspaces()

    @app.post("/api/workspaces", response_model=WorkspaceRecord)
    def create_workspace(
        payload: WorkspaceCreate,
        service: RunService = Depends(get_service),
    ) -> WorkspaceRecord:
        return service.create_workspace(payload)

    @app.get("/api/overview", response_model=OverviewResponse)
    def get_overview(service: RunService = Depends(get_service)) -> OverviewResponse:
        return service.get_overview()

    @app.get("/api/runs", response_model=list[BenchmarkRun])
    def list_runs(service: RunService = Depends(get_service)) -> list[BenchmarkRun]:
        return service.list_runs()

    @app.post("/api/runs", response_model=BenchmarkRun)
    def create_run(
        payload: RunCreate,
        background_tasks: BackgroundTasks,
        service: RunService = Depends(get_service),
    ) -> BenchmarkRun:
        try:
            run = service.create_run(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(service.execute_run, run.run_id)
        return run

    @app.get("/api/runs/{run_id}", response_model=BenchmarkRun)
    def get_run(run_id: str, service: RunService = Depends(get_service)) -> BenchmarkRun:
        run = service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.post("/api/runs/{run_id}/replay", response_model=BenchmarkRun)
    def replay_run(
        run_id: str,
        background_tasks: BackgroundTasks,
        service: RunService = Depends(get_service),
    ) -> BenchmarkRun:
        try:
            replay = service.replay_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        background_tasks.add_task(service.execute_run, replay.run_id)
        return replay

    @app.post("/api/compare", response_model=CompareResponse)
    def compare_runs(
        payload: CompareRequest,
        service: RunService = Depends(get_service),
    ) -> CompareResponse:
        try:
            return service.compare_runs(payload.left_run_id, payload.right_run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="one or both runs were not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="runs must be completed before comparison") from exc

    @app.get("/api/runs/{run_id}/artifacts/{filename}")
    def download_artifact(
        run_id: str,
        filename: str,
        service: RunService = Depends(get_service),
    ) -> FileResponse:
        try:
            path = service.get_artifact_path(run_id, filename)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        return FileResponse(path)

    return app


app = create_app()
