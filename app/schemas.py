from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ScriptLineType = Literal[
    "heading",
    "action",
    "character",
    "dialogue",
    "parenthetical",
    "transition",
]


class SemanticLine(BaseModel):
    type: ScriptLineType
    text: str = ""


class ProjectCreate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
    )
    format: str = Field(
        default="feature",
        max_length=50,
    )


class ProjectUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    format: str | None = Field(
        default=None,
        max_length=50,
    )


class SceneCreate(BaseModel):
    heading: str = ""
    body: str = ""
    semantic_lines: list[SemanticLine] = Field(
        default_factory=list
    )
    synopsis: str = ""


class SceneUpdate(BaseModel):
    heading: str | None = None
    body: str | None = None
    semantic_lines: list[SemanticLine] | None = None
    synopsis: str | None = None
    status: str | None = None


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)
    category: str = "general"


class BreakdownItemCreate(BaseModel):
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source: str = "manual"
    state: str = "confirmed"


class BreakdownItemUpdate(BaseModel):
    category: str | None = Field(
        default=None,
        min_length=1,
    )
    name: str | None = Field(
        default=None,
        min_length=1,
    )
    source: str | None = Field(
        default=None,
        min_length=1,
    )
    state: str | None = Field(
        default=None,
        min_length=1,
    )