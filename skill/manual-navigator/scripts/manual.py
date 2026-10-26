#!/usr/bin/env python3
"""Navigate PDF manuals through their table of contents.

  toc  <folder>                 list the PDFs under a folder: pages, ToC status, title
  toc  <pdf> [--depth N]        print one PDF's ToC (bookmarks) with physical page numbers
  toc  <pdf> --write            replace the PDF's bookmarks with a ToC read from stdin
  toc  <pdf> --undo             remove what --write appended; the file is byte-identical again
  find <query> <pdf|folder>...  pages containing every term of the query, with ToC path

Page numbers are physical PDF pages counted from 1, never the numbers printed on the page.

ToC input for --write is one entry per line:  level | page | title
    1 | 3  | Safety precautions
    2 | 4  | Symbols used in this manual
    1 | 87 | Troubleshooting
Lines that are blank or start with # are ignored.

--write appends an incremental update to the PDF: the original bytes are left untouched,
which is what makes --undo possible. A PDF that cannot be updated this way (encrypted,
digitally signed, read-only) gets its ToC in a sidecar file <name>.toc.txt instead, and
`toc` reads that sidecar automatically.

Requires pypdf (pip install pypdf).
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
except ImportError:  # pragma: no cover
    sys.exit("manual.py needs pypdf:  pip install pypdf")

logging.getLogger("pypdf").setLevel(logging.ERROR)  # malformed-PDF chatter is not useful here

# A document this short is cheaper to read whole than to navigate.
SMALL_DOC_PAGES = 5
# Fewer characters than this on the first pages means there is no text layer (a scan).
SCANNED_CHECK_PAGES = 3
SCANNED_TEXT_CHARS = 50
# Above this many entries `toc` shows only the top two levels unless --depth is given.
TOC_AUTO_DEPTH_ENTRIES = 200
MAX_FIND_HITS = 30
SNIPPET_CHARS = 70

SIDECAR_SUFFIX = ".toc.txt"
# Info-dictionary key holding the file size before the first --write (used by --undo).
ORIGINAL_SIZE_KEY = "/ManualNavOriginalSize"

_TOC_LINE_RE = re.compile(r"^\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*$")
# Document-info titles that are authoring-tool noise rather than the manual's name.
_JUNK_TITLE_RE = re.compile(
    r"^(microsoft word\s*-|한글\s*-|adobe indesign)|untitled|^document$|^cover$|제목\s*없음"
    r"|\.(docx?|pdf|cdr|xlsx?|pptx?|hwp|png|jpe?g)$",
    re.IGNORECASE,
)

# Korean particles, longest first, so that "설정값을" searches as "설정값".
_JOSA = sorted(
    [
        "은", "는", "이", "가", "을", "를", "의", "에", "도", "만",
        "와", "과", "랑", "로", "으로", "에서", "에게", "한테",
        "보다", "부터", "까지", "처럼", "같이", "마다", "조차", "마저", "밖에",
        "이나", "이란", "에는", "에도", "와의", "과의",
        "로는", "로도", "으로는", "으로도", "만으로", "에서는", "에서도",
    ],
    key=len,
    reverse=True,
)
_MIN_STEM_LENGTH = 2


class CannotWrite(Exception):
    """The PDF itself cannot take an incremental update."""


# ─── PDF reading ─────────────────────────────────────────────────────────────


def open_pdf(path: Path) -> PdfReader:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        # Most "protected" manuals only restrict editing/printing and open with an empty password.
        try:
            reader.decrypt("")
        except Exception as exc:  # missing crypto backend or a real password
            raise SystemExit(f"{path.name}: encrypted PDF could not be opened ({exc})") from exc
    return reader


def page_text(reader: PdfReader, index: int) -> str:
    try:
        return reader.pages[index].extract_text() or ""
    except Exception:
        return ""


def is_scanned(reader: PdfReader) -> bool:
    """True when the first pages carry almost no text, i.e. the PDF is page images."""
    pages = min(SCANNED_CHECK_PAGES, len(reader.pages))
    text = "".join(page_text(reader, i) for i in range(pages))
    return len(text.strip()) < SCANNED_TEXT_CHARS


def page_labels(reader: PdfReader) -> list[str] | None:
    """Printed page labels, or None when they are just the physical numbers."""
    try:
        labels = list(reader.page_labels)
    except Exception:
        return None
    if all(label == str(i + 1) for i, label in enumerate(labels)):
        return None
    return labels


def read_bookmarks(reader: PdfReader) -> list[dict]:
    """The PDF outline as [{"level", "title", "page"}]; page is None when the link is broken."""
    entries: list[dict] = []

    def walk(items, level):
        for item in items:
            if isinstance(item, list):  # children of the preceding item
                walk(item, level + 1)
                continue
            try:
                index = reader.get_destination_page_number(item)
            except Exception:
                index = None
            page = index + 1 if isinstance(index, int) and index >= 0 else None
            entries.append({"level": level, "title": str(item.title or "").strip(), "page": page})

    try:
        walk(reader.outline, 1)
    except Exception:
        return []
    return entries


def assess_toc(toc: list[dict], total_pages: int) -> tuple[str, str]:
    """("good" | "weak" | "none", reason). A weak ToC is too thin to navigate by."""
    if not toc:
        return "none", "no bookmarks"
    usable = [e for e in toc if e["page"] and e["title"]]
    if len(usable) < 0.8 * len(toc):
        return "weak", f"{len(toc) - len(usable)} of {len(toc)} bookmarks are broken"
    if total_pages > 100 and len(usable) < total_pages / 100:
        return "weak", f"only {len(usable)} entries for {total_pages} pages"
    levels = max(e["level"] for e in usable)
    if levels == 1 and len(usable) < 20:
        return "weak", f"only {len(usable)} top-level entries"
    pages = {e["page"] for e in usable}
    if len(usable) > 1 and len(pages) == 1:
        return "weak", "every bookmark points to the same page"
    if total_pages > 20 and max(pages) < total_pages * 0.5:
        return "weak", f"bookmarks stop at p.{max(pages)} of {total_pages}"
    return "good", f"{len(usable)} entries, {levels} levels"


def sidecar_path(pdf: Path) -> Path:
    return pdf.with_name(pdf.stem + SIDECAR_SUFFIX)


def load_toc(pdf: Path, reader: PdfReader) -> tuple[list[dict], str, str, str]:
    """(toc, source, status, reason). A sidecar wins only over weak or missing bookmarks."""
    total = len(reader.pages)
    toc = read_bookmarks(reader)
    status, reason = assess_toc(toc, total)
    source = "bookmarks"
    side = sidecar_path(pdf)
    if status != "good" and side.exists():
        side_toc = parse_toc_lines(side.read_text(encoding="utf-8"), total)
        toc, source = side_toc, f"sidecar {side.name}"
        status, reason = assess_toc(toc, total)
    return toc, source, status, reason


def breadcrumb(toc: list[dict], page: int) -> str:
    """ToC path of a page, e.g. "8 Troubleshooting > 8.2 Alarm list".

    Takes the nearest entry at or before the page on each level, top-down, and stops
    when a deeper entry starts before its parent (it belongs to an earlier chapter).
    """
    nearest: dict[int, tuple[int, str]] = {}
    for entry in toc:
        entry_page = entry.get("page")
        title = entry.get("title")
        if not entry_page or entry_page > page or not title:
            continue
        found = nearest.get(entry["level"])
        if found is None or entry_page >= found[0]:
            nearest[entry["level"]] = (entry_page, title)

    parts: list[str] = []
    last_page = 0
    for level in sorted(nearest):
        entry_page, title = nearest[level]
        if entry_page < last_page:
            break
        parts.append(title)
        last_page = entry_page
    return " > ".join(parts)


def breadcrumb_at(toc: list[dict], page: int, text: str, position: int) -> str:
    """Like breadcrumb(), but when several sections start on this page, picks the one
    whose heading appears last before `position` in the page's normalized text."""
    chosen = None
    best = -1
    for index, entry in enumerate(toc):
        if entry.get("page") != page or not entry.get("title"):
            continue
        found = text.find(normalize(entry["title"]))
        if 0 <= found <= position and found >= best:
            chosen, best = index, found
    if chosen is not None:
        return breadcrumb(toc[: chosen + 1], page)
    # The match sits above every heading on this page: it continues an earlier section.
    return breadcrumb([e for e in toc if (e.get("page") or 0) < page], page)


def pdf_title(reader: PdfReader) -> str:
    try:
        title = str((reader.metadata or {}).get("/Title") or "").strip()
    except Exception:
        title = ""
    if _JUNK_TITLE_RE.search(title):
        title = ""
    if not title and len(reader.pages):
        lines = [l.strip() for l in page_text(reader, 0).splitlines() if l.strip()]
        title = " ".join(lines[:2])
    return title[:80]


# ─── toc ─────────────────────────────────────────────────────────────────────


def iter_pdfs(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*") if p.suffix.lower() == ".pdf"))
        elif path.suffix.lower() == ".pdf" and path.exists():
            found.append(path)
        else:
            sys.exit(f"not a PDF or folder: {raw}")
    return found


def toc_status_line(pdf: Path, reader: PdfReader) -> str:
    total = len(reader.pages)
    toc, source, status, reason = load_toc(pdf, reader)
    if total <= SMALL_DOC_PAGES:
        state = "small document, read it whole"
    elif status == "good":
        state = f"good ({source}, {reason})"
    else:
        state = f"{status} ({source}: {reason})" if source != "bookmarks" else f"{status} ({reason})"
        if is_scanned(reader):
            state += ", scanned: no text layer"
    return f"{total}p  ToC: {state}"


def cmd_toc_folder(folder: Path) -> None:
    pdfs = iter_pdfs([str(folder)])
    print(f"{len(pdfs)} PDF(s) under {folder}")
    for pdf in pdfs:
        reader = open_pdf(pdf)
        rel = pdf.relative_to(folder)
        print(f"- {rel}  |  {toc_status_line(pdf, reader)}  |  \"{pdf_title(reader)}\"")


def cmd_toc_show(pdf: Path, depth: int | None) -> None:
    reader = open_pdf(pdf)
    total = len(reader.pages)
    toc, source, status, reason = load_toc(pdf, reader)
    print(f"{pdf.name} — {toc_status_line(pdf, reader)}")

    labels = page_labels(reader)
    if labels:
        sample = next((i for i, l in enumerate(labels) if l != str(i + 1)), 0)
        print(f"Printed page labels differ from physical pages (e.g. p.{sample + 1} is printed \"{labels[sample]}\").")

    if total <= SMALL_DOC_PAGES and not toc:
        return
    if status != "good":
        print("This ToC is not enough to navigate by. Build one and save it with:")
        print(f"  manual.py toc \"{pdf}\" --write   (entries on stdin: level | page | title)")
        if not toc:
            return

    hidden = 0
    if depth is None and len(toc) > TOC_AUTO_DEPTH_ENTRIES:
        depth = 2
    for entry in toc:
        if depth is not None and entry["level"] > depth:
            hidden += 1
            continue
        page = f"p.{entry['page']}" if entry["page"] else "p.?"
        if labels and entry["page"]:
            page += f" ({labels[entry['page'] - 1]})"
        print(f"{'  ' * (entry['level'] - 1)}[{entry['level']}] {entry['title']} .... {page}")
    if hidden:
        print(f"({hidden} deeper entries hidden; use --depth N to show them)")


# ─── toc --write / --undo ────────────────────────────────────────────────────


def parse_toc_lines(text: str, total_pages: int) -> list[dict]:
    entries: list[dict] = []
    errors: list[str] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _TOC_LINE_RE.match(raw)
        if not match:
            errors.append(f"line {number}: expected 'level | page | title', got {raw.strip()!r}")
            continue
        level, page, title = int(match[1]), int(match[2]), match[3]
        previous = entries[-1]["level"] if entries else 0
        if level < 1 or level > previous + 1:
            errors.append(f"line {number}: level {level} cannot follow level {previous}")
        if not 1 <= page <= total_pages:
            errors.append(f"line {number}: page {page} is outside 1..{total_pages}")
        if not title:
            errors.append(f"line {number}: empty title")
        entries.append({"level": level, "title": title, "page": page})
    if not entries and not errors:
        errors.append("no ToC entries given")
    if errors:
        raise ValueError("\n".join(errors))
    return entries


def _is_signed(reader: PdfReader) -> bool:
    try:
        form = reader.trailer["/Root"].get("/AcroForm")
        return bool(form) and int(form.get_object().get("/SigFlags", 0)) & 1 == 1
    except Exception:
        return False


def _original_size(reader: PdfReader) -> int | None:
    try:
        value = (reader.metadata or {}).get(ORIGINAL_SIZE_KEY)
        return int(value) if value is not None else None
    except Exception:
        return None


def _outline_signature(data: bytes) -> list[tuple]:
    reader = PdfReader(io.BytesIO(data), strict=True)
    return [(e["level"], e["title"], e["page"]) for e in read_bookmarks(reader)]


def write_bookmarks(pdf: Path, toc: list[dict]) -> int:
    """Append an incremental update that replaces the outline. Returns bytes appended."""
    original = pdf.read_bytes()
    reader = PdfReader(io.BytesIO(original))
    if reader.is_encrypted:
        raise CannotWrite("the PDF is encrypted")
    if _is_signed(reader):
        raise CannotWrite("the PDF is digitally signed")
    if not os.access(pdf, os.W_OK):
        raise CannotWrite("the file is read-only")

    writer = PdfWriter(io.BytesIO(original), incremental=True)
    # pypdf 6 numbers new objects after the highest one it found in the xref, which can
    # collide with an earlier update's xref-stream object and corrupt the file on the
    # second --write. Start new objects after the trailer's /Size instead. The result is
    # verified below either way, so a pypdf change here fails safe instead of corrupting.
    try:
        size = int(writer._reader.trailer["/Size"])
        if len(writer._objects) < size - 1:
            writer._objects.extend([None] * (size - 1 - len(writer._objects)))
    except Exception:
        pass

    writer._root_object.pop(NameObject("/Outlines"), None)
    parents: dict[int, object] = {}
    for entry in toc:
        parents[entry["level"]] = writer.add_outline_item(
            entry["title"], entry["page"] - 1, parent=parents.get(entry["level"] - 1)
        )
    writer.add_metadata({ORIGINAL_SIZE_KEY: str(_original_size(reader) or len(original))})

    buffer = io.BytesIO()
    writer.write(buffer)
    updated = buffer.getvalue()
    if not updated.startswith(original):
        raise CannotWrite("pypdf rewrote the original bytes instead of appending")
    expected = [(e["level"], e["title"], e["page"]) for e in toc]
    if _outline_signature(updated) != expected:
        raise CannotWrite("the updated PDF did not read back with the new ToC")

    try:
        with open(pdf, "ab") as handle:  # only the new bytes touch the file
            handle.write(updated[len(original):])
    except OSError as exc:
        raise CannotWrite(f"could not write the file ({exc.strerror}); is it open in a viewer?") from exc
    return len(updated) - len(original)


def cmd_toc_write(pdf: Path) -> None:
    reader = open_pdf(pdf)
    try:
        toc = parse_toc_lines(sys.stdin.read(), len(reader.pages))
    except ValueError as exc:
        sys.exit(f"ToC not saved:\n{exc}")
    try:
        added = write_bookmarks(pdf, toc)
        print(f"Saved {len(toc)} bookmarks into {pdf.name} (+{added} bytes; undo with --undo).")
    except CannotWrite as exc:
        side = sidecar_path(pdf)
        lines = [f"# ToC for {pdf.name} (physical pages). Read automatically by manual.py toc."]
        lines += [f"{e['level']} | {e['page']} | {e['title']}" for e in toc]
        side.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Could not update the PDF ({exc}); saved the ToC to {side.name} instead.")


def cmd_toc_undo(pdf: Path) -> None:
    data = pdf.read_bytes()
    base = _original_size(PdfReader(io.BytesIO(data)))
    if base is None:
        side = sidecar_path(pdf)
        if side.exists():
            side.unlink()
            print(f"Removed {side.name}.")
            return
        sys.exit(f"{pdf.name} has no ToC written by this tool.")
    original = data[:base]
    if not 0 < base < len(data) or not original.rstrip().endswith(b"%%EOF"):
        sys.exit("The file changed after the ToC was written; refusing to cut it.")
    try:
        if _original_size(PdfReader(io.BytesIO(original), strict=True)) is not None:
            raise ValueError
    except Exception:
        sys.exit("The original revision does not read cleanly; refusing to cut it.")
    os.truncate(pdf, base)
    print(f"Restored {pdf.name} to its original {base} bytes.")


# ─── find ────────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    """Full-width → ASCII, lower case, whitespace collapsed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).lower()


def strip_josa(token: str) -> str:
    if not token or not ("가" <= token[-1] <= "힣"):
        return token
    for josa in _JOSA:
        if token.endswith(josa) and len(token) - len(josa) >= _MIN_STEM_LENGTH:
            return token[: -len(josa)]
    return token


def term_pattern(term: str) -> re.Pattern:
    """Codes match across separators but not inside longer codes.

    "AL.21" matches "AL21", "AL-21", "al 21" and the sub-code "AL.21.1", but not "AL.210"
    or "XAL21". Plain words match as substrings, Korean ones without their particle.
    """
    term = normalize(term).strip()
    if any(c.isdigit() for c in term):
        chunks = re.findall(r"[a-z]+|\d+|[가-힣]+", term)
        body = r"[\s\-._:/]*".join(re.escape(c) for c in chunks)
        head = r"(?<!\d)" if chunks[0][0].isdigit() else r"(?<![a-z])"
        tail = r"(?!\d)" if chunks[-1][-1].isdigit() else r"(?![a-z])"
        return re.compile(head + body + tail)
    return re.compile(re.escape(strip_josa(term)))


def snippet(text: str, match: re.Match) -> str:
    start = max(0, match.start() - SNIPPET_CHARS)
    end = min(len(text), match.end() + SNIPPET_CHARS)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def cmd_find(query: str, paths: list[str], max_hits: int) -> None:
    terms = [t for t in query.split() if t.strip()]
    if not terms:
        sys.exit("empty query")
    patterns = [term_pattern(t) for t in terms]
    shown = 0
    total_hits = 0
    for pdf in iter_pdfs(paths):
        reader = open_pdf(pdf)
        toc, _source, _status, _reason = load_toc(pdf, reader)
        labels = page_labels(reader)

        toc_hits = [e for e in toc if all(p.search(normalize(e["title"])) for p in patterns)]
        phrase = re.compile(r"\s*".join(re.escape(c) for c in normalize(query).split()))
        page_hits: list[tuple[int, int, str, str]] = []  # (rank, page, path, snippet)
        term_counts = [0] * len(patterns)
        for index in range(len(reader.pages)):
            # Same length as the normalized text, so match positions carry over to the snippet.
            flat = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", page_text(reader, index)))
            text = flat.lower()
            matches = [p.search(text) for p in patterns]
            for i, found in enumerate(matches):
                term_counts[i] += bool(found)
            if all(matches):
                # Pages with the query as a phrase first, then by how often the terms occur.
                whole = phrase.search(text) if len(terms) > 1 else matches[0]
                anchor = whole or matches[0]
                occurrences = sum(len(p.findall(text)) for p in patterns)
                rank = (0 if whole else 1, -occurrences)
                path = breadcrumb_at(toc, index + 1, text, anchor.start())
                page_hits.append((rank, index + 1, path, snippet(flat, anchor)))

        if not page_hits and not toc_hits:
            if is_scanned(reader):
                print(f"== {pdf.name}: scanned, no text layer — search its ToC or look at the pages ==")
            elif len(terms) > 1 and any(term_counts):
                counts = ", ".join(f"'{t}': {n}" for t, n in zip(terms, term_counts))
                print(f"== {pdf.name}: no page has every term; pages per term — {counts} ==")
            continue
        print(f"== {pdf.name} ({len(reader.pages)} pages) ==")
        for entry in toc_hits:
            print(f"ToC: [{entry['level']}] {entry['title']} .... p.{entry['page']}")
        for _rank, page, path, text in sorted(page_hits):
            total_hits += 1
            if shown >= max_hits:
                continue
            shown += 1
            label = f" (printed {labels[page - 1]})" if labels else ""
            print(f"p.{page}{label}" + (f" [{path}]" if path else "") + f"  {text}")
        if len(terms) > 1 and not page_hits:
            counts = ", ".join(f"'{t}': {n}" for t, n in zip(terms, term_counts))
            print(f"(no page has every term; pages per term — {counts})")
    if total_hits > shown:
        print(f"... {total_hits - shown} more matching pages not shown; narrow the query or the files.")
    if total_hits == 0:
        print("No page matched.")


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    toc = sub.add_parser("toc", help="show, write or undo a ToC; list a folder")
    toc.add_argument("path")
    mode = toc.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="replace bookmarks with the ToC on stdin")
    mode.add_argument("--undo", action="store_true", help="remove what --write added")
    toc.add_argument("--depth", type=int, help="show levels up to N")

    find = sub.add_parser("find", help="search page text")
    find.add_argument("query")
    find.add_argument("paths", nargs="+")
    find.add_argument("--max", type=int, default=MAX_FIND_HITS, help="max pages to show")

    args = parser.parse_args(argv)
    if args.command == "toc":
        path = Path(args.path)
        if path.is_dir():
            cmd_toc_folder(path)
        elif not path.exists() or path.suffix.lower() != ".pdf":
            sys.exit(f"not a PDF or folder: {path}")
        elif args.write:
            cmd_toc_write(path)
        elif args.undo:
            cmd_toc_undo(path)
        else:
            cmd_toc_show(path, args.depth)
    else:
        cmd_find(args.query, args.paths, args.max)


if __name__ == "__main__":
    main()
