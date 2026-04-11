from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .repository import build_repositories
from .schemas import (
    BenchmarkRun,
    CatalogResponse,
    CompareRequest,
    CompareResponse,
    OverviewResponse,
    PublicDataset,
    RunCreate,
    SystemStatusResponse,
    WorkspaceCreate,
    WorkspaceRecord,
)
from .service import RunService
from .settings import Settings
from .worker import RunWorkerPool

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_service(request: Request) -> RunService:
    return request.app.state.run_service


def create_app(
    storage_path: Path | None = None,
    *,
    seed_demo_data: bool = True,
    database_url: str | None = None,
    inline_worker_enabled: bool | None = None,
) -> FastAPI:
    settings = Settings.from_env(
        BASE_DIR,
        storage_path=storage_path,
        database_url=database_url,
        inline_worker_enabled=inline_worker_enabled,
    )
    repository, workspace_repository = build_repositories(settings)
    run_service = RunService(
        repository,
        workspace_repository,
        settings.artifacts_dir,
        settings.public_datasets_dir,
        settings,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        run_service.ensure_seed_workspaces()
        if seed_demo_data:
            run_service.ensure_seed_data()
        run_service.recover_incomplete_runs()

        worker_pool = None
        if settings.inline_worker_enabled:
            worker_pool = RunWorkerPool(
                run_service,
                worker_count=settings.worker_count,
                poll_interval_seconds=settings.worker_poll_interval_seconds,
            )
            worker_pool.start()

        app.state.worker_pool = worker_pool
        yield

        if worker_pool:
            worker_pool.stop()

    app = FastAPI(
        title="RE-AMP",
        version="3.0.0",
        description="Production-shaped generative audio robustness evaluation dashboard.",
        lifespan=lifespan,
    )
    app.state.run_service = run_service
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health(service: RunService = Depends(get_service)) -> dict[str, object]:
        status = service.get_system_status()
        return {
            "status": "ok",
            "storage_backend": status.storage_backend,
            "inline_worker_enabled": status.inline_worker_enabled,
        }

    @app.get("/api/system", response_model=SystemStatusResponse)
    def get_system_status(service: RunService = Depends(get_service)) -> SystemStatusResponse:
        return service.get_system_status()

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
        service: RunService = Depends(get_service),
    ) -> BenchmarkRun:
        try:
            return service.create_run(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}", response_model=BenchmarkRun)
    def get_run(run_id: str, service: RunService = Depends(get_service)) -> BenchmarkRun:
        run = service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.post("/api/runs/{run_id}/replay", response_model=BenchmarkRun)
    def replay_run(
        run_id: str,
        service: RunService = Depends(get_service),
    ) -> BenchmarkRun:
        try:
            return service.replay_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
