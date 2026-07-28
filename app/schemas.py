from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    format: str = Field(default="feature", max_length=50)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    format: str | None = Field(default=None, max_length=50)


class SceneCreate(BaseModel):
    heading: str = ""
    body: str = ""
    synopsis: str = ""


class SceneUpdate(BaseModel):
    heading: str | None = None
    body: str | None = None
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
