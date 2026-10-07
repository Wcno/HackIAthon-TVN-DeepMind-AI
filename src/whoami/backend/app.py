"""FastAPI views for the eight G2 screens. G6 can replace the small templates."""

from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

from whoami.backend.gemini import GeminiClient, GenerationUnavailable
from whoami.backend.pipeline import load_pipeline, validate_answer
from whoami.backend.repository import EditorialRepository, InvalidReview, MissingRecord, ReviewConflict
from whoami.backend.service import EditorialService, quality_report
from whoami.backend.settings import Settings
from whoami.contracts import PROCESSED, REVIEW_STATES, TOPIC_LABELS


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["nuevo", "en_revision", "requiere_evidencia", "aprobado_como_borrador", "descartado"]
    actor: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("actor")
    @classmethod
    def human_actor(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A human reviewer is required.")
        return value.strip()


def panama_time(value: str | None) -> str:
    if value is None:
        return "Fecha desconocida"
    return datetime.fromisoformat(value).astimezone(ZoneInfo("America/Panama")).strftime("%d/%m/%Y %H:%M")


def safe_url(value: str) -> str:
    return value if urlsplit(value).scheme in ("https", "http") else "#"


# G4 supplies generation/retrieval; G5 owns the cached client and transport.
QueryProvider = Callable[[str, GeminiClient, EditorialRepository], Awaitable[dict]]


def create_app(settings: Settings | None = None, *, query_provider: QueryProvider | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    templates.env.filters.update(panama_time=panama_time, safe_url=safe_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository = EditorialRepository(settings.database)
        repository.import_bundle(load_pipeline(settings.data_directory, settings.output_directory))
        app.state.repository = repository
        app.state.editorial = EditorialService(repository)
        app.state.gemini = GeminiClient(repository, settings)
        try:
            yield
        finally:
            await app.state.gemini.close()

    app = FastAPI(title="TVN DataMind AI", lifespan=lifespan)

    def render(request: Request, screen: str, title: str, **context):
        return templates.TemplateResponse(request=request, name="screen.html", context={
            "screen": screen, "title": title, "demo": settings.demo,
            "fragment": request.headers.get("HX-Request") == "true", "topics": TOPIC_LABELS,
            "review_states": REVIEW_STATES, **context,
        })

    @app.exception_handler(MissingRecord)
    async def missing_record(request: Request, error: MissingRecord):
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(ReviewConflict)
    async def review_conflict(request: Request, error: ReviewConflict):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(InvalidReview)
    async def invalid_review(request: Request, error: InvalidReview):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(GenerationUnavailable)
    async def unavailable(request: Request, error: GenerationUnavailable):
        return JSONResponse({"detail": str(error)}, status_code=503)

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/inbox")

    @app.get("/health")
    def health(request: Request):
        return {"status": "ready", "demo": settings.demo, "offline": settings.offline,
                "groups": len(request.app.state.repository.records("group"))}

    @app.get("/quality", response_class=HTMLResponse)
    def quality(request: Request):
        return render(request, "quality", "Calidad de los datos", reports=quality_report(PROCESSED if settings.demo else settings.data_directory))

    @app.get("/inbox", response_class=HTMLResponse)
    def inbox(request: Request, topic: str | None = None):
        return render(request, "inbox", "Agenda priorizada", groups=request.app.state.editorial.inbox(topic=topic))

    @app.get("/groups/{group_id}", response_class=HTMLResponse)
    def group(request: Request, group_id: str):
        item = request.app.state.editorial.group(group_id)
        return render(request, "group", item["titulo"], group=item)

    @app.get("/groups/{group_id}/context", response_class=HTMLResponse)
    def context(request: Request, group_id: str):
        return render(request, "context", "Contexto oficial", group=request.app.state.editorial.group(group_id))

    @app.get("/evidence/{evidence_id}", response_class=HTMLResponse)
    def evidence(request: Request, evidence_id: str):
        item = request.app.state.repository.record("evidence", evidence_id)
        return render(request, "evidence", item["titulo"], evidence=item)

    @app.get("/cases/{case_id}", response_class=HTMLResponse)
    def case(request: Request, case_id: str):
        item = request.app.state.editorial.case(case_id)
        return render(request, "case", item["titulo"], case=item)

    @app.get("/cases/{case_id}/draft", response_class=HTMLResponse)
    def draft(request: Request, case_id: str):
        return render(request, "draft", "Paquete editorial", case=request.app.state.editorial.case(case_id))

    @app.get("/cases/{case_id}/review", response_class=HTMLResponse)
    def review(request: Request, case_id: str):
        return render(request, "review", "Revisión humana", case=request.app.state.editorial.case(case_id),
                      history=request.app.state.repository.review_history(case_id))

    @app.post("/cases/{case_id}/review", response_class=HTMLResponse)
    def update_review(request: Request, case_id: str, decision: Annotated[ReviewRequest, Form()]):
        request.app.state.repository.review(case_id, **decision.model_dump())
        return review(request, case_id)

    @app.get("/queries", response_class=HTMLResponse)
    async def queries(request: Request, q: Annotated[str | None, Query(max_length=2000)] = None):
        answer = None
        if q and q.strip():
            try:
                answer = request.app.state.editorial.query(q)
            except GenerationUnavailable:
                if settings.offline:
                    raise
                if query_provider is None:
                    raise GenerationUnavailable("Live query generation is not configured by the G4 pipeline.") from None
                answer = await query_provider(q, request.app.state.gemini, request.app.state.repository)
                evidence = {item["id_evidencia"]: item for item in request.app.state.repository.records("evidence")}
                try:
                    validate_answer(answer, evidence)
                except (ValueError, TypeError, AttributeError):
                    raise GenerationUnavailable("The query pipeline returned an invalid answer.") from None
        return render(request, "queries", "Consulta con evidencia", answer=answer,
                      examples=request.app.state.repository.records("answer"))

    return app


app = create_app()
