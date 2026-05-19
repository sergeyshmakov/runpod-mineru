"""Reference adapter showing how to wrap MineruClient in a domain-typed
"ParserAdapter" interface, of the sort a document indexer (or any
RAG/context system) would use internally.

A typical shape in a downstream project:

    services/parsers/src/your_parsers/
        adapter.py             # the ParserAdapter ABC below
        adapters/mineru.py     # the MineruParserAdapter below
        normalize.py           # the _to_parsed_document helpers below
        models.py              # the ParsedDocument / Section / Chunk models below

This single-file demo collapses all four into one runnable script for clarity.
It's NOT meant to be imported by anything — it's a copy-and-specialize template.

What it demonstrates
--------------------
1. A typed `ParsedDocument` with sections + chunks + page provenance.
2. An abstract `ParserAdapter` interface that different backends can implement
   (MinerU today, another parser tomorrow).
3. A concrete `MineruParserAdapter` that calls `MineruClient.parse_pdf()` and
   converts MinerU's `content_list_v2.json` entries into the domain model.
4. Title-vs-paragraph classification, section nesting, and section-aware
   chunking.

Run it with a small public PDF to smoke-test:

    set RUNPOD_API_KEY=...
    set RUNPOD_ENDPOINT_ID=...
    python examples/parser_adapter_example.py https://example.com/report.pdf
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
from abc import ABC, abstractmethod
from typing import Any, Literal

from mineru_client import MineruClient


# -----------------------------------------------------------------------------
# Domain model — what the calling system stores / serves
# -----------------------------------------------------------------------------

ChunkType = Literal["text", "title", "table", "equation", "image", "code"]


@dataclasses.dataclass(frozen=True)
class Chunk:
    """One atomic unit of retrievable content, with provenance."""
    chunk_id: str               # e.g. f"{doc_id}-{ordinal:05d}"
    section_path: tuple[str, ...]   # e.g. ("Results", "Statistical methods")
    chunk_type: ChunkType
    text: str                   # plain text (or markdown for tables/equations)
    page_idx: int | None        # 0-based PDF page
    html: str | None = None     # original HTML for tables / inline math
    image_name: str | None = None  # filename within the parsed bundle


@dataclasses.dataclass(frozen=True)
class Section:
    title: str
    level: int                  # 1 = top-level, 2 = subsection, ...
    page_idx: int | None
    chunk_ids: tuple[str, ...]  # references into ParsedDocument.chunks


@dataclasses.dataclass(frozen=True)
class ParsedDocument:
    """Output of any ParserAdapter. The retrieval/index layer reads from this."""
    artifact_id: str
    chunks: tuple[Chunk, ...]
    sections: tuple[Section, ...]
    page_count: int
    parser: str                 # e.g. "mineru@2.5.0"
    parser_elapsed_seconds: float

    @property
    def normalized_markdown(self) -> str:
        """Concatenated text, suitable for full-text search / embedding."""
        return "\n\n".join(c.text for c in self.chunks if c.chunk_type != "image")


# -----------------------------------------------------------------------------
# Adapter interface
# -----------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Artifact:
    """Whatever the calling system tracks per document: the actual bytes to parse,
    plus identity / language hints. The adapter doesn't need to know how the
    artifact was obtained or where it's stored."""
    artifact_id: str            # opaque to the adapter; used to namespace chunk ids
    presigned_url: str | None = None
    inline_bytes_b64: str | None = None
    volume_path: str | None = None
    lang: str = "en"


class ParserAdapter(ABC):
    """One implementation per parsing backend (mineru, others, …)."""

    @abstractmethod
    def parse(self, artifact: Artifact) -> ParsedDocument: ...


# -----------------------------------------------------------------------------
# MinerU adapter
# -----------------------------------------------------------------------------

class MineruParserAdapter(ParserAdapter):
    """Wraps the runpod-mineru service. Constructs ParsedDocument from MinerU's
    `content_list_v2.json` entries plus its inline images."""

    def __init__(self, *, endpoint_id: str, api_key: str | None = None) -> None:
        self._client = MineruClient(endpoint_id=endpoint_id, api_key=api_key)

    def parse(self, artifact: Artifact) -> ParsedDocument:
        result = self._client.parse_pdf(
            pdf_url=artifact.presigned_url,
            pdf_b64=artifact.inline_bytes_b64,
            volume_path=artifact.volume_path,
            lang=artifact.lang,
            return_format="inline",   # we want structured data, not a tarball
            basename=artifact.artifact_id,
        )
        return _to_parsed_document(result, artifact)


# -----------------------------------------------------------------------------
# MinerU content_list → ParsedDocument
# -----------------------------------------------------------------------------

def _to_parsed_document(result: dict[str, Any], artifact: Artifact) -> ParsedDocument:
    content_list: list[dict] = result.get("content_list") or []

    chunks: list[Chunk] = []
    sections: list[Section] = []
    section_stack: list[Section] = []     # current heading hierarchy
    chunks_by_section: dict[int, list[str]] = {}  # section index → chunk_ids
    pages_seen: set[int] = set()

    for ordinal, entry in enumerate(content_list):
        if not isinstance(entry, dict):
            continue
        et = entry.get("type")
        page_idx = entry.get("page_idx")
        if isinstance(page_idx, int):
            pages_seen.add(page_idx)

        chunk_id = f"{artifact.artifact_id}-{ordinal:05d}"

        if et == "text" and str(entry.get("level", "")).lower() == "title":
            title = _strip_html(entry.get("text") or "")
            level = _heading_level(title)
            section = Section(
                title=title,
                level=level,
                page_idx=page_idx if isinstance(page_idx, int) else None,
                chunk_ids=(),
            )
            # Adjust the stack so the new section nests under the right parent.
            while section_stack and section_stack[-1].level >= level:
                section_stack.pop()
            section_stack.append(section)
            sections.append(section)
            chunks_by_section[len(sections) - 1] = []
            chunks.append(Chunk(
                chunk_id=chunk_id,
                section_path=tuple(s.title for s in section_stack),
                chunk_type="title",
                text=title,
                page_idx=page_idx if isinstance(page_idx, int) else None,
            ))
            chunks_by_section[len(sections) - 1].append(chunk_id)
            continue

        chunk_type, text, html, image_name = _classify_entry(entry)
        if not text and not html and not image_name:
            continue

        chunk = Chunk(
            chunk_id=chunk_id,
            section_path=tuple(s.title for s in section_stack),
            chunk_type=chunk_type,
            text=text,
            page_idx=page_idx if isinstance(page_idx, int) else None,
            html=html,
            image_name=image_name,
        )
        chunks.append(chunk)
        if sections:
            chunks_by_section.setdefault(len(sections) - 1, []).append(chunk_id)

    # Replace each Section's empty chunk_ids tuple with the real one.
    sections_out: list[Section] = []
    for idx, sec in enumerate(sections):
        ids = tuple(chunks_by_section.get(idx, []))
        sections_out.append(dataclasses.replace(sec, chunk_ids=ids))

    return ParsedDocument(
        artifact_id=artifact.artifact_id,
        chunks=tuple(chunks),
        sections=tuple(sections_out),
        page_count=max(pages_seen) + 1 if pages_seen else 0,
        parser=f"mineru@{result.get('mineru_version', 'unknown')}",
        parser_elapsed_seconds=float(result.get("elapsed_seconds") or 0.0),
    )


def _classify_entry(entry: dict) -> tuple[ChunkType, str, str | None, str | None]:
    et = entry.get("type")
    text = _strip_html(entry.get("text") or "")
    if et == "text":
        return "text", text, None, None
    if et == "equation":
        # MinerU emits LaTeX in `text` (often wrapped in $...$).
        return "equation", text or _strip_html(entry.get("html") or ""), entry.get("html"), None
    if et == "table":
        html = entry.get("html") or ""
        return "table", _strip_html(html), html, None
    if et == "image":
        return "image", entry.get("caption") or "", None, entry.get("img_path") or None
    if et == "code":
        return "code", text, None, None
    # Unknown type — keep as text so nothing is silently dropped.
    return "text", text, entry.get("html"), None


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _heading_level(title: str) -> int:
    """Guess a heading level from a numeric prefix (1.2.3 → 3, "Abstract" → 1)."""
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\s+", title)
    if not m:
        return 1
    return m.group(1).count(".") + 1


# -----------------------------------------------------------------------------
# Smoke test
# -----------------------------------------------------------------------------

def _main() -> int:
    if len(sys.argv) < 2:
        print("usage: parser_adapter_example.py <pdf_url>", file=sys.stderr)
        return 2

    adapter = MineruParserAdapter(
        endpoint_id=os.environ["RUNPOD_ENDPOINT_ID"],
        api_key=os.environ["RUNPOD_API_KEY"],
    )
    parsed = adapter.parse(Artifact(
        artifact_id="example-doc",
        presigned_url=sys.argv[1],
        lang="en",
    ))
    print(f"parser:    {parsed.parser}")
    print(f"elapsed:   {parsed.parser_elapsed_seconds}s")
    print(f"pages:     {parsed.page_count}")
    print(f"sections:  {len(parsed.sections)}")
    print(f"chunks:    {len(parsed.chunks)}")
    print(f"normalized markdown size: {len(parsed.normalized_markdown)} chars")
    if parsed.sections:
        print()
        print("First few sections:")
        for sec in parsed.sections[:8]:
            indent = "  " * (sec.level - 1)
            page = f"p.{sec.page_idx}" if sec.page_idx is not None else "p.?"
            print(f"  {indent}[{page}] {sec.title}  ({len(sec.chunk_ids)} chunks)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
