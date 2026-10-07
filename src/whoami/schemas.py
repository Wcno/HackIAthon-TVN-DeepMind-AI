"""Pipeline output schemas shared by the `ai`, `api` and frontend lanes (issue G2).

Frozen dataclasses with no third-party dependencies. Every invariant of the challenge that can be
checked from the data alone is enforced at construction, so a lane cannot hand over a record
another lane would have to distrust.
"""

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from whoami.contracts import (
    ANSWER_STATES,
    BRIEF_MAX_WORDS,
    CLAIM_TYPES,
    COPY_MAX_WORDS,
    EVIDENCE_PREFIXES,
    EVIDENCE_STATES,
    HEADLINE_ONLY_LEGEND,
    MODALITY,
    NO_TOPIC,
    RESEARCH_QUESTIONS,
    REVIEW_STATES,
    RULES_VERSION,
    SCORE_RANGES,
    SCORE_WEIGHTS,
    TEXT_SCOPE_HEADLINE,
    TEXT_SCOPES,
    TOPICS,
)

#: §7: ISO 8601 in UTC. The interface converts to Panama time for display.
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


@dataclass(frozen=True)
class Componentes:
    """R, I, U, N, E of the attention score, each in 0-1."""

    R: float
    I: float  # noqa: E741
    U: float
    N: float
    E: float

    def __post_init__(self) -> None:
        for name in SCORE_WEIGHTS:
            value = getattr(self, name)
            if not (isinstance(value, int | float) and math.isfinite(value) and 0 <= value <= 1):
                raise ValueError(f"componente {name} debe estar entre 0 y 1: {value!r}")


def calcular_puntaje(componentes: Componentes) -> float:
    return round(sum(weight * getattr(componentes, name) for name, weight in SCORE_WEIGHTS.items()), 2)


def rango_de(puntaje: float) -> str:
    if not (isinstance(puntaje, int | float) and math.isfinite(puntaje) and 0 <= puntaje <= 100):
        raise ValueError(f"puntaje fuera de 0-100: {puntaje!r}")
    for name, low, high in SCORE_RANGES:
        if low <= puntaje < high or (name == "alto" and puntaje == 100):
            return name
    raise AssertionError("unreachable: ranges cover 0-100")


@dataclass(frozen=True)
class Puntaje:
    """Attention score with its components; value and range are derived, never trusted from a lane."""

    componentes: Componentes
    valor: float
    rango: str
    version_reglas: str
    justificaciones: dict[str, str]

    def __post_init__(self) -> None:
        missing = [name for name in SCORE_WEIGHTS if not str(self.justificaciones.get(name, "")).strip()]
        if missing:
            raise ValueError(f"falta justificación para los componentes: {', '.join(missing)}")
        expected = calcular_puntaje(self.componentes)
        if self.valor != expected:
            raise ValueError(f"valor {self.valor} no coincide con los componentes ({expected})")
        if self.rango != rango_de(self.valor):
            raise ValueError(f"rango {self.rango!r} no corresponde al valor {self.valor}")

    @classmethod
    def de(cls, componentes: Componentes, justificaciones: dict[str, str]) -> "Puntaje":
        valor = calcular_puntaje(componentes)
        return cls(componentes, valor, rango_de(valor), RULES_VERSION, dict(justificaciones))


@dataclass(frozen=True)
class Evidencia:
    """One citable record: a news item, an official indicator, an INEC series point or an earthquake."""

    id_evidencia: str
    tipo: str
    titulo: str
    url: str
    fecha: str | None
    campos: dict[str, str]

    def __post_init__(self) -> None:
        prefix = EVIDENCE_PREFIXES.get(self.tipo)
        if prefix is None:
            raise ValueError(f"tipo desconocido: {self.tipo!r}")
        if not self.id_evidencia.startswith(prefix):
            raise ValueError(f"id_evidencia {self.id_evidencia!r} debe empezar por {prefix!r} para tipo {self.tipo!r}")
        _utc("fecha", self.fecha)
        if not self.campos:
            raise ValueError("campos no puede estar vacío: no habría qué citar")


@dataclass(frozen=True)
class Cita:
    """Points at a passage of one field of one evidence record; a bare URL is not a citation (§7)."""

    id_evidencia: str
    campo: str
    pasaje: str

    def __post_init__(self) -> None:
        for name in ("id_evidencia", "campo", "pasaje"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} no puede estar vacío")


def errores_de_citas(citas: Iterable[Cita], evidencias: Mapping[str, Evidencia]) -> list[str]:
    """Deterministic check of §7: the id exists, the field exists and the passage is literal."""
    errores = []
    for cita in citas:
        evidencia = evidencias.get(cita.id_evidencia)
        if evidencia is None:
            errores.append(f"{cita.id_evidencia}: la evidencia no existe")
        elif cita.campo not in evidencia.campos:
            errores.append(f"{cita.id_evidencia}: el campo {cita.campo!r} no existe")
        elif cita.pasaje not in evidencia.campos[cita.campo]:
            errores.append(f"{cita.id_evidencia}: el pasaje no es literal en {cita.campo!r}: {cita.pasaje!r}")
    return errores


@dataclass(frozen=True)
class Afirmacion:
    """A claim of a fiche or draft. Accusations are statements attributed to someone, never facts (§8)."""

    id_afirmacion: str
    texto: str
    tipo: str
    citas: tuple[Cita, ...]
    atribuida_a: str | None = None

    def __post_init__(self) -> None:
        if self.tipo not in CLAIM_TYPES:
            raise ValueError(f"tipo debe ser uno de {CLAIM_TYPES}: {self.tipo!r}")
        if not self.texto.strip():
            raise ValueError("texto no puede estar vacío")
        if not self.citas:
            raise ValueError(f"la afirmación {self.id_afirmacion} necesita al menos una cita")
        if self.tipo == "declaracion" and not (self.atribuida_a or "").strip():
            raise ValueError(f"la declaración {self.id_afirmacion} necesita atribuida_a")


def _utc(name: str, value: str | None) -> None:
    if value is not None and not _UTC.fullmatch(value):
        raise ValueError(f"{name} debe ser ISO 8601 UTC (AAAA-MM-DDTHH:MM:SSZ): {value!r}")


def _in(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} debe ser uno de {allowed}: {value!r}")


@dataclass(frozen=True)
class PaqueteEditorial:
    """§3 editorial package. Never invents interviews, quotes or available images."""

    titulo: str
    brief: str
    enfoque_interes_publico: str
    preguntas: tuple[str, ...]
    fuentes_y_verificaciones: tuple[str, ...]
    guion: str
    copy_digital: str
    leyenda: str | None

    def __post_init__(self) -> None:
        if len(self.brief.split()) > BRIEF_MAX_WORDS:
            raise ValueError(f"brief excede {BRIEF_MAX_WORDS} palabras")
        if len(self.copy_digital.split()) > COPY_MAX_WORDS:
            raise ValueError(f"copy_digital excede {COPY_MAX_WORDS} palabras")
        if len(self.preguntas) != RESEARCH_QUESTIONS:
            raise ValueError(f"preguntas debe tener exactamente {RESEARCH_QUESTIONS} elementos")
        for name in ("titulo", "brief", "enfoque_interes_publico", "guion", "copy_digital"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} no puede estar vacío")


@dataclass(frozen=True)
class VersionContradictoria:
    valor: str
    alcance: str
    id_evidencia: str


@dataclass(frozen=True)
class Contradiccion:
    """Incompatible claims inside one group: both versions are shown and verification stays pending (T05)."""

    descripcion: str
    versiones: tuple[VersionContradictoria, ...]

    def __post_init__(self) -> None:
        if len(self.versiones) < 2:
            raise ValueError("una contradicción necesita al menos dos versiones")


@dataclass(frozen=True)
class Ficha:
    """One case of `fichas.jsonl` (§7), plus the fields the screens need."""

    id_caso: str
    modalidad: str
    id_grupo: str
    titulo: str
    tema: str
    alcance_texto: str
    ids_fuente: tuple[str, ...]
    afirmaciones: tuple[Afirmacion, ...]
    puntaje: Puntaje
    estado_evidencia: str
    estado_revision: str
    borrador: PaqueteEditorial | None
    vacios: tuple[str, ...]
    contradicciones: tuple[Contradiccion, ...]
    accion_recomendada: str
    sintetico: bool = False

    def __post_init__(self) -> None:
        if self.modalidad != MODALITY:
            raise ValueError(f"modalidad debe ser {MODALITY!r}: {self.modalidad!r}")
        _in("tema", self.tema, (*TOPICS, NO_TOPIC))
        _in("alcance_texto", self.alcance_texto, TEXT_SCOPES)
        _in("estado_evidencia", self.estado_evidencia, EVIDENCE_STATES)
        _in("estado_revision", self.estado_revision, REVIEW_STATES)
        if not self.afirmaciones:
            raise ValueError("una ficha necesita al menos una afirmación")
        if not self.accion_recomendada.strip():
            raise ValueError("accion_recomendada no puede estar vacía")
        cited = {cita.id_evidencia for afirmacion in self.afirmaciones for cita in afirmacion.citas}
        if not cited <= set(self.ids_fuente):
            raise ValueError(f"ids_fuente no incluye las evidencias citadas: {sorted(cited - set(self.ids_fuente))}")
        if self.estado_evidencia != "suficiente_para_borrador" and not self.vacios:
            raise ValueError("vacios debe decir qué falta cuando la evidencia no es suficiente")
        if self.estado_revision == "aprobado_como_borrador" and (
            self.estado_evidencia == "insuficiente" or self.borrador is None
        ):
            raise ValueError("estado_revision aprobado_como_borrador exige evidencia no insuficiente y un borrador")
        if (
            self.borrador is not None
            and self.alcance_texto == TEXT_SCOPE_HEADLINE
            and self.borrador.leyenda != HEADLINE_ONLY_LEGEND
        ):
            raise ValueError(f"leyenda del borrador debe ser {HEADLINE_ONLY_LEGEND!r} cuando solo hay titular/metadatos")


@dataclass(frozen=True)
class Miembro:
    """A news item inside a group. `procedencia` is who produced the content: an agency republished by
    three outlets is one procedencia, so repetition is not read as corroboration (CU-03)."""

    id_noticia: str
    titulo: str
    url: str
    medio: str
    procedencia: str
    fecha_publicacion: str
    alcance_texto: str
    recirculada_en: str | None

    def __post_init__(self) -> None:
        if not self.id_noticia.startswith(EVIDENCE_PREFIXES["noticia"]):
            raise ValueError(f"id_noticia debe empezar por {EVIDENCE_PREFIXES['noticia']!r}: {self.id_noticia!r}")
        _utc("fecha_publicacion", self.fecha_publicacion)
        _utc("recirculada_en", self.recirculada_en)
        _in("alcance_texto", self.alcance_texto, TEXT_SCOPES)
        if self.recirculada_en is not None and self.recirculada_en <= self.fecha_publicacion:
            raise ValueError("recirculada_en debe ser posterior a la fecha de publicación original (T03)")


@dataclass(frozen=True)
class VinculoContexto:
    """An official indicator or event linked to a group, with what is needed to read it correctly."""

    id_evidencia: str
    etiqueta: str
    pais: str
    periodo: str
    valor: float | None
    unidad: str
    limitaciones: str
    razon: str

    def __post_init__(self) -> None:
        if self.id_evidencia.startswith(EVIDENCE_PREFIXES["noticia"]) or not any(
            self.id_evidencia.startswith(prefix) for prefix in EVIDENCE_PREFIXES.values()
        ):
            raise ValueError(f"id_evidencia debe ser de un indicador, serie INEC o sismo: {self.id_evidencia!r}")
        for name in ("periodo", "unidad", "limitaciones", "razon"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} no puede estar vacío")


@dataclass(frozen=True)
class Grupo:
    """News about the same event, ranked in the inbox. Counters are derived from the members."""

    id_grupo: str
    titulo: str
    tema: str
    miembros: tuple[Miembro, ...]
    puntaje: Puntaje
    estado_evidencia: str
    estado_revision: str
    contexto: tuple[VinculoContexto, ...]
    sin_contexto_motivo: str | None
    id_caso: str | None
    sintetico: bool = False

    def __post_init__(self) -> None:
        _in("tema", self.tema, (*TOPICS, NO_TOPIC))
        _in("estado_evidencia", self.estado_evidencia, EVIDENCE_STATES)
        _in("estado_revision", self.estado_revision, REVIEW_STATES)
        if not self.miembros:
            raise ValueError("un grupo necesita al menos un miembro")
        if len({m.id_noticia for m in self.miembros}) != len(self.miembros):
            raise ValueError("miembros no puede repetir id_noticia")
        if bool(self.contexto) == bool((self.sin_contexto_motivo or "").strip()):
            raise ValueError("sin_contexto_motivo se indica si y solo si el grupo no tiene contexto oficial")

    @property
    def n_noticias(self) -> int:
        return len(self.miembros)

    @property
    def n_medios(self) -> int:
        return len({m.medio for m in self.miembros})

    @property
    def n_procedencias(self) -> int:
        return len({m.procedencia for m in self.miembros})


def ordenar_bandeja(grupos: Iterable[Grupo]) -> list[Grupo]:
    """§4: highest score first; ties go to the more urgent group, then to the lower id."""
    return sorted(grupos, key=lambda g: (-g.puntaje.valor, -g.puntaje.componentes.U, g.id_grupo))


@dataclass(frozen=True)
class Respuesta:
    """Answer of the query box. Without evidence it abstains and says what information is needed (§8)."""

    id_consulta: str
    consulta: str
    estado: str
    respuesta: str | None = None
    citas: tuple[Cita, ...] = ()
    motivo_abstencion: str | None = None
    faltante: str | None = None
    versiones: tuple[VersionContradictoria, ...] = ()

    def __post_init__(self) -> None:
        _in("estado", self.estado, ANSWER_STATES)
        if self.estado == "respondida":
            if not (self.respuesta or "").strip() or not self.citas:
                raise ValueError("una respuesta respondida necesita texto y citas")
        elif self.estado == "abstencion":
            if self.respuesta or self.citas:
                raise ValueError("una abstencion no responde ni cita")
            if not (self.motivo_abstencion or "").strip():
                raise ValueError("una abstencion necesita motivo_abstencion")
            if not (self.faltante or "").strip():
                raise ValueError("una abstencion necesita faltante: qué información se necesita")
        elif len(self.versiones) < 2:
            raise ValueError("una contradiccion necesita al menos dos versiones")


@dataclass(frozen=True)
class RegistroRevision:
    """One human decision on a case (§3 stage 7). The history of a case is a list of these."""

    id_caso: str
    estado: str
    responsable: str | None
    fecha: str
    nota: str | None

    def __post_init__(self) -> None:
        _in("estado", self.estado, REVIEW_STATES)
        _utc("fecha", self.fecha)
        if self.estado != "nuevo" and not (self.responsable or "").strip():
            raise ValueError("responsable es obligatorio: la revisión la hace una persona")
