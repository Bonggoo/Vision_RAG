#!/usr/bin/env python3
"""Generate a fictional manual library for testing manual-navigator.

    python make_samples.py <out_dir> [--truth ground_truth.json]

Every brand and product here is made up (Acme, Globex, Initech). The library mixes the
cases the skill has to handle:

  Acme_AS200_서보앰프_사용설명서.pdf   good 3-level bookmarks, roman/chapter-page labels
  Acme_AS100_Servo_Manual_v3.pdf      older model: AL.21 means something else here
  Acme_MC500_모션컨트롤러_매뉴얼.pdf    upstream controller: owns error code 2051
  AS200_설치가이드.pdf                 no bookmarks, printed ToC, pin table only as an image
  GX7_inverter_scan.pdf               image-only scan, printed ToC
  IT300_manual.pdf                    weak bookmarks (3 entries), printed ToC

--truth writes the physical page of each fact the evals ask about. Keep it outside the
library folder so an agent under test cannot read it.

Needs reportlab, pypdf, Pillow and pdftoppm (poppler) for the scanned manual, plus a font
with Hangul glyphs (found automatically, or set MANUAL_SAMPLE_FONT).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "C:/Windows/Fonts/malgun.ttf",
]
WIDTH, HEIGHT = A4
LEFT, RIGHT, TOP, BOTTOM = 56, WIDTH - 56, HEIGHT - 64, 64


def find_font() -> str:
    env = os.environ.get("MANUAL_SAMPLE_FONT")
    for path in ([env] if env else []) + FONT_CANDIDATES:
        if path and Path(path).exists():
            return path
    sys.exit("No font with Hangul glyphs found; set MANUAL_SAMPLE_FONT to a .ttf/.ttc file.")


def register_font(path: str) -> None:
    kwargs = {"subfontIndex": 0} if path.lower().endswith(".ttc") else {}
    pdfmetrics.registerFont(TTFont("KR", path, **kwargs))


# ─── tiny layout engine ──────────────────────────────────────────────────────


class Manual:
    """Line-based page layout that knows which physical page everything lands on."""

    def __init__(self, path: Path, label_style: str = "plain", bookmarks: str = "full"):
        self.path = path
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.page = 1
        self.y = TOP
        self.label_style = label_style   # plain | minus_cover | roman_front
        self.bookmarks = bookmarks       # full | none | custom
        self.chapter = 0
        self.front_pages = 0
        self.chapter_starts: dict[int, int] = {}
        self.toc: list[tuple[int, str, int]] = []
        self.marks: dict[str, int] = {}
        self._bm = 0

    # labels printed in the footer
    def label(self, page: int) -> str:
        if self.label_style == "minus_cover":
            return "" if page == 1 else str(page - 1)
        if self.label_style == "roman_front":
            if page <= self.front_pages or not self.chapter:
                return roman(page)
            return f"{self.chapter}-{page - self.chapter_starts[self.chapter] + 1}"
        return str(page)

    def _footer(self) -> None:
        text = self.label(self.page)
        if text:
            self.c.setFont("KR", 9)
            self.c.drawCentredString(WIDTH / 2, 36, text)

    def new_page(self) -> None:
        self._footer()
        self.c.showPage()
        self.page += 1
        self.y = TOP

    def ensure(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.new_page()

    def fresh_page(self) -> None:
        if self.y != TOP:
            self.new_page()

    def mark(self, key: str) -> None:
        self.marks[key] = self.page

    def heading(self, text: str, level: int, bookmark: bool = True) -> None:
        size = {1: 17, 2: 13, 3: 11}[level]
        if level == 1:
            self.fresh_page()
        self.ensure(size * 2.4)
        self.y -= size * 0.6
        self.c.setFont("KR", size)
        self.c.drawString(LEFT, self.y, text)
        self.y -= size * 1.5
        self.toc.append((level, text, self.page))
        if bookmark and self.bookmarks == "full":
            key = f"b{self._bm}"
            self._bm += 1
            self.c.bookmarkPage(key, fit="XYZ", top=self.y + size * 2, left=0, zoom=0)
            self.c.addOutlineEntry(text, key, level=level - 1)

    def chapter_heading(self, number: int, title: str) -> None:
        self.fresh_page()
        self.chapter = number
        self.chapter_starts[number] = self.page
        self.heading(f"{number} {title}", 1)

    def para(self, text: str, size: float = 10, indent: float = 0) -> None:
        for line in wrap(text, RIGHT - LEFT - indent, size):
            self.ensure(size * 1.55)
            self.c.setFont("KR", size)
            self.c.drawString(LEFT + indent, self.y, line)
            self.y -= size * 1.55
        self.y -= size * 0.5

    def table(self, header: list[str], rows: list[list[str]], widths: list[float], size: float = 9,
              row_marks: dict[int, str] | None = None) -> None:
        line_height = size * 1.7

        def draw_row(cells, bold=False):
            self.ensure(line_height)
            self.c.setFont("KR", size + (0.5 if bold else 0))
            x = LEFT
            for cell, width in zip(cells, widths):
                self.c.drawString(x + 3, self.y, fit(cell, width - 6, size))
                x += width
            self.c.line(LEFT, self.y - 4, LEFT + sum(widths), self.y - 4)
            self.y -= line_height

        draw_row(header, bold=True)
        start_page = self.page
        for index, row in enumerate(rows):
            draw_row(row)
            if self.page != start_page:  # repeat the header on a continued table
                start_page = self.page
                self.y += line_height
                self.c.setFillGray(1)
                self.c.rect(LEFT, self.y - 5, sum(widths), line_height, stroke=0, fill=1)
                self.c.setFillGray(0)
                draw_row(header, bold=True)
                draw_row(row)
            if row_marks and index in row_marks:
                self.mark(row_marks[index])
        self.y -= size

    def image(self, path: Path, width: float, height: float, caption: str) -> None:
        self.ensure(height + 30)
        self.c.drawImage(str(path), LEFT, self.y - height, width=width, height=height)
        self.y -= height + 16
        self.para(caption, size=9)

    def save(self) -> None:
        self._footer()
        self.c.showPage()
        self.c.save()


def roman(n: int) -> str:
    values = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for value, sym in values:
        while n >= value:
            out += sym
            n -= value
    return out


def wrap(text: str, width: float, size: float) -> list[str]:
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}".strip()
        if pdfmetrics.stringWidth(candidate, "KR", size) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit(text: str, width: float, size: float) -> str:
    while text and pdfmetrics.stringWidth(text, "KR", size) > width:
        text = text[:-1]
    return text


def set_labels(path: Path, manual: Manual) -> None:
    """Embed page labels that match the printed footers (roman front matter, chapter-page)."""
    writer = PdfWriter(clone_from=str(path))
    if manual.front_pages:
        writer.set_page_label(0, manual.front_pages - 1, style="/r")
    chapters = sorted(manual.chapter_starts.items())
    for i, (number, start) in enumerate(chapters):
        end = chapters[i + 1][1] - 1 if i + 1 < len(chapters) else manual.page
        writer.set_page_label(start - 1, end - 1, style="/D", prefix=f"{number}-", start=1)
    writer.write(str(path))


def printed_toc(m: Manual, entries: list[tuple[int, str, int]], offset: int) -> None:
    """Draw a printed ToC page listing printed page numbers (physical - offset)."""
    m.c.setFont("KR", 17)
    m.c.drawString(LEFT, m.y, "목차")
    m.y -= 34
    for level, title, page in entries:
        m.ensure(16)
        m.c.setFont("KR", 10.5 if level == 1 else 9.5)
        x = LEFT + (level - 1) * 16
        m.c.drawString(x, m.y, title)
        number = str(page - offset)
        m.c.drawRightString(RIGHT, m.y, number)
        dots_from = x + pdfmetrics.stringWidth(title, "KR", 10) + 6
        dots_to = RIGHT - pdfmetrics.stringWidth(number, "KR", 10) - 6
        if dots_to > dots_from:
            m.c.setFont("KR", 8)
            m.c.drawString(dots_from, m.y, "." * int((dots_to - dots_from) / 3.2))
        m.y -= 17 if level == 1 else 15


# ─── shared filler text ──────────────────────────────────────────────────────

SAFETY = [
    "감전 위험이 있으므로 주회로 전원을 차단하고 충전 램프가 꺼진 것을 확인한 뒤 10분 이상 지나서 배선 작업을 하십시오.",
    "보호 접지 단자는 반드시 접지 저항 100Ω 이하의 접지에 연결하십시오.",
    "젖은 손으로 스위치를 조작하지 마십시오. 감전의 원인이 됩니다.",
    "운전 중이나 전원 차단 직후에는 방열판과 회생저항이 고온이므로 만지지 마십시오.",
    "케이블에 무리한 힘을 가하거나 무거운 물체를 올려두지 마십시오.",
    "제품을 분해하거나 개조하지 마십시오. 고장이나 화재의 원인이 됩니다.",
    "비상 정지 회로는 제품 외부에 반드시 별도로 구성하십시오.",
    "정전 후 복전 시 갑자기 재기동할 수 있으므로 기계에 가까이 가지 마십시오.",
]
GENERIC = [
    "설정을 변경한 뒤에는 반드시 시운전으로 동작을 확인하십시오.",
    "주위 온도는 0~55℃, 상대 습도는 90%RH 이하(결로 없을 것)를 유지하십시오.",
    "진동이 큰 장소에 설치할 경우 방진 고무를 사용하십시오.",
    "통신 케이블은 동력선과 30cm 이상 떨어뜨려 배선하십시오.",
    "정기 점검 주기는 사용 환경에 따라 다르나 1년에 1회 이상을 권장합니다.",
    "본 장의 설정값은 출하 시 기본값을 기준으로 설명합니다.",
    "제어 신호 케이블은 트위스트 페어 실드선을 사용하고 실드는 한쪽 끝에서 접지하십시오.",
    "부하 관성비가 큰 경우 게인을 낮게 설정한 뒤 단계적으로 올리십시오.",
    "모니터 기능을 사용하면 운전 중 상태를 실시간으로 확인할 수 있습니다.",
    "외부 장치와의 인터록 회로를 반드시 구성하십시오.",
]


# Multiplies every filler block; the default makes manuals of a few hundred pages, long
# enough that reading one cover to cover is not a sensible strategy.
SCALE = 6


def filler(rng: random.Random, m: Manual, paragraphs: int) -> None:
    for _ in range(paragraphs * SCALE):
        m.para(" ".join(rng.sample(GENERIC, 3)))


# ─── Acme AS200 servo amplifier ──────────────────────────────────────────────

AS200_ALARMS = [
    ("AL.10", "부족 전압", "리셋 가능", "전원 전압 저하, 순간 정전", "전원 전압과 배선을 확인한다"),
    ("AL.12", "메모리 이상 1 (RAM)", "전원 재투입", "제어 기판 고장", "서보앰프를 교체한다"),
    ("AL.16", "엔코더 초기 통신 이상", "전원 재투입", "전원 투입 시 엔코더 응답 없음", "엔코더 케이블 연결을 확인한다"),
    ("AL.20", "모터 결선 이상", "전원 재투입", "U/V/W 결선 순서 오류", "모터 동력선 결선을 확인한다"),
    ("AL.21", "엔코더 통신 이상", "전원 재투입", "운전 중 엔코더 통신 두절", "아래 상세 설명 참조"),
    ("AL.24", "주회로 이상 (지락)", "리셋 가능", "출력 측 지락", "모터 절연저항을 측정한다"),
    ("AL.30", "회생 이상", "리셋 가능", "회생 전력 과대, 회생저항 미연결", "회생저항 선정과 Pr.012 설정을 확인한다"),
    ("AL.31", "과속도", "리셋 가능", "지령 속도 과대, 게인 과대", "전자 기어와 게인을 확인한다"),
    ("AL.32", "과전류", "전원 재투입", "출력 단락, 주회로 소자 고장", "출력 배선과 모터를 점검한다"),
    ("AL.33", "과전압", "리셋 가능", "회생 에너지 과대", "감속 시간을 늘리거나 회생저항을 추가한다"),
    ("AL.35", "지령 펄스 주파수 이상", "리셋 가능", "입력 펄스 주파수 과대", "상위 장치 펄스 출력을 확인한다"),
    ("AL.37", "파라미터 이상", "전원 재투입", "파라미터 설정 범위 외", "파라미터를 초기화한다"),
    ("AL.45", "주회로 소자 과열", "전원 재투입", "주위 온도 과대, 팬 정지", "설치 환경과 냉각을 확인한다"),
    ("AL.46", "서보모터 과열", "리셋 가능", "모터 과부하 운전", "운전 패턴을 재검토한다"),
    ("AL.47", "냉각팬 이상", "전원 재투입", "팬 수명, 이물질", "냉각팬을 교체한다"),
    ("AL.50", "과부하 1", "리셋 가능", "정격 초과 연속 운전", "부하율을 확인한다"),
    ("AL.51", "과부하 2", "리셋 가능", "기계 충돌, 구속", "기계 상태를 확인한다"),
    ("AL.52", "위치 편차 과대", "리셋 가능", "가감속 과대, 토크 부족", "편차 과대 레벨 설정과 게인을 확인한다"),
    ("AL.8A", "시리얼 통신 타임아웃", "리셋 가능", "상위 통신 두절", "통신 케이블과 설정을 확인한다"),
    ("AL.E1", "과부하 경고", "자동 해제", "과부하 알람 직전 상태", "부하를 줄인다"),
    ("AL.E9", "주회로 오프 경고", "자동 해제", "서보 온 상태에서 주회로 전원 차단", "주회로 전원을 확인한다"),
]

AS200_PARAMS = [
    "위치 루프 게인", "속도 루프 게인", "속도 적분 시정수", "토크 필터 시정수", "전자 기어 분자",
    "전자 기어 분모", "인포지션 범위", "가속 시정수", "감속 시정수", "S자 가감속 시정수",
    "원점복귀 속도", "회생저항 선택", "원점복귀 크리프 속도", "원점 시프트량", "토크 제한 (정방향)",
    "토크 제한 (역방향)", "속도 제한", "아날로그 속도 지령 최대 회전수", "모니터 출력 선택", "입력 신호 필터",
]


def build_as200(path: Path, rng: random.Random) -> dict:
    m = Manual(path, label_style="roman_front")
    # front matter: cover + notices, roman labels
    m.c.setFont("KR", 26)
    m.c.drawString(LEFT, HEIGHT - 260, "Acme AS200 시리즈")
    m.c.setFont("KR", 18)
    m.c.drawString(LEFT, HEIGHT - 300, "AC 서보앰프 사용설명서")
    m.c.setFont("KR", 11)
    m.c.drawString(LEFT, HEIGHT - 330, "모델: AS200-01 / AS200-04 / AS200-10   문서번호 ACM-AS200-KR-05")
    m.new_page()
    for _ in range(4):
        m.heading("안전상의 주의", 2, bookmark=False)
        for line in rng.sample(SAFETY, 6):
            m.para("• " + line)
        m.new_page()
    m.para("본 사용설명서는 Acme AS200 시리즈 서보앰프의 설치, 배선, 운전, 보수에 대해 설명합니다.")
    m.para("관련 문서: AS200 설치 가이드, MC500 모션컨트롤러 매뉴얼")
    m.front_pages = m.page

    m.chapter_heading(1, "제품 개요")
    m.heading("1.1 형명 구성", 2)
    m.para("AS200-□□ : □□ 는 정격 출력을 나타냅니다. 01=100W, 04=400W, 10=1kW.")
    filler(rng, m, 18)
    m.heading("1.2 각부 명칭", 2)
    filler(rng, m, 20)

    m.chapter_heading(2, "설치")
    m.heading("2.1 설치 환경", 2)
    filler(rng, m, 22)
    m.heading("2.2 설치 방향과 간격", 2)
    filler(rng, m, 22)

    m.chapter_heading(3, "배선")
    m.heading("3.1 주회로 배선", 2)
    filler(rng, m, 20)
    m.heading("3.2 입출력 신호 배선", 2)
    m.para("CN1 핀 배치는 AS200 설치 가이드 4.2절을 참조하십시오.")
    filler(rng, m, 20)

    m.chapter_heading(4, "파라미터")
    m.heading("4.1 파라미터 목록", 2)
    rows = []
    for i in range(1, 241):
        name = AS200_PARAMS[(i - 1) % len(AS200_PARAMS)]
        if i > len(AS200_PARAMS):
            name = f"{name} {(i - 1) // len(AS200_PARAMS) + 1}"
        rows.append([f"Pr.{i:03d}", name, str(rng.choice([0, 1, 10, 100, 500, 1000])), "0~65535", "즉시" if i % 3 else "재투입"])
    m.table(["번호", "명칭", "초기값", "설정 범위", "반영"], rows, [60, 190, 70, 90, 60])
    m.heading("4.2 파라미터 상세", 2)
    for i in range(1, 61):
        m.para(f"Pr.{i:03d} {AS200_PARAMS[(i - 1) % len(AS200_PARAMS)]}: " + " ".join(rng.sample(GENERIC, 2)))

    m.chapter_heading(5, "운전")
    m.heading("5.1 시운전 순서", 2)
    filler(rng, m, 16)
    m.heading("5.2 게인 조정", 2)
    filler(rng, m, 20)
    m.heading("5.3 원점복귀", 2)
    m.mark("as200_homing")
    m.para("AS200은 다음 4가지 원점복귀 방식을 지원합니다. 방식은 원점복귀 방식 선택 파라미터로 지정합니다.")
    for row in [
        ("도그 방식 (Type D)", "근점 도그 신호의 상승 에지 이후 첫 Z상 위치를 원점으로 한다."),
        ("Z상 방식 (Type Z)", "도그 없이 현재 위치에서 가장 가까운 Z상 위치를 원점으로 한다."),
        ("누름 방식 (Type P)", "기계 스토퍼에 눌러 토크 제한에 도달한 위치를 원점으로 한다."),
        ("데이터 세트 방식 (Type S)", "원점복귀 지령을 입력한 현재 위치를 그대로 원점으로 한다."),
    ]:
        m.para(f"• {row[0]}: {row[1]}")
    m.para("원점복귀 속도는 Pr.011, 크리프 속도는 Pr.013 으로 설정합니다.")
    filler(rng, m, 12)

    m.chapter_heading(6, "보수 및 점검")
    m.heading("6.1 일상 점검", 2)
    filler(rng, m, 18)
    m.heading("6.2 부품 수명", 2)
    filler(rng, m, 14)

    m.chapter_heading(7, "통신 기능")
    m.heading("7.1 A-LINK 접속", 2)
    m.para("AS200은 A-LINK 를 통해 MC500 모션컨트롤러와 접속할 수 있습니다.")
    filler(rng, m, 20)
    m.heading("7.2 Modbus 통신", 2)
    filler(rng, m, 20)

    m.chapter_heading(8, "트러블슈팅")
    m.heading("8.1 알람 개요", 2)
    m.para("알람이 발생하면 전면 표시부에 AL.□□ 형식으로 알람 번호가 표시되고 ALM 출력이 OFF 됩니다.")
    filler(rng, m, 14)
    m.fresh_page()
    m.mark("as200_reset_table")
    m.heading("8.2 알람 해제 방법", 2)
    m.para("표 8-2 알람 해제 방법: 알람은 해제 방법에 따라 세 그룹으로 나뉩니다. "
           "전원 재투입이 필요한 알람은 원인을 제거한 뒤 제어 전원을 껐다 켜야 해제됩니다.")
    m.table(["해제 방법", "대상 알람", "비고"], [
        ["전원 재투입", "AL.12 AL.16 AL.20 AL.21 AL.32 AL.37 AL.45 AL.47", "원인 제거 후 전원 OFF→ON"],
        ["리셋 가능", "AL.10 AL.24 AL.30 AL.31 AL.33 AL.35 AL.46 AL.50 AL.51 AL.52 AL.8A", "RES 입력 / SET 버튼"],
        ["자동 해제", "AL.E1 AL.E9 (경고)", "원인 해소 시 자동 해제"],
    ], [80, 300, 100], size=8)
    filler(rng, m, 6)
    m.heading("8.3 알람 목록", 2)
    m.mark("as200_alarm_list")
    m.table(["표시", "명칭", "해제", "주요 원인"], [[a[0], a[1], a[2], a[3]] for a in AS200_ALARMS], [50, 150, 70, 210])
    m.heading("8.4 알람별 원인과 조치", 2)
    for code, name, reset, cause, action in AS200_ALARMS:
        m.heading(f"{code} {name}", 3)
        if code == "AL.21":
            m.mark("as200_al21_detail")
            m.para("운전 중에 서보앰프와 엔코더 사이의 시리얼 통신이 끊겼습니다. 상세 코드로 원인을 구분합니다.")
            m.table(["상세 코드", "내용"], [["AL.21.1", "통신 타임아웃"], ["AL.21.2", "수신 데이터 CRC 오류"]], [90, 300])
            m.para("원인 1: 엔코더 케이블의 단선 또는 커넥터 접촉 불량 → 케이블을 교체하고 CN2 커넥터 체결을 확인한다.")
            m.para("원인 2: 노이즈 유입 → 엔코더 케이블을 동력선과 분리 배선하고 실드를 접지한다.")
            m.para("원인 3: 엔코더 고장 → 서보모터를 교체한다.")
            m.para("해제: 원인을 제거한 뒤 전원을 재투입한다.")
        else:
            m.para(f"원인: {cause}. 조치: {action}. 해제 방법: {reset}.")
            m.para(" ".join(rng.sample(GENERIC, 2)))

    m.chapter_heading(9, "사양")
    m.heading("9.1 일반 사양", 2)
    m.table(["항목", "AS200-01", "AS200-04", "AS200-10"], [
        ["정격 출력", "100W", "400W", "1kW"], ["주회로 전원", "AC200~240V", "AC200~240V", "AC200~240V"],
        ["제어 방식", "정현파 PWM", "정현파 PWM", "정현파 PWM"], ["내장 회생저항", "없음", "10W", "30W"],
    ], [120, 110, 110, 110])
    filler(rng, m, 30)
    m.save()
    set_labels(path, m)
    return m.marks


# ─── Acme AS100 (older model) ────────────────────────────────────────────────

AS100_ALARMS = [
    ("AL.10", "부족 전압", "전원 전압 저하"),
    ("AL.16", "엔코더 이상", "엔코더 케이블 단선"),
    ("AL.20", "엔코더 이상 2", "엔코더 데이터 이상"),
    ("AL.21", "과부하 2", "기계 충돌 또는 구속으로 최대 전류가 수 초간 지속"),
    ("AL.30", "회생 이상", "회생 전력 과대"),
    ("AL.32", "과전류", "출력 단락"),
    ("AL.50", "과부하 1", "정격 초과 연속 운전"),
    ("AL.52", "오차 과대", "위치 편차가 설정값 초과"),
]


def build_as100(path: Path, rng: random.Random) -> dict:
    m = Manual(path)
    m.c.setFont("KR", 24)
    m.c.drawString(LEFT, HEIGHT - 260, "Acme AS100 Series Servo Amplifier")
    m.c.setFont("KR", 16)
    m.c.drawString(LEFT, HEIGHT - 296, "사용설명서 (제3판)")
    m.new_page()
    for number, title, n in [(1, "개요", 30), (2, "설치와 배선", 50), (3, "파라미터", 60), (4, "운전", 50), (5, "보수", 30)]:
        m.chapter_heading(number, title)
        for s in range(1, 4):
            m.heading(f"{number}.{s} {title} 항목 {s}", 2)
            filler(rng, m, n // 3)
    m.chapter_heading(6, "알람과 대책")
    m.heading("6.1 알람 일람", 2)
    m.table(["표시", "명칭", "원인"], [list(a) for a in AS100_ALARMS], [60, 140, 280])
    m.heading("6.2 알람 상세", 2)
    for code, name, cause in AS100_ALARMS:
        m.heading(f"{code} {name}", 3)
        if code == "AL.21":
            m.mark("as100_al21_detail")
            m.para("원인: 기계 충돌 또는 구속으로 최대 전류가 수 초간 지속되었습니다.")
            m.para("조치: 기계의 충돌·구속 여부를 확인하고, 운전 패턴(가감속)을 완화하거나 모터 용량을 재검토하십시오. "
                   "모터 동력선 U/V/W 결선이 바른지도 확인하십시오.")
        else:
            m.para(f"원인: {cause}. " + " ".join(rng.sample(GENERIC, 2)))
    m.chapter_heading(7, "사양")
    filler(rng, m, 40)
    m.save()
    return m.marks


# ─── Acme MC500 motion controller ────────────────────────────────────────────


def build_mc500(path: Path, rng: random.Random) -> dict:
    m = Manual(path)
    m.c.setFont("KR", 24)
    m.c.drawString(LEFT, HEIGHT - 260, "Acme MC500 모션컨트롤러")
    m.c.setFont("KR", 16)
    m.c.drawString(LEFT, HEIGHT - 296, "사용자 매뉴얼")
    m.new_page()
    m.chapter_heading(1, "시스템 구성")
    m.heading("1.1 접속 가능한 서보앰프", 2)
    m.para("MC500은 A-LINK 를 통해 최대 16축의 Acme AS100, AS200 서보앰프를 제어합니다.")
    filler(rng, m, 30)
    for number, title in [(2, "설치"), (3, "A-LINK 배선"), (4, "축 파라미터"), (5, "위치결정 제어"), (6, "보간 제어"),
                          (7, "원점복귀"), (8, "프로그램"), (9, "모니터"), (10, "통신")]:
        m.chapter_heading(number, title)
        for s in range(1, 4):
            m.heading(f"{number}.{s} {title} {s}", 2)
            filler(rng, m, 16)
    m.chapter_heading(11, "에러 코드")
    m.heading("11.1 에러 코드 체계", 2)
    m.para("에러 코드는 4자리입니다. 1000번대: 공통 에러, 2000번대: 축 에러, 3000번대: 경고. "
           "에러 코드는 HMI 와 모니터 화면에 표시됩니다.")
    m.heading("11.2 공통 에러 (1000번대)", 2)
    m.table(["코드", "내용"], [[str(1000 + i), f"공통 에러 {i}: " + rng.choice(GENERIC)[:30]] for i in range(1, 31)], [60, 420])
    m.heading("11.3 축 에러 (2000번대)", 2)
    axis = {
        2001: "목표 위치 범위 외", 2010: "속도 지령 범위 외", 2020: "소프트웨어 스트로크 리밋 (+)",
        2021: "소프트웨어 스트로크 리밋 (-)", 2050: "하드웨어 스트로크 리밋 (+)", 2052: "하드웨어 스트로크 리밋 (-)",
        2060: "원점복귀 미완료", 2070: "A-LINK 통신 에러",
    }
    rows = [[str(c), n] for c, n in sorted(axis.items())]
    rows.insert(5, ["2051", "서보 레디 OFF (운전 중)"])
    m.table(["코드", "내용"], rows, [60, 420])
    m.heading("11.4 축 에러 상세", 2)
    for code, name in rows:
        m.heading(f"{code} {name}", 3)
        if code == "2051":
            m.mark("mc500_2051_detail")
            m.para("운전 중에 축의 서보 레디 신호가 OFF 되었습니다. 연결된 서보앰프가 알람 상태이거나 "
                   "서보앰프의 주회로 전원이 차단된 경우에 발생합니다.")
            m.para("조치: 서보앰프 전면 표시부의 알람 번호(AL.□□)를 확인하고 해당 서보앰프 매뉴얼의 알람 조치를 따르십시오. "
                   "서보앰프에 알람이 없으면 주회로 전원과 A-LINK 케이블 연결을 확인하십시오.")
        else:
            m.para(" ".join(rng.sample(GENERIC, 2)))
    m.heading("11.5 경고 (3000번대)", 2)
    m.table(["코드", "내용"], [[str(3000 + i), f"경고 {i}"] for i in range(1, 21)], [60, 420])
    m.save()
    return m.marks


# ─── AS200 installation guide (no bookmarks, printed ToC, pin table image) ───

CN1_PINS = [
    (1, "P15R", "DC15V output"), (2, "VC", "Analog speed command"), (3, "LG", "Control common"),
    (4, "LA", "Encoder A-phase out"), (5, "LAR", "Encoder A-phase out (inv)"), (6, "LB", "Encoder B-phase out"),
    (7, "LBR", "Encoder B-phase out (inv)"), (8, "LZ", "Encoder Z-phase out"), (9, "LZR", "Encoder Z-phase out (inv)"),
    (10, "PP", "Forward pulse"), (11, "PG", "Forward pulse (inv)"), (12, "NP", "Reverse pulse"),
    (13, "NG", "Reverse pulse (inv)"), (14, "SON", "Servo-on input"), (15, "RES", "Reset input"),
    (16, "EMG", "Emergency stop input"), (17, "LSP", "Forward stroke end"), (18, "LSN", "Reverse stroke end"),
    (19, "DOG", "Near-point dog input"), (20, "TL", "Torque limit select"), (21, "DICOM", "Input common"),
    (22, "RD", "Ready output"), (23, "ALM", "Alarm output (open collector, OFF at alarm)"),
    (24, "INP", "In-position output"), (25, "ZSP", "Zero speed output"), (26, "DOCOM", "Output common"),
]


def pin_table_image(path: Path, font_path: str) -> None:
    font = ImageFont.truetype(font_path, 22)
    bold = ImageFont.truetype(font_path, 26)
    img = Image.new("RGB", (1000, 1120), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 20), "CN1 Pin Assignment (AS200)", fill="black", font=bold)
    y = 80
    d.text((40, y), "Pin", fill="black", font=font)
    d.text((140, y), "Signal", fill="black", font=font)
    d.text((300, y), "Function", fill="black", font=font)
    for pin, signal, function in CN1_PINS:
        y += 38
        d.line((30, y - 6, 970, y - 6), fill="gray")
        d.text((50, y), str(pin), fill="black", font=font)
        d.text((140, y), signal, fill="black", font=font)
        d.text((300, y), function, fill="black", font=font)
    img.save(path)


def build_install_guide(path: Path, rng: random.Random, font_path: str, work: Path) -> dict:
    m = Manual(path, label_style="minus_cover", bookmarks="none")
    m.c.setFont("KR", 24)
    m.c.drawString(LEFT, HEIGHT - 260, "AS200 설치 가이드")
    m.c.setFont("KR", 13)
    m.c.drawString(LEFT, HEIGHT - 292, "Acme AC 서보앰프 AS200 시리즈 설치·배선 안내서")
    m.new_page()
    toc_page = m.page
    m.new_page()  # printed ToC is drawn after layout, once the pages are known
    m.new_page()

    def chapter(number, title):
        m.chapter_heading(number, title)

    chapter(1, "안전 주의사항")
    for line in SAFETY:
        m.para("• " + line)
    filler(rng, m, 14)
    chapter(2, "제품 확인")
    m.heading("2.1 동봉품", 2)
    filler(rng, m, 12)
    m.heading("2.2 명판 보는 법", 2)
    filler(rng, m, 12)
    chapter(3, "설치 및 배선")
    m.heading("3.1 설치 공간", 2)
    filler(rng, m, 16)
    m.heading("3.2 주회로 단자", 2)
    m.table(["단자", "명칭"], [["L1 L2 L3", "주회로 전원"], ["L11 L21", "제어 회로 전원"], ["P+ C D", "회생 옵션"],
                               ["U V W", "모터 출력"], ["PE", "보호 접지"]], [120, 300])
    filler(rng, m, 10)
    m.heading("3.3 주회로 배선 순서", 2)
    filler(rng, m, 14)
    m.heading("3.4 회생저항 연결", 2)
    m.mark("install_regen")
    m.para("AS200-04 와 AS200-10 은 회생저항을 내장하고 있으며, 출하 시 P+ 와 D 단자 사이에 단락편이 연결되어 있습니다.")
    m.para("외부 회생저항을 사용할 때는 P+ 와 D 사이의 단락편을 제거하고, 외부 회생저항을 P+ 와 C 단자에 연결합니다. "
           "그 다음 Pr.012 회생저항 선택을 사용하는 회생저항에 맞게 설정합니다.")
    m.para("내장 회생저항을 사용할 때는 P+ 와 D 사이의 단락편을 그대로 둡니다. AS200-01 은 회생저항이 없으므로 "
           "회생 에너지가 큰 경우 외부 회생저항이 필요합니다.")
    m.para("주의: 회생저항은 운전 중 고온이 되므로 불연성 재질 위에 설치하고 배선은 내열 전선을 사용하십시오.")
    filler(rng, m, 6)
    chapter(4, "커넥터 및 핀 배치")
    m.heading("4.1 커넥터 개요", 2)
    m.para("CN1: 입출력 신호, CN2: 엔코더, CN3: 통신(A-LINK), CN4: USB.")
    filler(rng, m, 10)
    m.heading("4.2 CN1 핀 배치", 2)
    image = work / "cn1_pins.png"
    pin_table_image(image, font_path)
    m.fresh_page()
    m.mark("install_cn1_pins")
    m.image(image, 430, 482, "그림 4-2 CN1 핀 배치 (커넥터 정면에서 본 그림)")
    m.heading("4.3 CN2 엔코더 커넥터", 2)
    filler(rng, m, 14)
    chapter(5, "시운전")
    m.heading("5.1 전원 투입 전 확인", 2)
    filler(rng, m, 14)
    m.heading("5.2 JOG 운전", 2)
    filler(rng, m, 14)

    # Draw the printed ToC on pages 2-3 now that page numbers are known.
    m.save()
    entries = m.toc
    tmp = path.with_suffix(".tmp.pdf")
    toc_doc = Manual(tmp, label_style="minus_cover", bookmarks="none")
    toc_doc.page = toc_page
    printed_toc(toc_doc, entries, offset=1)
    toc_doc.save()
    _overlay_pages(path, tmp, toc_page)
    tmp.unlink()
    return m.marks


def _overlay_pages(target: Path, overlay: Path, first_page: int) -> None:
    """Merge the overlay's pages onto target pages starting at first_page (1-based)."""
    base = PdfReader(str(target))
    over = PdfReader(str(overlay))
    writer = PdfWriter()
    for i, page in enumerate(base.pages):
        j = i - (first_page - 1)
        if 0 <= j < len(over.pages):
            page.merge_page(over.pages[j])
        writer.add_page(page)
    writer.write(str(target))


# ─── Globex GX7 inverter, scanned ────────────────────────────────────────────

GX7_FAULTS = [
    ("E.OC1", "가속 중 과전류", ["가속 시간이 너무 짧지 않은지", "출력 배선의 단락·지락", "토크 부스트 설정 과다"]),
    ("E.OC2", "정속 중 과전류", ["부하가 급변하지 않았는지", "출력 배선(U/V/W)의 단락·지락", "모터 절연저항 저하",
                              "모터 축의 구속 여부"]),
    ("E.OC3", "감속 중 과전류", ["감속 시간이 너무 짧지 않은지", "기계 브레이크가 동작하지 않았는지"]),
    ("E.OV1", "가속 중 과전압", ["전원 전압 변동", "가속 시간"]),
    ("E.OV2", "정속 중 과전압", ["부하에 의한 회생 운전 여부"]),
    ("E.OV3", "감속 중 과전압", ["감속 시간 연장", "제동 저항 사용 검토"]),
    ("E.THM", "모터 과부하", ["전자 서멀 설정값", "부하 상태"]),
    ("E.FIN", "방열판 과열", ["주위 온도", "냉각팬 동작"]),
    ("E.UVT", "부족 전압", ["전원 전압", "순간 정전 여부"]),
    ("E.GF", "출력 지락", ["모터와 출력 배선의 지락"]),
]


def build_gx7_scan(path: Path, rng: random.Random, work: Path) -> dict:
    text_pdf = work / "gx7_text.pdf"
    m = Manual(text_pdf, bookmarks="none")
    m.c.setFont("KR", 24)
    m.c.drawString(LEFT, HEIGHT - 260, "Globex GX7 범용 인버터")
    m.c.setFont("KR", 15)
    m.c.drawString(LEFT, HEIGHT - 294, "취급설명서")
    m.new_page()
    m.new_page()  # page 2: blank notice page
    toc_page = m.page
    m.new_page()
    m.new_page()
    for number, title, n in [(1, "안전 주의", 14), (2, "설치", 20), (3, "배선", 24), (4, "조작 패널", 20),
                             (5, "기본 운전", 20), (6, "파라미터", 30)]:
        m.chapter_heading(number, title)
        for s in range(1, 3):
            m.heading(f"{number}.{s} {title} {s}", 2)
            filler(rng, m, n // 2)
    m.chapter_heading(7, "보호 기능과 고장 코드")
    m.heading("7.1 고장 코드 일람", 2)
    m.table(["표시", "명칭"], [[c, n] for c, n, _ in GX7_FAULTS], [80, 300])
    m.heading("7.2 고장 코드별 점검 사항", 2)
    for code, name, checks in GX7_FAULTS:
        m.heading(f"{code} {name}", 3)
        if code == "E.OC2":
            m.mark("gx7_eoc2_detail")
            m.para("정속 운전 중에 출력 전류가 과전류 검출 레벨을 넘었습니다. 다음을 점검하십시오.")
        for i, check in enumerate(checks, 1):
            m.para(f"{i}) {check}")
        m.para(rng.choice(GENERIC))
    m.chapter_heading(8, "사양")
    filler(rng, m, 26)
    m.save()

    tmp = work / "gx7_toc.pdf"
    toc_doc = Manual(tmp, bookmarks="none")
    toc_doc.page = toc_page
    printed_toc(toc_doc, m.toc, offset=0)
    toc_doc.save()
    _overlay_pages(text_pdf, tmp, toc_page)

    # Rasterize and rebuild as an image-only PDF, like a scanned paper manual.
    if not shutil.which("pdftoppm"):
        sys.exit("pdftoppm (poppler-utils) is needed to build the scanned sample.")
    subprocess.run(["pdftoppm", "-r", "100", "-gray", "-jpeg", str(text_pdf), str(work / "gx7")], check=True)
    scan = canvas.Canvas(str(path), pagesize=A4)
    for image in sorted(work.glob("gx7-*.jpg")):
        scan.drawImage(str(image), 0, 0, width=WIDTH, height=HEIGHT)
        scan.showPage()
    scan.save()
    return m.marks


# ─── Initech IT300 torque controller (weak bookmarks) ────────────────────────


def build_it300(path: Path, rng: random.Random) -> dict:
    m = Manual(path, bookmarks="none")
    m.c.setFont("KR", 24)
    m.c.drawString(LEFT, HEIGHT - 260, "Initech IT300 토크 컨트롤러")
    m.c.setFont("KR", 15)
    m.c.drawString(LEFT, HEIGHT - 294, "사용 설명서")
    m.new_page()
    toc_page = m.page
    m.new_page()
    m.new_page()
    for number, title, n in [(1, "안전", 14), (2, "개요", 20), (3, "설치", 24), (4, "배선", 24)]:
        m.chapter_heading(number, title)
        for s in range(1, 3):
            m.heading(f"{number}.{s} {title} {s}", 2)
            filler(rng, m, n // 2)
    m.chapter_heading(5, "체결 프로그램")
    m.heading("5.1 프로그램 구성", 2)
    m.para("토크 상한(P-17)을 변경할 때는 토크 하한(P-18)이 상한보다 작은지 함께 확인하십시오.")
    filler(rng, m, 20)
    m.heading("5.2 체결 단계 설정", 2)
    filler(rng, m, 20)
    m.chapter_heading(6, "파라미터")
    m.heading("6.1 파라미터 일람", 2)
    params = {
        1: ("체결 모드", "0", "0~3", ""), 2: ("목표 토크", "50.0", "0.0~300.0", "%"),
        17: ("토크 상한", "150.0", "0.0~300.0", "%"), 18: ("토크 하한", "20.0", "0.0~300.0", "%"),
        170: ("통신 응답 지연", "5", "0~100", "ms"),
    }
    rows = []
    for i in list(range(1, 61)) + list(range(100, 181, 5)):
        name, default, rng_text, unit = params.get(i, (f"설정 항목 {i}", str(rng.randint(0, 100)), "0~1000", ""))
        rows.append([f"P-{i:02d}", name, default, rng_text, unit])
    m.table(["번호", "명칭", "기본값", "설정 범위", "단위"], rows, [60, 170, 80, 110, 60], row_marks={16: "it300_p17"})
    m.heading("6.2 파라미터 상세", 2)
    filler(rng, m, 30)
    m.chapter_heading(7, "에러")
    filler(rng, m, 30)
    m.save()

    tmp = path.with_suffix(".tmp.pdf")
    toc_doc = Manual(tmp, bookmarks="none")
    toc_doc.page = toc_page
    printed_toc(toc_doc, m.toc, offset=0)
    toc_doc.save()
    _overlay_pages(path, tmp, toc_page)
    tmp.unlink()

    # Weak bookmarks: three top-level entries that say almost nothing.
    writer = PdfWriter(clone_from=str(path))
    writer.add_outline_item("표지", 0)
    writer.add_outline_item("본문", toc_page + 1)
    writer.add_outline_item("부록", m.page - 5)
    writer.write(str(path))
    return m.marks


# ─── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir")
    parser.add_argument("--truth", help="write ground-truth pages (JSON) here; keep it outside out_dir")
    parser.add_argument("--scale", type=int, default=SCALE, help="filler multiplier (1 = small, fast test files)")
    args = parser.parse_args()
    globals()["SCALE"] = args.scale

    font_path = find_font()
    register_font(font_path)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    truth: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        builders = [
            ("Acme_AS200_서보앰프_사용설명서.pdf", lambda p: build_as200(p, random.Random(200))),
            ("Acme_AS100_Servo_Manual_v3.pdf", lambda p: build_as100(p, random.Random(100))),
            ("Acme_MC500_모션컨트롤러_매뉴얼.pdf", lambda p: build_mc500(p, random.Random(500))),
            ("AS200_설치가이드.pdf", lambda p: build_install_guide(p, random.Random(201), font_path, work)),
            ("GX7_inverter_scan.pdf", lambda p: build_gx7_scan(p, random.Random(7), work)),
            ("IT300_manual.pdf", lambda p: build_it300(p, random.Random(300))),
        ]
        for name, build in builders:
            marks = build(out / name)
            labels = PdfReader(str(out / name)).page_labels
            for key, page in marks.items():
                truth[key] = {"file": name, "page": page, "printed_label": labels[page - 1]}
            print(f"built {name}")
    if args.truth:
        Path(args.truth).write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ground truth → {args.truth}")


if __name__ == "__main__":
    main()
