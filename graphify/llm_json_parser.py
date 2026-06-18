"""Robust JSON parsing for LLM graph-extraction responses.

Small local models (notably Ollama Gemma) sometimes emit split or malformed
envelopes — e.g. ``{"nodes":[...]\\n{"edges":[...]}`` without closing the
outer object. This module heals those patterns and merges multiple top-level
JSON objects before ``llm.py`` consumes the result.
"""
from __future__ import annotations

import json
import re
import sys

LLM_JSON_MAX_BYTES = 10 * 1024 * 1024  # 10 MB hard cap before json.loads (F-016)

_EMPTY_FRAGMENT: dict = {"nodes": [], "edges": [], "hyperedges": []}

# ``{"nodes":[...]`` then ``{"edges":[...]}`` with the closing ``}`` omitted.
_SPLIT_ENVELOPE_RE = re.compile(
    r"(\])\s*(\{\s*\"(?:edges|hyperedges)\"\s*:)",
    re.DOTALL,
)
# Gemma via Google OpenAI-compat sometimes prefixes JSON with a <thought> block.
_THOUGHT_BLOCK_RE = re.compile(r"<thought>.*?</thought>", re.IGNORECASE | re.DOTALL)


def strip_model_thought_blocks(text: str) -> str:
    """Remove model thinking preamble (Gemma ``<thought>…</thought>``) before JSON parse."""
    cleaned = _THOUGHT_BLOCK_RE.sub("", text)
    stripped = cleaned.lstrip()
    if stripped.lower().startswith("<thought"):
        brace = cleaned.find("{")
        if brace != -1:
            return cleaned[brace:].lstrip()
        return ""
    return cleaned.strip()


def heal_split_json_envelope(text: str) -> str:
    """Insert missing ``}`` before trailing edges/hyperedges objects."""
    healed = text
    while True:
        next_healed = _SPLIT_ENVELOPE_RE.sub(r"\1}\2", healed, count=1)
        if next_healed == healed:
            return healed
        healed = next_healed


def extract_balanced_json_object(text: str, start: int) -> tuple[str | None, int]:
    """Return a balanced ``{...}`` substring starting at *start*, or ``(None, start)``."""
    if start >= len(text) or text[start] != "{":
        return None, start
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
    return None, start


def extract_all_json_objects(text: str) -> list[dict]:
    """Scan *text* for every top-level JSON object and parse each one."""
    objects: list[dict] = []
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset] in " \t\n\r":
            offset += 1
        if offset >= len(text):
            break
        if text[offset] != "{":
            next_brace = text.find("{", offset)
            if next_brace == -1:
                break
            offset = next_brace
        fragment, end = extract_balanced_json_object(text, offset)
        if fragment is None:
            break
        try:
            obj = json.loads(fragment)
        except json.JSONDecodeError:
            offset = end
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        offset = end
    return objects


def merge_json_fragments(objects: list[dict]) -> dict:
    """Merge nodes/edges/hyperedges arrays from multiple parsed fragments."""
    merged: dict = {"nodes": [], "edges": [], "hyperedges": []}
    for obj in objects:
        merged["nodes"].extend(obj.get("nodes") or [])
        merged["edges"].extend(obj.get("edges") or [])
        merged["hyperedges"].extend(obj.get("hyperedges") or [])
    return merged


def _strip_markdown_fences(raw: str) -> str:
    """Strip optional markdown fences anywhere in the text."""
    stripped = raw.strip()
    fence_start = stripped.find("```")
    if fence_start == -1:
        return stripped
    after_fence = stripped[fence_start + 3 :]
    nl = after_fence.find("\n")
    if nl != -1 and after_fence[:nl].strip().lower() in {"json", "javascript", "js", ""}:
        after_fence = after_fence[nl + 1 :]
    fence_end = after_fence.rfind("```")
    if fence_end != -1:
        return after_fence[:fence_end].strip()
    return after_fence.strip()


def parse_llm_json(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON. Returns empty fragment on failure.

    Caps the input at ``LLM_JSON_MAX_BYTES`` so a hostile or runaway model
    response cannot exhaust memory inside ``json.loads`` (F-016).
    """
    if len(raw) > LLM_JSON_MAX_BYTES:
        print(
            f"[graphify] LLM response exceeds {LLM_JSON_MAX_BYTES} bytes "
            f"({len(raw)} bytes); refusing to parse and dropping chunk.",
            file=sys.stderr,
        )
        return dict(_EMPTY_FRAGMENT)
    stripped = strip_model_thought_blocks(_strip_markdown_fences(raw))
    healed = heal_split_json_envelope(stripped)
    for candidate in (stripped, healed):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    objects = extract_all_json_objects(healed)
    if objects:
        merged = merge_json_fragments(objects)
        if merged["nodes"] or merged["edges"] or merged["hyperedges"]:
            return merged
    start = healed.find("{")
    if start != -1:
        fragment, _ = extract_balanced_json_object(healed, start)
        if fragment is not None:
            try:
                return json.loads(fragment)
            except json.JSONDecodeError:
                pass
    print(
        f"[graphify] LLM returned invalid JSON, skipping chunk "
        f"(first 200 chars: {raw[:200]!r})",
        file=sys.stderr,
    )
    return dict(_EMPTY_FRAGMENT)
