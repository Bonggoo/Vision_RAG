"""Tests for manual-navigator/scripts/manual.py against the generated sample library.

    pip install pypdf reportlab pillow pytest
    pytest skill/tests
"""
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

SKILL = Path(__file__).resolve().parents[1] / "manual-navigator"
sys.path.insert(0, str(SKILL / "scripts"))
import manual  # noqa: E402

AS200 = "Acme_AS200_서보앰프_사용설명서.pdf"
AS100 = "Acme_AS100_Servo_Manual_v3.pdf"
INSTALL = "AS200_설치가이드.pdf"
SCAN = "GX7_inverter_scan.pdf"
IT300 = "IT300_manual.pdf"


@pytest.fixture(scope="session")
def library(tmp_path_factory):
    out = tmp_path_factory.mktemp("lib")
    truth = out / "truth.json"
    subprocess.run(
        [sys.executable, str(SKILL / "evals" / "make_samples.py"), str(out / "manuals"),
         "--truth", str(truth), "--scale", "1"],
        check=True, capture_output=True,
    )
    return out / "manuals", json.loads(truth.read_text(encoding="utf-8"))


def run(capsys, *argv, stdin=None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    manual.main([str(a) for a in argv])
    return capsys.readouterr().out


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ─── toc ─────────────────────────────────────────────────────────────────────


def test_folder_listing_reports_each_toc_state(library, capsys):
    folder, _ = library
    out = run(capsys, "toc", folder)
    lines = {line.split("  |  ")[0][2:]: line for line in out.splitlines() if line.startswith("- ")}
    assert "ToC: good" in lines[AS200]
    assert "ToC: none" in lines[INSTALL]
    assert "ToC: weak" in lines[IT300]
    assert "scanned" in lines[SCAN]
    assert "untitled" not in lines[AS100]  # authoring-tool title replaced by cover text


def test_toc_shows_printed_labels_next_to_physical_pages(library, capsys):
    folder, truth = library
    out = run(capsys, "toc", folder / AS200)
    homing = truth["as200_homing"]
    assert "Printed page labels differ" in out
    assert f"5.3 원점복귀 .... p.{homing['page']} ({homing['printed_label']})" in out


def test_weak_toc_tells_how_to_fix_it(library, capsys):
    folder, _ = library
    out = run(capsys, "toc", folder / IT300)
    assert "not enough to navigate by" in out and "--write" in out


# ─── find ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text, hit", [
    ("al21", True), ("al-21", True), ("al 21", True), ("al.21.1", True), ("al.21:", True),
    ("al.210", False), ("xal21", False), ("al.e21", False), ("121", False),
])
def test_code_terms_match_across_separators_but_not_inside_longer_codes(text, hit):
    assert bool(manual.term_pattern("AL.21").search(text)) is hit


def test_full_width_query_matches_ascii_text():
    assert manual.term_pattern("ＡＬ．２１").search(manual.normalize("AL.21 엔코더"))


@pytest.mark.parametrize("word, stem", [("설정값을", "설정값"), ("회생저항은", "회생저항"), ("차이", "차이"), ("AL.21", "AL.21")])
def test_strip_josa(word, stem):
    assert manual.strip_josa(word) == stem


def test_find_lands_on_the_alarm_section_with_its_toc_path(library, capsys):
    folder, truth = library
    page = truth["as200_al21_detail"]["page"]
    out = run(capsys, "find", "AL.21", folder / AS200)
    line = next(l for l in out.splitlines() if l.startswith(f"p.{page} "))
    assert "> AL.21 엔코더 통신 이상]" in line


def test_find_across_folder_reports_scans_it_cannot_search(library, capsys):
    folder, truth = library
    out = run(capsys, "find", "2051", folder)
    assert f"p.{truth['mc500_2051_detail']['page']}" in out
    assert f"{SCAN}: scanned, no text layer" in out


def test_find_needs_every_term_and_says_which_were_missing(library, capsys):
    folder, _ = library
    out = run(capsys, "find", "AL.21 존재하지않는말", folder / AS200)
    assert "no page has every term" in out


# ─── toc --write / --undo ────────────────────────────────────────────────────

GOOD_TOC = "1 | 4 | 1 안전\n2 | 5 | 1.1 표시\n1 | 8 | 2 개요\n"


def test_write_then_rewrite_then_undo_restores_original_bytes(library, tmp_path, capsys, monkeypatch):
    folder, _ = library
    pdf = tmp_path / IT300
    shutil.copy(folder / IT300, pdf)
    original = sha(pdf)

    out = run(capsys, "toc", pdf, "--write", stdin=GOOD_TOC, monkeypatch=monkeypatch)
    assert "Saved 3 bookmarks" in out
    # A second write stacks a second incremental update; pypdf used to corrupt this case.
    run(capsys, "toc", pdf, "--write", stdin=GOOD_TOC + "1 | 9 | 3 설치\n", monkeypatch=monkeypatch)
    reader = PdfReader(str(pdf), strict=True)
    assert [(e["level"], e["title"], e["page"]) for e in manual.read_bookmarks(reader)][-1] == (1, "3 설치", 9)

    out = run(capsys, "toc", pdf, "--undo")
    assert "Restored" in out
    assert sha(pdf) == original


def test_write_rejects_invalid_toc_and_leaves_file_alone(library, tmp_path, capsys, monkeypatch):
    folder, _ = library
    pdf = tmp_path / IT300
    shutil.copy(folder / IT300, pdf)
    original = sha(pdf)
    with pytest.raises(SystemExit) as exc:
        run(capsys, "toc", pdf, "--write", stdin="1 | 4 | ok\n3 | 9999 | bad\n|x|\n", monkeypatch=monkeypatch)
    message = str(exc.value)
    assert "level 3 cannot follow level 1" in message
    assert "outside 1.." in message
    assert "expected 'level | page | title'" in message
    assert sha(pdf) == original


def test_encrypted_pdf_gets_a_sidecar_that_toc_reads(library, tmp_path, capsys, monkeypatch):
    folder, _ = library
    pdf = tmp_path / "locked.pdf"
    writer = PdfWriter(clone_from=str(folder / IT300))
    writer.encrypt(user_password="", owner_password="owner")
    writer.write(str(pdf))
    original = sha(pdf)

    out = run(capsys, "toc", pdf, "--write", stdin=GOOD_TOC, monkeypatch=monkeypatch)
    assert "saved the ToC to locked.toc.txt" in out
    assert sha(pdf) == original
    assert "sidecar locked.toc.txt" in run(capsys, "toc", pdf)

    run(capsys, "toc", pdf, "--undo")
    assert not (tmp_path / "locked.toc.txt").exists()


# ─── pure functions ──────────────────────────────────────────────────────────


def test_breadcrumb_stops_at_a_section_from_an_earlier_chapter():
    toc = [
        {"level": 1, "title": "2 설치", "page": 10},
        {"level": 2, "title": "2.3 배선", "page": 14},
        {"level": 1, "title": "3 운전", "page": 20},
    ]
    assert manual.breadcrumb(toc, 15) == "2 설치 > 2.3 배선"
    assert manual.breadcrumb(toc, 22) == "3 운전"


@pytest.mark.parametrize("toc, pages, status", [
    ([], 50, "none"),
    ([{"level": 1, "title": f"c{i}", "page": None} for i in range(30)], 300, "weak"),
    ([{"level": 1, "title": f"c{i}", "page": 1} for i in range(30)], 300, "weak"),
    ([{"level": 1, "title": f"c{i}", "page": i + 1} for i in range(30)], 300, "weak"),  # stops at p.30
    ([{"level": 1, "title": "a", "page": 1}, {"level": 2, "title": "b", "page": 40}], 60, "good"),
])
def test_assess_toc(toc, pages, status):
    assert manual.assess_toc(toc, pages)[0] == status
