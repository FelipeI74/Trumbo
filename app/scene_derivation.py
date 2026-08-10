import re
from dataclasses import dataclass
from typing import Iterable

_HEADING_TOKEN_ONLY_RE = re.compile(r"^(INT\.|EXT\.)$", re.IGNORECASE)
_HEADING_COMPLETE_RE = re.compile(r"^(INT\.|EXT\.)\s*.+", re.IGNORECASE)


@dataclass(frozen=True)
class ReconciliationResult:
    headings: list[str]
    kept_scene_ids: list[int]
    created_scene_ids: list[int]
    deleted_scene_ids: list[int]

    @property
    def scene_count(self) -> int:
        return len(self.headings)


def is_complete_scene_heading(value: str) -> bool:
    text = (value or "").strip()

    if not text:
        return False

    return bool(_HEADING_COMPLETE_RE.match(text)) and not bool(
        _HEADING_TOKEN_ONLY_RE.match(text)
    )


def derive_scene_headings_from_lines(lines: Iterable[str]) -> list[str]:
    headings: list[str] = []

    for raw_line in lines:
        text = str(raw_line or "").strip()

        if is_complete_scene_heading(text):
            headings.append(text.upper())

    return headings


def derive_scene_headings_from_document(document_text: str) -> list[str]:
    return derive_scene_headings_from_lines((document_text or "").splitlines())


def reconcile_scene_ids(
    existing_scene_ids: list[int],
    headings: list[str],
    next_scene_id: int | None = None,
) -> ReconciliationResult:
    required_count = len(headings)
    kept_scene_ids = list(existing_scene_ids[:required_count])
    deleted_scene_ids = list(existing_scene_ids[required_count:])

    created_scene_ids: list[int] = []

    if len(kept_scene_ids) < required_count:
        seed = next_scene_id
        if seed is None:
            seed = (max(existing_scene_ids) + 1) if existing_scene_ids else 1

        for offset in range(required_count - len(kept_scene_ids)):
            created_scene_ids.append(seed + offset)

    return ReconciliationResult(
        headings=list(headings),
        kept_scene_ids=kept_scene_ids,
        created_scene_ids=created_scene_ids,
        deleted_scene_ids=deleted_scene_ids,
    )


def apply_reconciliation(
    existing_scene_ids: list[int],
    document_text: str,
    next_scene_id: int | None = None,
) -> tuple[list[int], ReconciliationResult, int]:
    headings = derive_scene_headings_from_document(document_text)
    result = reconcile_scene_ids(existing_scene_ids, headings, next_scene_id)

    updated_ids = [
        *result.kept_scene_ids,
        *result.created_scene_ids,
    ]

    next_seed = next_scene_id
    if next_seed is None:
        next_seed = (max(existing_scene_ids) + 1) if existing_scene_ids else 1

    next_seed += len(result.created_scene_ids)

    return updated_ids, result, next_seed
