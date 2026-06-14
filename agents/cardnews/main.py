import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import google.genai as genai
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

import sys as _sys
_sys.path.insert(0, str(ROOT))
from utils.gemini_retry import gemini_retry

# ── 색상 ─────────────────────────────────────────────────────────────────────
C_GRAD_TOP    = (102, 126, 234)   # #667eea
C_GRAD_BTM    = (118,  75, 162)   # #764ba2
C_PURPLE      = (118,  75, 162)
C_PURPLE_MID  = ( 80,  50, 140)
C_PURPLE_DEEP = ( 50,  30, 110)
C_PURPLE_LITE = (240, 235, 255)   # 연보라 배경
C_PURPLE_CARD = (250, 248, 255)
C_WHITE       = (255, 255, 255)
C_DARK        = ( 30,  20,  60)
C_MID         = ( 90,  70, 130)
C_ACCENT_LITE = (220, 200, 255)
C_ACCENT_GOLD = (255, 220, 100)   # 강조 골드
C_GREEN_LT    = (160, 230, 140)   # 체크 아이콘
C_DIVIDER     = (220, 215, 240)
C_SHADOW      = (200, 195, 220)   # 카드 그림자 시뮬레이션

SIZE   = 1080
MARGIN = 72


@gemini_retry
def _gemini_one_liner(text: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not text.strip():
        return (text[:38] + "…") if len(text) > 38 else text
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f"다음 텍스트를 한국어 20자 이내 1줄로 요약하세요. 요약문만 출력하세요:\n{text}",
        )
        summary = resp.text.strip()
        return (summary[:38] + "…") if len(summary) > 38 else summary
    except Exception:
        return (text[:38] + "…") if len(text) > 38 else text


def _safe_keyword(keyword: str) -> str:
    return re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)


def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    import sys
    if sys.platform == "win32":
        paths = (
            ["C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf"]
            if bold
            else ["C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/gulim.ttc"]
        ) + [
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold
            else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        ]
    else:
        paths = (
            [
                "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
            if bold
            else [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/nanum/NanumGothicLight.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _gradient_bg(img: Image.Image, c1: tuple, c2: tuple) -> None:
    draw = ImageDraw.Draw(img)
    h = img.height
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (img.width, y)], fill=(r, g, b))


def _shadow_rect(draw: ImageDraw.ImageDraw, xy: list, radius: int = 14,
                 shadow_offset: int = 5, shadow_alpha: int = 40) -> None:
    """그림자가 있는 둥근 사각형. offset만큼 오프셋된 어두운 레이어를 먼저 그린다."""
    sx0, sy0, sx1, sy1 = xy[0] + shadow_offset, xy[1] + shadow_offset, xy[2] + shadow_offset, xy[3] + shadow_offset
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=radius, fill=C_SHADOW)


def _accent_bar(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int,
                color: tuple, width: int = 6, radius: int = 3) -> None:
    """카드 왼쪽 수직 강조 바."""
    draw.rounded_rectangle([x, y0, x + width, y1], radius=radius, fill=color)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """한국어 포함 텍스트를 max_w px 이내로 줄바꿈."""
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if dummy_draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _center_x(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    w = draw.textlength(text, font=font)
    return int((SIZE - w) // 2)


def _draw_centered(draw: ImageDraw.ImageDraw, y: int, text: str,
                   font: ImageFont.FreeTypeFont, color: tuple) -> int:
    """수평 중앙 정렬 텍스트 그리기. 다음 y 반환."""
    x = _center_x(draw, text, font)
    draw.text((x, y), text, font=font, fill=color)
    bbox = draw.textbbox((0, 0), text, font=font)
    return y + (bbox[3] - bbox[1]) + 16


# ── 공용 헬퍼 (가독성/구조 개선) ────────────────────────────────────────────
def _clean(text: str) -> str:
    """마크다운 기호(**, *, 선행 #) 제거 + 공백 정리."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"^#+\s*", "", text.strip())
    return text.strip()


def _first_sentences(text: str, max_chars: int) -> str:
    """문장 경계로 잘라 '완결된' 텍스트만 반환 (중간 잘림 방지)."""
    text = _clean(text)
    if len(text) <= max_chars:
        out = text
    else:
        parts = re.split(r"(?<=[.!?다요죠음])[\s.]+", text)
        out = ""
        for p in parts:
            if not p:
                continue
            if out and len(out) + len(p) + 1 > max_chars:
                break
            out = (out + " " + p).strip()
        if len(out) > max_chars:  # 첫 문장이 예산 초과 → 단어 경계로 자름 (중간 글자 안 끊기게)
            trimmed = ""
            for w in out.split():
                if trimmed and len(trimmed) + len(w) + 1 > max_chars:
                    break
                trimmed = (trimmed + " " + w).strip()
            out = trimmed
    # 닫히지 않은 괄호 조각(예: "(ex.") 제거
    if out.count("(") > out.count(")"):
        out = out[: out.rfind("(")].rstrip(" ,")
    return out.strip()


def _page_index(draw: ImageDraw.ImageDraw, n: int, total: int = 4, on_light: bool = False) -> None:
    """우하단 페이지 인덱스 (n/total) + 다음 장 유도 화살표."""
    col = C_MID if on_light else C_WHITE
    f = _find_font(28, bold=True)
    txt = f"{n} / {total}"
    w = int(draw.textlength(txt, font=f))
    draw.text((SIZE - MARGIN - w, SIZE - 64), txt, font=f, fill=col)
    if n < total:
        af = _find_font(34, bold=True)
        draw.text((SIZE - MARGIN - w - 50, SIZE - 67), "▶", font=af,
                  fill=C_ACCENT_GOLD if not on_light else C_PURPLE)


def _highlight_text(draw, x, y, text, font, text_col, bg_col, pad=(16, 8)):
    """포인트 컬러 배경 블록 위에 텍스트 (강조용). 끝 x 반환."""
    w = int(draw.textlength(text, font=font))
    bbox = draw.textbbox((0, 0), text, font=font)
    h = bbox[3] - bbox[1]
    draw.rounded_rectangle([x, y - pad[1], x + w + pad[0] * 2, y + h + pad[1] + 6],
                           radius=10, fill=bg_col)
    draw.text((x + pad[0], y), text, font=font, fill=text_col)
    return x + w + pad[0] * 2


def _sentiment_pct(data: dict) -> int:
    counts = {"긍정": 0, "중립": 0, "부정": 0}
    for p in data.get("posts_sentiment", []):
        counts[p.get("sentiment", "중립")] = counts.get(p.get("sentiment", "중립"), 0) + 1
    total = sum(counts.values()) or 1
    return counts["긍정"] * 100 // total


def _interest_level(data: dict) -> str:
    c = {"높음": 0, "중간": 0, "낮음": 0}
    for it in data.get("interest_estimation", []):
        c[it.get("level", "중간")] = c.get(it.get("level", "중간"), 0) + 1
    return max(c, key=c.get) if any(c.values()) else "중간"


# ── 슬라이드 1: 후킹형 표지 (히어로 수치) ───────────────────────────────────
def make_slide1(data: dict) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE))
    _gradient_bg(img, C_GRAD_TOP, C_GRAD_BTM)
    draw = ImageDraw.Draw(img)

    keyword = data.get("keyword", "")
    analyzed_at = data.get("analyzed_at", "")
    try:
        date_str = datetime.fromisoformat(analyzed_at).strftime("%Y.%m.%d")
    except Exception:
        date_str = date.today().strftime("%Y.%m.%d")

    cr = ""
    for t in data.get("search_trends", []):
        if t.get("change_rate"):
            cr = t["change_rate"]
            break

    # 배경 장식 원
    draw.ellipse([SIZE - 230, -110, SIZE + 90, 210], fill=C_PURPLE_MID)
    draw.ellipse([SIZE - 165, -70, SIZE + 45, 165], fill=C_PURPLE_DEEP)

    # 태그 배지
    tag_font = _find_font(30, bold=True)
    tag_text = "마케팅 인사이트"
    tw = int(draw.textlength(tag_text, font=tag_font))
    draw.rounded_rectangle([MARGIN, MARGIN, MARGIN + tw + 36, MARGIN + 52], radius=26, fill=C_PURPLE_DEEP)
    draw.text((MARGIN + 18, MARGIN + 9), tag_text, font=tag_font, fill=C_WHITE)

    # 키워드 (큰 텍스트)
    kw_font = _find_font(82, bold=True)
    y = 188
    for line in _wrap(keyword, kw_font, SIZE - MARGIN * 2):
        y = _draw_centered(draw, y, line, kw_font, C_WHITE)

    # 히어로 지표: 검색량 변화율 크게
    y += 26
    if cr:
        up = cr.startswith("+")
        hero_col = (150, 240, 170) if up else C_ACCENT_GOLD
        arrow = "▲" if up else "▼"
        _draw_centered(draw, y, "최근 검색량", _find_font(40, bold=True), C_ACCENT_LITE)
        y += 60
        num_font = _find_font(156, bold=True)
        hero = f"{cr}{arrow}"
        hw = int(draw.textlength(hero, font=num_font))
        draw.text(((SIZE - hw) // 2, y), hero, font=num_font, fill=hero_col)
        bb = draw.textbbox((0, 0), hero, font=num_font)
        y += (bb[3] - bb[1]) + 56
    else:
        y += 10

    # 스탯 칩 2개 (관심도 / 긍정반응) — 고대비
    chips = [("관심도", _interest_level(data)), ("긍정 반응", f"{_sentiment_pct(data)}%")]
    gap = 30
    chip_w = (SIZE - MARGIN * 2 - gap) // 2
    chip_h = 132
    lab_f = _find_font(28)
    val_f = _find_font(52, bold=True)
    for ci, (lab, val) in enumerate(chips):
        cx0 = MARGIN + ci * (chip_w + gap)
        draw.rounded_rectangle([cx0, y, cx0 + chip_w, y + chip_h], radius=22, fill=C_PURPLE_DEEP)
        lw = int(draw.textlength(lab, font=lab_f))
        draw.text((cx0 + (chip_w - lw) // 2, y + 26), lab, font=lab_f, fill=C_ACCENT_LITE)
        vw = int(draw.textlength(val, font=val_f))
        draw.text((cx0 + (chip_w - vw) // 2, y + 62), val, font=val_f, fill=C_WHITE)

    # 하단: 넘겨보기 유도 + 날짜 + 페이지
    _draw_centered(draw, SIZE - 150, "핵심 전략 보기 →", _find_font(34, bold=True), C_ACCENT_GOLD)
    draw.text((MARGIN, SIZE - 62), date_str, font=_find_font(28), fill=C_ACCENT_LITE)
    _page_index(draw, 1)

    return img


# ── 슬라이드 2: 트렌드 TOP 3 ─────────────────────────────────────────────────
def make_slide2(data: dict) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), C_WHITE)

    # 헤더 그라데이션 바
    hdr = Image.new("RGB", (SIZE, 148))
    _gradient_bg(hdr, C_GRAD_TOP, C_GRAD_BTM)
    img.paste(hdr, (0, 0))
    draw = ImageDraw.Draw(img)
    _draw_centered(draw, 44, "이번 주 트렌드 TOP 3", _find_font(52, bold=True), C_WHITE)

    trends = data.get("trends", [])[:3]
    num_font   = _find_font(38, bold=True)
    title_font = _find_font(30, bold=True)
    desc_font  = _find_font(26)
    brand_font = _find_font(26)

    card_h = 224
    gap = 16
    card_starts = [162, 162 + card_h + gap, 162 + (card_h + gap) * 2]

    for i, trend in enumerate(trends):
        trend = _clean(trend)
        y0 = card_starts[i]

        # 카드 그림자 + 배경
        _shadow_rect(draw, [MARGIN, y0, SIZE - MARGIN, y0 + card_h], radius=16, shadow_offset=4)
        draw.rounded_rectangle([MARGIN, y0, SIZE - MARGIN, y0 + card_h],
                                radius=16, fill=C_PURPLE_CARD, outline=C_DIVIDER, width=1)
        # 왼쪽 강조 바
        _accent_bar(draw, MARGIN, y0, y0 + card_h, C_PURPLE, width=7, radius=4)

        # 번호 원 (골드 테두리)
        cx, cy, cr = MARGIN + 54, y0 + 44, 34
        draw.ellipse([cx - cr - 3, cy - cr - 3, cx + cr + 3, cy + cr + 3], fill=C_ACCENT_GOLD)
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=C_PURPLE)
        num_str = str(i + 1)
        nw = int(draw.textlength(num_str, font=num_font))
        draw.text((cx - nw // 2, cy - 20), num_str, font=num_font, fill=C_WHITE)

        # 제목
        if ":" in trend:
            title_raw = trend.split(":")[0].strip()
        else:
            title_raw = trend[:40]

        tx = MARGIN + 106
        title_lines = _wrap(title_raw, title_font, SIZE - tx - MARGIN - 12)[:2]
        ty = y0 + 16
        for line in title_lines:
            draw.text((tx, ty), line, font=title_font, fill=C_DARK)
            ty += 38

        # 카드 내 구분선
        draw.line([(MARGIN + 20, ty + 8), (SIZE - MARGIN - 20, ty + 8)],
                  fill=C_DIVIDER, width=1)

        # 설명: 완결된 문장만 (중간 잘림 방지)
        if ":" in trend:
            desc_raw = trend.split(":", 1)[1].strip()
        else:
            desc_raw = trend
        desc_raw = _first_sentences(desc_raw, 92)
        desc_lines = _wrap(desc_raw, desc_font, SIZE - MARGIN * 2 - 40)[:3]
        dy = ty + 22
        for line in desc_lines:
            draw.text((MARGIN + 26, dy), line, font=desc_font, fill=C_MID)
            dy += 34

    # 브랜드 + 페이지
    _draw_centered(draw, SIZE - 50, "@auto.markai", brand_font, C_PURPLE)
    _page_index(draw, 2, on_light=True)

    return img


# ── 슬라이드 3: 다음 주 추천 키워드 ─────────────────────────────────────────
def make_slide3(data: dict) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), C_PURPLE_LITE)
    draw = ImageDraw.Draw(img)

    # 배경 장식 원 (좌하단)
    draw.ellipse([-80, SIZE - 200, 200, SIZE + 80], fill=(200, 190, 240))

    # 헤더 그라데이션 바
    hdr = Image.new("RGB", (SIZE, 148))
    _gradient_bg(hdr, C_GRAD_TOP, C_GRAD_BTM)
    img.paste(hdr, (0, 0))
    draw = ImageDraw.Draw(img)
    _draw_centered(draw, 44, "다음 주 공략 키워드", _find_font(52, bold=True), C_WHITE)

    next_kws = data.get("next_week_keywords", [])[:3]
    kw_font     = _find_font(38, bold=True)
    reason_font = _find_font(26)
    num_font    = _find_font(30, bold=True)
    card_colors = [C_PURPLE, C_PURPLE_MID, (140, 100, 200)]

    card_y_starts = [180, 416, 652]
    card_h = 200

    for i, item in enumerate(next_kws):
        kw     = _clean(item.get("keyword", "") if isinstance(item, dict) else item)
        reason = _first_sentences(item.get("reason", "") if isinstance(item, dict) else "", 54)

        cy = card_y_starts[i]
        # 카드 그림자 + 배경
        _shadow_rect(draw, [MARGIN, cy, SIZE - MARGIN, cy + card_h], radius=18, shadow_offset=4)
        draw.rounded_rectangle([MARGIN, cy, SIZE - MARGIN, cy + card_h],
                                radius=18, fill=C_WHITE)
        # 왼쪽 강조 바 (두껍게)
        _accent_bar(draw, MARGIN, cy, cy + card_h, card_colors[i], width=10, radius=5)

        # 번호 배지 (색상 원)
        nc = MARGIN + 34
        draw.ellipse([nc - 20, cy + 18, nc + 20, cy + 58], fill=card_colors[i])
        num_str = str(i + 1)
        nw = int(draw.textlength(num_str, font=num_font))
        draw.text((nc - nw // 2, cy + 22), num_str, font=num_font, fill=C_WHITE)

        # 키워드
        kw_lines = _wrap(kw, kw_font, SIZE - MARGIN * 2 - 80)[:2]
        ky = cy + 20
        for line in kw_lines:
            draw.text((MARGIN + 68, ky), line, font=kw_font, fill=C_DARK)
            ky += 48

        # 구분선
        draw.line([(MARGIN + 68, ky + 2), (SIZE - MARGIN - 20, ky + 2)],
                  fill=C_DIVIDER, width=1)

        # 이유
        if reason:
            reason_lines = _wrap(reason, reason_font, SIZE - MARGIN * 2 - 80)[:2]
            ry = ky + 12
            for rline in reason_lines:
                draw.text((MARGIN + 68, ry), rline, font=reason_font, fill=C_MID)
                ry += 30

    # 하단 메시지 + 페이지
    _draw_centered(draw, SIZE - 60, "매주 월요일 네이버 실시간 데이터 업데이트",
                   _find_font(26), C_PURPLE)
    _draw_centered(draw, SIZE - 30, "@auto.markai", _find_font(22), C_MID)
    _page_index(draw, 3, on_light=True)

    return img


# ── 슬라이드 4: CTA ──────────────────────────────────────────────────────────
def make_slide4(data: dict) -> Image.Image:
    ig_username = os.environ.get("INSTAGRAM_USERNAME", "@auto.markai")
    if not ig_username.startswith("@"):
        ig_username = "@" + ig_username

    img = Image.new("RGB", (SIZE, SIZE))
    _gradient_bg(img, C_GRAD_BTM, C_GRAD_TOP)
    draw = ImageDraw.Draw(img)

    # 상단 헤드라인 (박스 밖)
    _draw_centered(draw, 106, "팔로우하면", _find_font(34), C_ACCENT_LITE)
    _draw_centered(draw, 152, "마케팅 인사이트가 자동으로", _find_font(42, bold=True), C_WHITE)

    # 메인 박스 (슬라이드 하단까지 꽉 채움)
    bx, by, bw, bh = 72, 224, SIZE - 144, 800
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=24,
                            fill=(90, 60, 140), outline=C_WHITE, width=2)

    # 박스 내 상단: 브랜드 & 주기
    y = by + 52
    y = _draw_centered(draw, y, "매주 월요일", _find_font(52, bold=True), C_WHITE)
    y = _draw_centered(draw, y + 6, "네이버 DataLab 실시간 분석", _find_font(34), C_ACCENT_LITE)
    y += 36

    # 구분선
    draw.line([(bx + 56, y), (bx + bw - 56, y)], fill=(200, 180, 255), width=1)
    y += 32

    # 혜택 목록 4개
    benefits = [
        "실검색량 트렌드 & 변화율",
        "다음 주 공략 키워드 3선",
        "경쟁 포화도 & 틈새 기회",
        "감성 분석 & 타겟 인사이트",
    ]
    bullet_font = _find_font(30)
    for benefit in benefits:
        # 체크 원형 배지 (체크마크는 폰트 대신 선으로 직접 그림 — 글리프 깨짐 방지)
        cr = 18
        cx_icon = bx + 44 + cr
        cy_icon = y + 18
        draw.ellipse([cx_icon - cr, cy_icon - cr, cx_icon + cr, cy_icon + cr], fill=C_GREEN_LT)
        draw.line([(cx_icon - 8, cy_icon + 1), (cx_icon - 2, cy_icon + 7), (cx_icon + 9, cy_icon - 8)],
                  fill=C_PURPLE_DEEP, width=4, joint="curve")
        draw.text((bx + 44 + cr * 2 + 14, y), benefit, font=bullet_font, fill=C_WHITE)
        y += 58

    y += 20
    # 구분선 2
    draw.line([(bx + 56, y), (bx + bw - 56, y)], fill=(200, 180, 255), width=1)
    y += 40

    # CTA 버튼 스타일
    cta_font = _find_font(44, bold=True)
    y = _draw_centered(draw, y, f"{ig_username} 팔로우", cta_font, C_WHITE)
    y += 40
    _draw_centered(draw, y, "전체 인사이트는 캡션에서 확인 ↓", _find_font(32, bold=True), C_ACCENT_GOLD)

    # 하단 점 인디케이터 (4번째 점 활성 — 마지막 슬라이드)
    for j in range(4):
        cx = SIZE // 2 - 54 + j * 36
        cy = SIZE - 36
        r = 8 if j == 3 else 5
        color = C_WHITE if j == 3 else C_ACCENT_LITE
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    return img


# ── 메인 ─────────────────────────────────────────────────────────────────────
def generate_cardnews(keyword: str, target_date: str | None = None) -> list[Path]:
    safe_kw = _safe_keyword(keyword)
    data_dir = ROOT / "data"

    if target_date:
        path = data_dir / f"analyzed_{safe_kw}_{target_date}.json"
        if not path.exists():
            print(f"[ERROR] 파일 없음: {path}", file=sys.stderr)
            sys.exit(1)
    else:
        matches = sorted(data_dir.glob(f"analyzed_{safe_kw}_*.json"), reverse=True)
        if not matches:
            print(f"[ERROR] analyzed_{safe_kw}_*.json 파일이 없습니다.", file=sys.stderr)
            sys.exit(1)
        path = matches[0]

    print(f"[cardnews] 데이터: {path.name}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    file_date = target_date or date.today().isoformat()
    makers = [make_slide1, make_slide2, make_slide3, make_slide4]
    saved: list[Path] = []

    for i, make_fn in enumerate(makers, start=1):
        img = make_fn(data)
        out = output_dir / f"cardnews_{safe_kw}_{file_date}_{i}.png"
        img.save(str(out))
        print(f"  [{i}/4] {out.name}")
        saved.append(out)

    return saved


def _out(msg: str) -> None:
    sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="카드뉴스 이미지 생성기")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (생략 시 최신 파일)")
    args = parser.parse_args()

    _out(f"[cardnews] 키워드: {args.keyword}")
    paths = generate_cardnews(args.keyword, args.date)
    _out(f"[cardnews] 완료 - {len(paths)}장 생성")
    for p in paths:
        _out(f"  -> {p}")


if __name__ == "__main__":
    main()
