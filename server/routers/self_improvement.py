"""Self-improvement HTTP endpoints.

Exposes the autonomous improvement engine over REST — discovery, test runs,
improvement cycles, and report retrieval.  Operates standalone or as part
of the full Jarvis system.  Rather like giving oneself a performance review,
except this one actually accomplishes something.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from jarvis.services.self_improvement_service import (
    NightCycleState,
    SelfImprovementService,
)
from ..models import CycleRequest, DiscoveryRequest, TaskSubmitRequest, TestRunRequest

router = APIRouter()

# Module-level state — shared across requests within this process.
_state: Dict = {
    "running": False,
    "discoveries": [],
    "test_runs": {},
    "submitted_tasks": [],
    "last_report": None,
    "cycle_error": None,
}


# ------------------------------------------------------------------
# Service resolution
# ------------------------------------------------------------------


def _get_service(request: Request) -> SelfImprovementService:
    """Lazy-initialize from app state or standalone."""
    jarvis_system = getattr(request.app.state, "jarvis_system", None)
    if jarvis_system:
        agent = jarvis_system.network.agents.get("SelfImprovementAgent")
        if agent and hasattr(agent, "_service"):
            return agent._service
    # Fallback: standalone service
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return SelfImprovementService(project_root=project_root)


# ------------------------------------------------------------------
# Background task helpers
# ------------------------------------------------------------------


async def _run_test_background(
    run_id: str,
    service: SelfImprovementService,
    test_files: Optional[List[str]],
    working_directory: Optional[str],
) -> None:
    """Execute pytest in the background and stash results in _state."""
    _state["test_runs"][run_id]["status"] = "running"
    try:
        result = await service._runner.run_tests(
            worktree_path=working_directory or service._project_root,
            test_files=test_files,
        )
        _state["test_runs"][run_id].update(
            {
                "status": "completed" if result.success else "failed",
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_seconds": result.duration_seconds,
            }
        )
    except Exception as exc:
        _state["test_runs"][run_id].update(
            {
                "status": "failed",
                "success": False,
                "error": str(exc),
            }
        )


async def _run_cycle_background(
    service: SelfImprovementService,
    max_tasks: Optional[int],
) -> None:
    """Execute a full improvement cycle in the background."""
    _state["running"] = True
    try:
        if max_tasks:
            service.MAX_TASKS_PER_NIGHT = max_tasks
        report = await service.run_improvement_cycle()
        _state["last_report"] = report.to_dict()
    except Exception as exc:
        _state["cycle_error"] = str(exc)
    finally:
        _state["running"] = False


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/status")
async def get_status():
    """Current state of the self-improvement engine."""
    return {
        "running": _state["running"],
        "discoveries_count": len(_state["discoveries"]),
        "submitted_tasks_count": len(_state["submitted_tasks"]),
        "test_runs_count": len(_state["test_runs"]),
        "last_report": _state.get("last_report"),
        "cycle_error": _state.get("cycle_error"),
    }


@router.post("/discover")
async def run_discovery(body: DiscoveryRequest, request: Request):
    """Run discovery analysis and cache the results."""
    service = _get_service(request)
    analyzer = service._analyzer

    discoveries = await analyzer.run_full_analysis()

    # Serialize discoveries to dicts
    serialized = []
    for d in discoveries:
        entry = {
            "discovery_type": d.discovery_type.value,
            "title": d.title,
            "description": d.description,
            "priority": d.priority,
            "relevant_files": d.relevant_files,
            "source_detail": d.source_detail,
            "todo_id": d.todo_id,
        }
        serialized.append(entry)

    # Filter by requested types if provided
    if body.types:
        serialized = [
            d for d in serialized if d["discovery_type"] in body.types
        ]

    _state["discoveries"] = serialized
    return {"count": len(serialized), "discoveries": serialized}


@router.get("/discoveries")
async def get_discoveries(type: Optional[str] = Query(None)):
    """Return cached discoveries, optionally filtered by type."""
    discoveries = _state["discoveries"]
    if type:
        discoveries = [d for d in discoveries if d["discovery_type"] == type]
    return {"count": len(discoveries), "discoveries": discoveries}


@router.post("/cycle")
async def start_cycle(body: CycleRequest, request: Request):
    """Start a full improvement cycle as a background task."""
    if _state["running"]:
        raise HTTPException(
            status_code=409,
            detail="An improvement cycle is already running",
        )

    service = _get_service(request)
    _state["cycle_error"] = None
    asyncio.create_task(
        _run_cycle_background(service, body.max_tasks)
    )
    return {"status": "started", "message": "Improvement cycle launched"}


@router.post("/tasks")
async def submit_task(body: TaskSubmitRequest):
    """Submit an external improvement task."""
    task = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "description": body.description,
        "priority": body.priority,
        "relevant_files": body.relevant_files,
        "status": "pending",
    }
    _state["submitted_tasks"].append(task)
    return task


@router.get("/tasks")
async def list_tasks():
    """List all submitted improvement tasks."""
    return {"count": len(_state["submitted_tasks"]), "tasks": _state["submitted_tasks"]}


@router.post("/tests/run")
async def start_test_run(body: TestRunRequest, request: Request):
    """Launch a pytest run asynchronously and return a tracking ID."""
    service = _get_service(request)
    run_id = str(uuid.uuid4())
    _state["test_runs"][run_id] = {"status": "pending", "run_id": run_id}
    asyncio.create_task(
        _run_test_background(
            run_id, service, body.test_files, body.working_directory
        )
    )
    return {"run_id": run_id, "status": "pending"}


@router.get("/tests/{run_id}")
async def get_test_run(run_id: str):
    """Poll test run results by run_id."""
    run = _state["test_runs"].get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@router.get("/reports/latest")
async def get_latest_report(request: Request):
    """Retrieve the most recent NightReport."""
    service = _get_service(request)
    report = service.get_latest_report()
    if not report:
        return {"report": None, "message": "No reports on file"}
    return {"report": report.to_dict()}


@router.get("/reports")
async def list_reports(request: Request, limit: int = Query(20)):
    """List available report files."""
    service = _get_service(request)
    report_dir = service.REPORT_DIR
    if not report_dir.exists():
        return {"count": 0, "reports": []}

    files = sorted(report_dir.glob("*.json"), reverse=True)
    limited = files[:limit]
    return {
        "count": len(limited),
        "reports": [{"filename": f.name, "path": str(f)} for f in limited],
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the Night Mode dashboard — because staring at logs is so 2003."""
    dashboard_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "night_dashboard.html"
    )
    if os.path.exists(dashboard_path):
        return FileResponse(
            dashboard_path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    raise HTTPException(
        status_code=404,
        detail="Dashboard HTML not found. Someone misplaced the blueprints.",
    )


@router.get("/live")
async def get_live_state(request: Request):
    """Single endpoint returning everything the dashboard needs.

    Aggregates night mode status, cycle state, latest report, backlog,
    and cached discoveries into one tidy payload.  Polled every 3 seconds
    by the dashboard — efficient enough not to be embarrassing.
    """
    jarvis_system = getattr(request.app.state, "jarvis_system", None)
    night_mode = getattr(jarvis_system, "night_mode", False) if jarvis_system else False

    # Cycle state from persistent file
    cycle_state = None
    raw_state = NightCycleState.load()
    if raw_state:
        cycle_state = {
            "cycle_id": raw_state.cycle_id,
            "started_at": raw_state.started_at,
            "status": raw_state.status,
            "current_task_index": raw_state.current_task_index,
            "total_tasks": len(raw_state.discoveries),
            "completed_results": raw_state.completed_results,
            "discoveries": raw_state.discoveries,
            "skipped_count": raw_state.skipped_count,
        }

    # Latest report
    latest_report = _state.get("last_report")
    if not latest_report:
        service = _get_service(request)
        report = service.get_latest_report()
        if report:
            latest_report = report.to_dict()

    # Backlog items from TodoService
    backlog = []
    if jarvis_system:
        todo_svc = getattr(jarvis_system, "_agent_refs", {}).get("todo_service")
        if todo_svc:
            try:
                items = todo_svc.list(tag="night-agent-backlog")
                backlog = [
                    item.to_dict() for item in items
                    if item.status.value != "done"
                ]
            except Exception:
                pass

    return {
        "night_mode": night_mode,
        "running": _state["running"],
        "cycle_state": cycle_state,
        "latest_report": latest_report,
        "backlog": backlog,
        "discoveries": _state["discoveries"],
        "cycle_error": _state.get("cycle_error"),
    }


@router.get("/context/{file_path:path}")
async def get_context(file_path: str):
    """Read a project file. Path traversal is, naturally, forbidden."""
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    full_path = os.path.normpath(os.path.join(project_root, file_path))
    if not full_path.startswith(os.path.normpath(project_root)):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(full_path, "r") as f:
            content = f.read()
        return {"file_path": file_path, "content": content, "size": len(content)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
