from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent.runner import AgentRunner
from app.agent.tools import AgentTools
from app.config import get_settings
from app.database import Database
from app.services.catalogue import CatalogueService
from app.services.demo_payload import SafeDemoPayload
from app.services.events import EventLogger
from app.storage.azure import AzureProductFeed
from app.storage.local import LocalProductFeed

settings = get_settings()
INITIAL_SECURITY_MODE = settings.agent_security_mode
INITIAL_STORAGE_MODE = settings.demo_storage_mode
database = Database(settings.database_path)
events = EventLogger(database)
payload = SafeDemoPayload(settings.demo_blob_path / "scripts")
stop_event = Event()
run_lock = Lock()
state_guard = Lock()
run_state: dict[str, Any] = {
    "running": False,
    "reset_pending": False,
    "reset_version": 0,
    "last_reset_at": None,
    "last_result": None,
    "last_error": None,
}

POISONED_SOURCE_NAME = "products/product-016-poisoned.md"

def make_feed():
    if settings.demo_storage_mode == "azure":
        if not all((settings.azure_storage_account_url, settings.azure_storage_container, settings.azure_storage_sas_token)):
            raise RuntimeError("Azure mode requires AZURE_STORAGE_ACCOUNT_URL, AZURE_STORAGE_CONTAINER, and AZURE_STORAGE_SAS_TOKEN.")
        return AzureProductFeed(settings.azure_storage_account_url, settings.azure_storage_container, settings.azure_storage_sas_token)
    return LocalProductFeed(settings.demo_blob_path)


def make_service() -> CatalogueService:
    feed = make_feed()
    runner = AgentRunner(settings, AgentTools(feed, payload), events, stop_event.is_set)
    return CatalogueService(database, feed, runner, events)

app = FastAPI(title="Poisoned at the Source")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def page_context(request: Request) -> dict[str, Any]:
    return {"request": request, "settings": settings, "products": database.products()}


@app.get("/", response_class=HTMLResponse)
def catalogue(request: Request):
    return templates.TemplateResponse(request, "catalogue.html", page_context(request))


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: str):
    product = database.product(product_id)
    if not product:
        return templates.TemplateResponse(request, "product.html", {"request": request, "product": None}, status_code=404)
    return templates.TemplateResponse(request, "product.html", {"request": request, "product": product})


@app.get("/monitor", response_class=HTMLResponse)
def monitor(request: Request):
    return templates.TemplateResponse(request, "monitor.html", page_context(request))


@app.get("/demo", response_class=HTMLResponse)
@app.get("/controls", response_class=HTMLResponse)
def demo(request: Request):
    return templates.TemplateResponse(request, "demo.html", page_context(request))


@app.get("/demo/ransomware", response_class=HTMLResponse)
@app.get("/recovery", response_class=HTMLResponse)
def ransomware(request: Request):
    return templates.TemplateResponse(request, "fake_ransomware.html", page_context(request))


@app.get("/demo-assets/validation-check.sh", include_in_schema=False)
def demo_shell_script():
    return FileResponse(
        settings.demo_blob_path / "scripts" / "validation-check.sh",
        media_type="text/x-shellscript",
        filename="validation-check.sh",
    )


@app.get("/api/products")
def api_products():
    return database.products()


@app.get("/api/events")
def api_events(after_id: int = 0):
    return database.events(after_id)


@app.post("/api/events/clear")
def api_events_clear():
    database.clear_events()
    return {"ok": True, "message": "Event history cleared."}


@app.get("/api/status")
def api_status():
    try:
        source_total = len(make_feed().list_objects())
    except Exception:
        source_total = None
    with state_guard:
        state_snapshot = dict(run_state)
    return {
        "model": settings.openai_model,
        "storage": settings.demo_storage_mode,
        "security_mode": settings.agent_security_mode,
        "products_processed": len(database.products()),
        "source_total": source_total,
        "payload_active": payload.state.active,
        "payload_logs": payload.state.logs,
        "has_openai_key": settings.has_openai_key,
        **state_snapshot,
    }


def _perform_reset() -> None:
    """Restore the safe, repeatable state used at application startup."""
    database.clear()
    payload.reset()
    settings.agent_security_mode = INITIAL_SECURITY_MODE  # type: ignore[misc]
    settings.demo_storage_mode = INITIAL_STORAGE_MODE  # type: ignore[misc]
    stop_event.clear()
    with state_guard:
        run_state.update({
            "reset_pending": False,
            "reset_version": run_state["reset_version"] + 1,
            "last_reset_at": datetime.now(timezone.utc).isoformat(),
            "last_result": None,
            "last_error": None,
        })


@app.post("/api/reset")
def api_reset():
    with state_guard:
        if run_state["running"]:
            stop_event.set()
            run_state["reset_pending"] = True
            return JSONResponse(
                {"ok": True, "pending": True, "message": "Reset queued; waiting for the current model request to finish."},
                status_code=202,
            )
    _perform_reset()
    return {"ok": True, "pending": False, "message": "System restored to its initial state."}


@app.post("/api/process")
def api_process(source_name: str | None = Form(default=None), limit: int | None = Form(default=None), include_poisoned: bool = Form(default=True)):
    try:
        result = make_service().process(limit=limit, source_name=source_name, include_poisoned=include_poisoned)
        return {"ok": True, **result}
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.post("/api/mode")
def api_mode(mode: str = Form(...)):
    if mode not in {"vulnerable", "protected"}:
        return JSONResponse({"ok": False, "error": "Invalid security mode."}, status_code=400)
    settings.agent_security_mode = mode  # type: ignore[misc]
    return {"ok": True, "security_mode": mode}


@app.post("/api/storage")
def api_storage(mode: str = Form(...)):
    if mode not in {"local", "azure"}:
        return JSONResponse({"ok": False, "error": "Invalid storage mode."}, status_code=400)
    if run_state["running"]:
        return JSONResponse({"ok": False, "error": "Storage cannot change while the agent is running."}, status_code=409)
    settings.demo_storage_mode = mode  # type: ignore[misc]
    try:
        make_feed().list_objects()
    except Exception as exc:
        settings.demo_storage_mode = "local"  # type: ignore[misc]
        return JSONResponse({"ok": False, "error": str(exc), "storage": "local"}, status_code=400)
    return {"ok": True, "storage": mode}


def _run_agent(scope: str, limit: int | None) -> None:
    try:
        source_name = POISONED_SOURCE_NAME if scope == "poisoned" else None
        include_poisoned = scope != "normal"
        result = make_service().process(
            limit=limit,
            source_name=source_name,
            include_poisoned=include_poisoned,
            retry_sources={POISONED_SOURCE_NAME} if scope == "all" else None,
            stop_requested=stop_event.is_set,
        )
        with state_guard:
            run_state["last_result"] = result
    except Exception as exc:
        with state_guard:
            run_state["last_error"] = f"{type(exc).__name__}: {exc}"
        events.log("SECURITY_EVENT", f"Agent run failed: {type(exc).__name__}: {exc}", "warning")
    finally:
        with state_guard:
            reset_pending = run_state["reset_pending"]
        if reset_pending:
            _perform_reset()
        with state_guard:
            run_state["running"] = False
        run_lock.release()


@app.post("/api/run")
def api_run(scope: str = Form(default="normal"), limit: int | None = Form(default=None)):
    if scope not in {"normal", "poisoned", "all"}:
        return JSONResponse({"ok": False, "error": "Invalid run scope."}, status_code=400)
    if not run_lock.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "The agent is already running."}, status_code=409)
    stop_event.clear()
    with state_guard:
        run_state.update({"running": True, "reset_pending": False, "last_result": None, "last_error": None})
    Thread(target=_run_agent, args=(scope, limit), daemon=True, name="catalogue-agent").start()
    return {"ok": True, "scope": scope}


@app.post("/api/stop")
def api_stop():
    stop_event.set()
    return {"ok": True, "message": "Stop requested; the current model request will finish safely."}


@app.get("/api/stream")
async def api_stream():
    async def events_stream():
        last_id = 0
        while True:
            # SQLite reads are blocking; keep them off the event loop so open
            # monitor tabs cannot starve the server that also hosts the demo
            # asset the agent downloads.
            updates = await asyncio.to_thread(database.events, last_id)
            for event in updates:
                last_id = event["id"]
                yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0.7)
    return StreamingResponse(events_stream(), media_type="text/event-stream")
