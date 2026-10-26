# Building a ToC for a manual that has none

Read this when `manual.py toc` reports a manual's ToC as `weak` or `none` and you need to
navigate it. Most manuals print a table of contents near the front even when the PDF has
no bookmarks, so the job is usually to transcribe that page and fix the page numbers.

## 1. Find the printed contents pages

- Text PDF: `manual.py find "목차" <pdf>` (or `contents`, `table of contents`, `目次`). The
  hit in the first ~15 pages is usually it.
- Scan, or no hit: look at the first ~10 pages (cheap, low-resolution views are enough to
  spot a contents page), then open the contents pages at a readable resolution.
- Contents pages can run long (5-10 pages in big manuals). Capturing chapters and their
  sections (two levels) is normally enough to navigate; skip deeper levels unless the
  question needs them.

## 2. Transcribe

Write one entry per line in the format `--write` takes:

```
level | page | title
1 | 3  | 1 안전 주의사항
2 | 4  | 1.1 표시 기호
1 | 12 | 2 설치
```

Use the numbering to decide the level ("3" → 1, "3.4" → 2, "3.4.1" → 3). Keep titles as
printed, including their numbers; they are what `find` and the user will recognize.

## 3. Convert printed page numbers to physical pages

Do not skip this step: a ToC that is off by a few pages sends every later lookup to the
wrong place. A printed ToC lists printed numbers, and they rarely equal physical ones:

- **Constant offset**: covers and front matter are not counted, so physical = printed +
  offset. Find the offset from one entry: `find` its title (text PDFs) or open the page
  where you expect it and adjust until the heading is there.
- **Roman front matter** (i, ii, iii...) followed by 1, 2, 3...: the offset is the number of
  front-matter pages; check it on the first chapter.
- **Chapter-page numbering** ("3-12" = page 12 of chapter 3): there is no single offset.
  Find where each chapter starts physically (its title via `find`, or by checking pages),
  then physical = chapter start + (n - 1). Never treat "3-12" as page 12.

Then verify two more entries, one in the middle and one near the end, by checking that
the heading is on the physical page you computed. If the offset drifts, the PDF has inserted
or missing pages; fix the entries after the drift.

## 4. No printed contents at all

- Text PDF: navigate with `find` on the user's keywords; it does not need a ToC. If you
  want a ToC anyway, look at pages at regular intervals and note where chapters begin.
- Scan with no contents: open pages at intervals (every 10-20 pages) at low resolution to
  map chapter starts, then refine near the part you need. A coarse ToC of chapter starts
  is still worth saving: next time it saves the whole search.

## 5. Use it, then offer to save it

Answer the user's question with the ToC you built, then offer to save it into the PDF
(see "Saving a ToC you built" in SKILL.md). With their okay:

```
python scripts/manual.py toc "<pdf>" --write <<'EOF'
1 | 4  | 1 안전 주의사항
...
EOF
```

`--write` checks the entries (levels that skip, pages outside the document, empty titles)
and refuses the whole ToC if any are wrong, listing each problem. Fix them and run it
again. It replaces whatever bookmarks the PDF had, and `toc <pdf>` shows the result.
