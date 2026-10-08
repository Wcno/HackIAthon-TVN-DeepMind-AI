"""Human-edited packages are separate from the validated pipeline seed."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
ListText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class EditedDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    brief: Text
    enfoque_interes_publico: Text
    preguntas: list[ListText] = Field(max_length=50)
    fuentes_y_verificaciones: list[ListText] = Field(max_length=100)
    guion: Text
    copy_digital: Text
    leyenda: str | None = Field(default=None, max_length=1000)


class SaveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: EditedDraft
    source_ids: list[str] = Field(max_length=100)
    expected_version: int = Field(ge=1)


#: Text fields Co-News can rewrite; list fields are edited by hand.
RewritableField = Literal["titulo", "brief", "enfoque_interes_publico", "guion", "copy_digital"]


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    action: Literal["ask", "articles", "headlines", "shorten", "neutral", "gaps", "contradictions", "rewrite"] = "ask"
    # Co-News: the field a rewrite targets; None lets it choose among the text fields of the whole draft.
    field: RewritableField | None = None
    draft: EditedDraft
    source_ids: list[str] = Field(default_factory=list, max_length=100)
