"""FastAPI app for the TVN DeepMind AI editorial desk: routes, error handlers and Jinja filters."""

from contextlib import asynccontextmanager
import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, NamedTuple
from urllib.parse import quote, unquote, urlencode, urlsplit

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from whoami.backend.assistant import DraftAssistant
from whoami.backend.editor import AssistantRequest, SaveDraft
from whoami.backend.gemini import GeminiClient, GenerationUnavailable
from whoami.backend.gemini_completions import CompletionUnavailable
from whoami.backend.live_queries import LiveQueries
from whoami.backend.live_case_files import LiveCaseFiles, NoGroundedClaims
from whoami.backend.pipeline import load_pipeline, validate_answer
from whoami.backend.repository import (
    REVIEW_LABELS, EditorialRepository, InvalidReview, MissingRecord, NoteRequired, ReviewConflict, approval_cautions,
)
from whoami.backend.panama_time import panama_time, short_date
from whoami.backend.presentation import (
    NO_CASE_FILE, abstention_copy, case_questions, draft_budgets, evidence_card, field_label, file_state, latest_date, needs_investigation, pluralize,
    review_timeline, snapshot_view, source_line, split_queries,
)
from whoami.backend.reports import methodology_view, quality_view, score_components, spanish_decimals
from whoami.backend.service import EditorialService
from whoami.backend.settings import Settings
from whoami.contracts import PROCESSED, REVIEW_STATES, REVIEW_TRANSITIONS, TOPIC_LABELS, ReviewState
from whoami.ingest import images as news_images

logger = logging.getLogger(__name__)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: ReviewState
    actor: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("actor")
    @classmethod
    def human_actor(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A human reviewer is required.")
        return value.strip()


REVIEW_FIELD_ERRORS = {
    "state": "Elige una decisión válida para registrar la revisión.",
    "actor": "Escribe el nombre del responsable para registrar la decisión.",
    "expected_version": "La versión de la ficha no es válida. Recarga la página y vuelve a decidir.",
}


QUERY_MAX_LENGTH = 2000


def review_field_error(error: RequestValidationError) -> tuple[str | None, str]:
    """The invalid form field (if one is to blame) and the message that names it."""
    for problem in error.errors():
        if problem["loc"][-1] in REVIEW_FIELD_ERRORS:
            return problem["loc"][-1], REVIEW_FIELD_ERRORS[problem["loc"][-1]]
    return None, "Revisa la decisión, el responsable y la versión de la ficha."


DRAFT_FIELD_LABELS = {
    "titulo": "Título propuesto", "brief": "Brief", "enfoque_interes_publico": "Enfoque de interés público",
    "guion": "Guion", "copy_digital": "Copy digital", "leyenda": "Leyenda",
    "preguntas": "Pregunta", "fuentes_y_verificaciones": "Verificación",
}
FILE_STATE_LABELS = {NO_CASE_FILE: "Sin ficha", **REVIEW_LABELS}
INBOX_PAGE_SIZE = 50
METHODOLOGY_OPTIONS = 25


LIST_FIELDS = frozenset({"preguntas", "fuentes_y_verificaciones"})


def draft_field_error(error: RequestValidationError) -> dict:
    """Name the draft field that failed validation so the editor can highlight it."""
    for problem in error.errors():
        location = problem["loc"]
        if "draft" not in location or location[-1] == "draft":
            continue
        after = location[location.index("draft") + 1:]
        key = after[0]
        index = after[1] if len(after) > 1 and isinstance(after[1], int) else None
        label = DRAFT_FIELD_LABELS.get(key, key)
        name = f"{label} {index + 1}" if index is not None else label
        if problem["type"] == "string_too_long":
            reason = f"supera el máximo de {problem['ctx']['max_length']} caracteres"
        elif problem["type"] == "string_too_short":
            reason = "no puede estar vacío"
        else:
            reason = "no es válido"
        return {"message": f"{name} {reason}.", "field": key, "index": index}
    return {"message": "Revisa los campos: no dejes textos ni preguntas vacíos y respeta los límites de longitud."}


#: Screens whose every figure is real, so the synthetic-data banner would mislead.
REVIEWER_COOKIE = "reviewer"
REAL_DATA_SCREENS = frozenset({"quality"})
GENERATOR_OFFLINE = "Sin conexión: generar la ficha necesita Gemini y esta instancia trabaja sin conexión. Activa el modo en línea para generarla."
GENERATOR_UNAVAILABLE = ("No se pudo generar la ficha ahora: Gemini no respondió o se alcanzó su límite de uso. "
                         "No se guardó nada; reintenta en un momento.")
GENERATOR_UNSUPPORTED = ("Se intentó generar la ficha, pero ninguna afirmación quedó respaldada por las fuentes citadas, así que no se creó. "
                         "Hacen falta más fuentes, o fuentes con más texto, sobre este tema.")
#: Tab names of an open topic, used in the browser title so each tab is told apart in history and tab strips.
PANE_LABELS = {"case": "Historia", "group": "Cobertura", "context": "Contexto", "draft": "Borrador", "review": "Revisión"}
#: What a missing record is called to the editor, by the screen that asked for it.
class MissingSubject(NamedTuple):
    heading: str
    this_record: str


MISSING_SUBJECTS = (("/groups/", MissingSubject("Tema no encontrado", "este tema")),
                    ("/cases/", MissingSubject("Ficha no encontrada", "esta ficha")),
                    ("/evidence/", MissingSubject("Fuente no encontrada", "esta fuente")))
EVIDENCE_LABELS = {
    "suficiente_para_borrador": "Evidencia suficiente", "parcial": "Evidencia parcial", "insuficiente": "Evidencia insuficiente",
}


STATIC_DIRECTORY = Path(__file__).parent / "static"


def number(value: float | int | None, decimals: int | None = None) -> str:
    """Spanish number format: 30.823 and 44,36."""
    if value is None:
        return "-"
    if decimals is None:
        decimals = 0 if float(value).is_integer() else 2
    return f"{value:,.{decimals}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def score(value: float | int | None) -> str:
    """A priority score or its points: always two decimals, so 61 and 84,83 line up."""
    return number(value, 2)


def percent(value: float | int | None, decimals: int = 2) -> str:
    return "-" if value is None else f"{number(value, decimals)} %"


PHOTO_PLACEHOLDER = "/static/img/photo-placeholder.svg"


def image_src(value: str) -> str:
    """One of the app's own static images that exists on disk; anything else (an outlet's URL, a missing copy)
    is the local placeholder, so a page never asks an external server for a photo."""
    if value.startswith("/static/") and ".." not in value and (STATIC_DIRECTORY / value.removeprefix("/static/")).is_file():
        return value
    return PHOTO_PLACEHOLDER


def safe_url(value: str) -> str:
    try:
        return value if urlsplit(value).scheme in ("https", "http") else "#"
    except ValueError:
        return "#"


#: A seam for tests and alternative pipelines; by default the app answers with `LiveQueries`.
QueryProvider = Callable[[str, GeminiClient, EditorialRepository], Awaitable[dict]]


def create_app(settings: Settings | None = None, *, query_provider: QueryProvider | None = None, gemini_transport=None) -> FastAPI:
    settings = settings or Settings.from_environment()
    templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    templates.env.filters.update(panama_time=panama_time, safe_url=safe_url, image_src=image_src, number=number, score=score, percent=percent,
                            short_date=short_date, spanish_decimals=spanish_decimals, latest_date=latest_date, needs_investigation=needs_investigation)
    templates.env.globals.update(review_labels=REVIEW_LABELS, file_states=FILE_STATE_LABELS, evidence_labels=EVIDENCE_LABELS, draft_budgets=draft_budgets,
                                 score_components=score_components, abstention_copy=abstention_copy, approval_cautions=approval_cautions,
                                 review_timeline=review_timeline, pluralize=pluralize, evidence_card=evidence_card,
                                 source_line=lambda evidence_id: source_line(app.state.repository.record("evidence", evidence_id)))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository = EditorialRepository(settings.database)
        repository.import_bundle(load_pipeline(settings.data_directory, settings.output_directory))
        app.state.repository = repository
        app.state.synthetic = any(group.get("sintetico", False) for group in repository.records("group"))
        app.state.editorial = EditorialService(repository, images=news_images.load(settings.data_directory))
        app.state.snapshot = snapshot_view(PROCESSED if settings.demo else settings.data_directory)
        app.state.gemini = GeminiClient(repository, settings, transport=gemini_transport)
        app.state.live_case_files = LiveCaseFiles(repository, app.state.gemini)
        app.state.assistant = DraftAssistant(repository, None if settings.demo else settings.data_directory / "embeddings")
        app.state.live_queries = LiveQueries(app.state.gemini, app.state.assistant.index, app.state.assistant.evidence)
        try:
            yield
        finally:
            await app.state.gemini.close()

    app = FastAPI(title="TVN DeepMind AI", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")

    def render(request: Request, screen: str, title: str, status_code: int = 200, **context):
        return templates.TemplateResponse(request=request, name="screen.html", context={
            "screen": screen, "title": title, "offline": settings.offline, "demo": (settings.demo or request.app.state.synthetic) and screen not in REAL_DATA_SCREENS,
            "fragment": request.headers.get("HX-Request") == "true", "topics": TOPIC_LABELS,
            "target": request.headers.get("HX-Target") if request.headers.get("HX-Request") == "true" else None,
            "workspace": screen == "workspace", "filter_query": "", "base_path": request.url.path,
            "snapshot": request.app.state.snapshot, "review_states": REVIEW_STATES, "transitions": REVIEW_TRANSITIONS, **context,
        }, status_code=status_code)

    def desk(request: Request, title: str, pane: str | None = None, *, group: dict | None = None, case: dict | None = None,
             status_code: int = 200, **context):
        """Master/detail screen: ranked list plus the open workspace; with no group, the first listed one is selected."""
        editorial = request.app.state.editorial
        ranked = editorial.inbox()
        topic_options = sorted({item["tema"] for item in ranked})
        topic = request.query_params.get("topic", "")
        topic = topic if topic in topic_options else ""
        estado = request.query_params.get("estado", "")
        estado = estado if estado in FILE_STATE_LABELS else ""
        topic_search = request.query_params.get("q", "").strip()[:2000]
        groups = [item for item in ranked if (not topic or item["tema"] == topic)
                  and (not estado or file_state(item) == estado)
                  and (not topic_search or topic_search.casefold() in item["titulo"].casefold())]
        filtering = bool(topic or estado or topic_search)
        lead = None if filtering or not ranked else ranked[0]
        listing = groups[1:] if lead else groups
        offset = int(request.query_params["desde"]) if request.query_params.get("desde", "").isdecimal() else 0
        end = offset + INBOX_PAGE_SIZE
        is_more = request.headers.get("HX-Request") == "true" and request.headers.get("HX-Target") == "more-rows"
        rows = listing[offset:end] if is_more else listing[:end]
        active = {key: value for key, value in {"topic": topic, "estado": estado, "q": topic_search}.items() if value}
        opened = group is not None
        if group is None and groups:
            group = editorial.group(groups[0]["id_grupo"])
        if group is not None and case is None and group["id_caso"]:
            case = editorial.case(group["id_caso"])
        pane = pane or ("case" if case else "group")
        document_title = f"{PANE_LABELS[pane]} · {(case or group)['titulo']}" if opened and group else title
        filters = urlencode({"topic": topic, "estado": estado, **({"q": topic_search} if topic_search else {})}) if filtering else ""
        return render(request, "workspace", title, status_code=status_code, groups=groups, rows=rows, total=len(groups), lead=lead,
                      remaining=max(0, len(listing) - end), more_query=urlencode({**active, "desde": end}),
                      rank={item["id_grupo"]: position for position, item in enumerate(ranked, 1)}, topic=topic, estado=estado,
                      topic_options=topic_options, group=group, case=case, pane=pane, opened=opened, document_title=document_title,
                      selected=group["id_grupo"] if group else None, filter_query=f"?{filters}" if filters else "", topic_search=topic_search, **context)

    def case_screen(request: Request, case_id: str, pane: str, title: str | None = None, status_code: int = 200, **context):
        case = request.app.state.editorial.case(case_id)
        group = request.app.state.editorial.group(case["id_grupo"])
        return desk(request, title or case["titulo"], pane, group=group, case=case, status_code=status_code, **context)

    def review_screen(request: Request, case_id: str, status_code: int = 200, error: str | None = None, form: dict | None = None,
                      error_field: str | None = None):
        remembered = unquote(request.cookies.get(REVIEWER_COOKIE, ""))
        return case_screen(request, case_id, "review", "Revisión humana", status_code, error=error, error_field=error_field,
                           form={"actor": remembered, **(form or {})},
                           history=request.app.state.repository.review_history(case_id),
                           audit=request.app.state.repository.audit_history(case_id))

    @app.exception_handler(MissingRecord)
    async def missing_record(request: Request, error: MissingRecord):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"message": "La ficha o la fuente ya no están disponibles."}, status_code=404)
        subject = next((name for prefix, name in MISSING_SUBJECTS if request.url.path.startswith(prefix)), None)
        if subject is None:
            return render(request, "error", "Registro no disponible", status_code=404, message=str(error))
        return render(request, "error", subject.heading, status_code=404,
                      message=f"No encontramos {subject.this_record}. Puede que el enlace sea antiguo o esté incompleto.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException):
        if request.url.path.startswith(("/api/", "/static/")):
            return await http_exception_handler(request, error)
        if error.status_code == 404:
            return render(request, "error", "Página no encontrada", status_code=404,
                          message="No encontramos esta página. Puede que el enlace sea antiguo o esté incompleto.")
        return render(request, "error", "Página no disponible", status_code=error.status_code,
                      message="Esta página no admite la acción solicitada.")

    @app.exception_handler(ReviewConflict)
    async def review_conflict(request: Request, error: ReviewConflict):
        return render(request, "error", "La ficha cambió", status_code=409, message=str(error))

    @app.exception_handler(InvalidReview)
    async def invalid_review(request: Request, error: InvalidReview):
        return render(request, "error", "Decisión no válida", status_code=422, message=str(error))

    @app.exception_handler(GenerationUnavailable)
    async def unavailable(request: Request, error: GenerationUnavailable):
        logger.warning("Generation unavailable: %s", error)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"message": "El asistente no pudo completar una respuesta verificable. Intenta de nuevo más tarde."}, status_code=503)
        return render(request, "error", "Consulta no disponible", status_code=503,
                      message="La consulta no pudo completarse. Intenta de nuevo más tarde.")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return JSONResponse(draft_field_error(error), status_code=422)
        case_id = request.path_params.get("case_id")
        if request.method == "POST" and case_id and request.url.path.endswith("/review"):
            form = dict((await request.form()).items())
            field, message = review_field_error(error)
            return review_screen(request, case_id, 422, message, form, field)
        if request.url.path == "/queries":
            return render(request, "error", "Consulta demasiado larga", status_code=422,
                          message=f"La consulta supera los {number(QUERY_MAX_LENGTH)} caracteres. Acórtala y vuelve a intentarlo.")
        return render(request, "error", "Revisa los campos", status_code=422,
                      message="La solicitud contiene campos ausentes o no válidos. Revisa la decisión y el responsable.")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/inbox")

    @app.get("/health")
    def health(request: Request):
        return {"status": "ready", "demo": settings.demo, "offline": settings.offline,
                "groups": len(request.app.state.repository.records("group"))}

    @app.get("/quality", response_class=HTMLResponse)
    def quality(request: Request):
        return render(request, "quality", "Calidad de datos", quality=quality_view(PROCESSED if settings.demo else settings.data_directory))

    @app.get("/inbox", response_class=HTMLResponse)
    def inbox(request: Request):
        return desk(request, "Agenda priorizada")

    @app.get("/methodology", response_class=HTMLResponse)
    def methodology(request: Request, grupo: str | None = None, q: Annotated[str, Query(max_length=200)] = ""):
        return render(request, "methodology", "Metodología", search=q.strip(),
                      methodology=methodology_view(request.app.state.editorial.inbox(), grupo, q, METHODOLOGY_OPTIONS))

    @app.get("/groups/{group_id}", response_class=HTMLResponse)
    def group(request: Request, group_id: str):
        item = request.app.state.editorial.group(group_id)
        return desk(request, item["titulo"], "group", group=item)

    def generator_failure(request: Request, group: dict, status_code: int, message: str, *, retry: bool = False):
        """The generator panel after a refused or failed attempt; htmx swaps it in place of the old panel."""
        state = {"message": message, "retry": retry}
        if request.headers.get("HX-Request") != "true":
            return desk(request, group["titulo"], "group", group=group, status_code=status_code, generator=state)
        query = request.url.query
        return templates.TemplateResponse(request=request, name="views/case/_generator.html", status_code=status_code,
                                          headers={"HX-Retarget": "#case-file-generator", "HX-Reswap": "outerHTML"},
                                          context={"group": group, "generator": state, "offline": settings.offline,
                                                   "filter_query": f"?{query}" if query else ""})

    @app.post("/groups/{group_id}/case-file", response_class=HTMLResponse)
    async def generate_case_file(request: Request, group_id: str):
        group = request.app.state.editorial.group(group_id)
        if group["id_caso"] is None:
            if settings.offline:
                return generator_failure(request, group, 409, GENERATOR_OFFLINE)
            try:
                group["id_caso"] = await request.app.state.live_case_files.generate(group_id)
            except CompletionUnavailable as error:
                logger.warning("Case file generation unavailable for %s: %s", group_id, error)
                return generator_failure(request, group, 503, GENERATOR_UNAVAILABLE, retry=True)
            except NoGroundedClaims as error:
                logger.warning("No grounded claims for %s: %s", group_id, error)
                return generator_failure(request, group, 422, GENERATOR_UNSUPPORTED)
        url = f"/cases/{quote(group['id_caso'])}" + (f"?{request.url.query}" if request.url.query else "")
        if request.headers.get("HX-Request") != "true":
            return RedirectResponse(url, status_code=303)
        response = case_screen(request, group["id_caso"], "case")
        response.headers["HX-Push-Url"] = url
        return response

    @app.get("/groups/{group_id}/context", response_class=HTMLResponse)
    def context(request: Request, group_id: str):
        return desk(request, "Contexto oficial", "context", group=request.app.state.editorial.group(group_id))

    @app.get("/evidence/{evidence_id}", response_class=HTMLResponse)
    def evidence(request: Request, evidence_id: str):
        item = request.app.state.repository.record("evidence", evidence_id)
        return render(request, "evidence", item["titulo"], evidence=evidence_card(item))

    @app.get("/cases/{case_id}", response_class=HTMLResponse)
    def case(request: Request, case_id: str):
        return case_screen(request, case_id, "case")

    @app.get("/cases/{case_id}/draft", response_class=HTMLResponse)
    def draft(request: Request, case_id: str):
        assistant = request.app.state.assistant
        questions = case_questions(request.app.state.repository.records("answer"), assistant.sources(request.app.state.repository.case(case_id)))
        return case_screen(request, case_id, "draft", "Borrador", case_questions=questions)

    def editor_record(case: dict) -> dict:
        return {"draft": case["borrador"], "source_ids": case["ids_fuente"], "version": case["version"],
                "review_state": case["estado_revision"]}

    @app.get("/api/evidence/{evidence_id}")
    def get_evidence(request: Request, evidence_id: str):
        evidence = request.app.state.repository.record("evidence", evidence_id)
        return {**evidence, "etiquetas": {key: field_label(key) for key in evidence["campos"]},
                "fecha_texto": panama_time(evidence["fecha"]) if evidence["fecha"] else None}

    @app.post("/api/cases/{case_id}/assistant")
    async def draft_assistant(request: Request, case_id: str, payload: AssistantRequest):
        return await request.app.state.assistant.respond(case_id, payload, request.app.state.gemini)

    @app.get("/api/cases/{case_id}/draft")
    def get_draft(request: Request, case_id: str):
        return editor_record(request.app.state.repository.case(case_id))

    @app.put("/api/cases/{case_id}/draft")
    def save_draft(request: Request, case_id: str, payload: SaveDraft):
        try:
            case = request.app.state.repository.save_draft(case_id, **payload.model_dump())
        except ReviewConflict as error:
            return JSONResponse({"message": str(error)}, status_code=409)
        except (MissingRecord, InvalidReview) as error:
            return JSONResponse({"message": str(error)}, status_code=422)
        return editor_record(case)

    @app.get("/cases/{case_id}/review", response_class=HTMLResponse)
    def review(request: Request, case_id: str):
        return review_screen(request, case_id)

    @app.post("/cases/{case_id}/review", response_class=HTMLResponse)
    def update_review(request: Request, case_id: str, decision: Annotated[ReviewRequest, Form()]):
        try:
            request.app.state.repository.review(case_id, **decision.model_dump())
        except ReviewConflict:
            return review_screen(request, case_id, 409, "Otra persona actualizó esta ficha mientras la revisabas. Revisa el estado actual y vuelve a decidir.", decision.model_dump())
        except NoteRequired as error:
            return review_screen(request, case_id, 422, str(error), decision.model_dump(), "note")
        except InvalidReview as error:
            return review_screen(request, case_id, 422, str(error), decision.model_dump())
        response = review_screen(request, case_id, form={"actor": decision.actor})
        response.set_cookie(REVIEWER_COOKIE, quote(decision.actor), httponly=True, samesite="lax")
        return response

    @app.get("/queries", response_class=HTMLResponse)
    async def queries(request: Request, q: Annotated[str | None, Query(max_length=QUERY_MAX_LENGTH)] = None):
        answer = None
        examples, probes = split_queries(request.app.state.repository.records("answer"))
        try:
            if q and q.strip():
                try:
                    answer = request.app.state.editorial.query(q)
                except GenerationUnavailable:
                    if settings.offline:
                        raise
                    answer = await live_answer(request, q)
        except (GenerationUnavailable, CompletionUnavailable) as error:
            if settings.offline:
                # Offline, a question outside the precomputed set is an honest abstention, not a server fault.
                return render(request, "queries", "Consulta con evidencia", answer=None, examples=examples, probes=probes,
                              query_status="no_precomputed", query_text=q)
            logger.warning("Query unavailable: %s", error)
            return render(request, "queries", "Consulta con evidencia", status_code=503, answer=None, examples=examples, probes=probes,
                          query_status="unavailable", query_text=q)
        return render(request, "queries", "Consulta con evidencia", answer=answer, examples=examples, probes=probes, query_text=q)

    async def live_answer(request: Request, question: str) -> dict:
        provider = query_provider or (lambda text, gemini, repository: request.app.state.live_queries.answer(text))
        try:
            async with asyncio.timeout(settings.generation_timeout):
                answer = await provider(question, request.app.state.gemini, request.app.state.repository)
        except TimeoutError:
            raise GenerationUnavailable("The query deadline was exceeded.") from None
        evidence = {item["id_evidencia"]: item for item in request.app.state.repository.records("evidence")}
        try:
            validate_answer(answer, evidence)
        except (ValueError, TypeError, AttributeError):
            raise GenerationUnavailable("The query pipeline returned an invalid answer.") from None
        return answer

    return app


app = create_app()
