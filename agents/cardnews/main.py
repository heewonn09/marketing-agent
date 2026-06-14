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
C_PURPLE_LITE = (240, 235, 255)   # 연보라 배경
C_PURPLE_CARD = (250, 248, 255)
C_WHITE       = (255, 255, 255)
C_DARK        = ( 30,  20,  60)
C_MID         = ( 90,  70, 130)
C_ACCENT_LITE = (220, 200, 255)
C_DIVIDER     = (220, 215, 240)

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


# ── 슬라이드 1: 메인 타이틀 ─────────────────────────────────────────────────
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

    search_trends = data.get("search_trends", [])
    change_rate = ""
    if search_trends:
        cr = search_trends[0].get("change_rate", "")
        if cr:
            arrow = "↑" if cr.startswith("+") else "↓"
            change_rate = f"검색량 {cr} {arrow}"

    # 상단 레이블
    draw.text((MARGIN, MARGIN), "마케팅 인사이트", font=_find_font(32), fill=C_ACCENT_LITE)

    # 키워드 (큰 텍스트, 줄바꿈)
    kw_font = _find_font(76, bold=True)
    lines = _wrap(keyword, kw_font, SIZE - MARGIN * 2)
    y = 200
    for line in lines:
        y = _draw_centered(draw, y, line, kw_font, C_WHITE)

    # 검색량 변화율 배지
    if change_rate:
        y += 20
        badge_font = _find_font(46, bold=True)
        tw = int(draw.textlength(change_rate, font=badge_font))
        bw, bh = tw + 64, 72
        bx = (SIZE - bw) // 2
        draw.rounded_rectangle([bx, y, bx + bw, y + bh], radius=14,
                                fill=C_PURPLE_LITE, outline=C_WHITE, width=2)
        draw.text((bx + 32, y + 12), change_rate, font=badge_font, fill=C_PURPLE)
        y += bh + 44

    # ── 핵심 지표 패널 ──
    sentiment_counts = {"긍정": 0, "중립": 0, "부정": 0}
    for p in data.get("posts_sentiment", []):
        s = p.get("sentiment", "중립")
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1
    total_s = sum(sentiment_counts.values()) or 1
    positive_pct = sentiment_counts["긍정"] * 100 // total_s

    int_counts = {"높음": 0, "중간": 0, "낮음": 0}
    for item in data.get("interest_estimation", []):
        lv = item.get("level", "중간")
        int_counts[lv] = int_counts.get(lv, 0) + 1
    interest_level = max(int_counts, key=int_counts.get) if any(int_counts.values()) else "중간"
    competition_level = data.get("competition_saturation", {}).get("level", "미확인")

    panel_h = 128
    draw.rounded_rectangle([MARGIN, y, SIZE - MARGIN, y + panel_h],
                            radius=18, fill=(80, 50, 140))

    stats = [("관심도", interest_level), ("경쟁강도", competition_level), ("긍정반응", f"{positive_pct}%")]
    label_font = _find_font(24)
    val_font = _find_font(36, bold=True)
    col_w = (SIZE - MARGIN * 2) // 3
    for si, (label, value) in enumerate(stats):
        col_x = MARGIN + col_w * si
        lw = int(draw.textlength(label, font=label_font))
        draw.text((col_x + (col_w - lw) // 2, y + 18), label, font=label_font, fill=C_ACCENT_LITE)
        vw = int(draw.textlength(value, font=val_font))
        draw.text((col_x + (col_w - vw) // 2, y + 54), value, font=val_font, fill=C_WHITE)
        if si < 2:
            draw.line([(col_x + col_w, y + 20), (col_x + col_w, y + panel_h - 20)],
                      fill=(150, 120, 200), width=1)

    y += panel_h + 36

    # ── 핵심 인사이트 2줄 ──
    insights = data.get("insights", [])
    insight_font = _find_font(28)
    for insight in insights[:2]:
        ilines = _wrap(insight, insight_font, SIZE - MARGIN * 2)
        itext = (ilines[0] + "…") if len(ilines) > 1 else (ilines[0] if ilines else "")
        if itext:
            iw = int(draw.textlength(itext, insight_font))
            draw.text(((SIZE - iw) // 2, y), itext, font=insight_font, fill=C_ACCENT_LITE)
            y += 40

    # ── 트렌드 요약 ──
    trend_summary = data.get("trend_summary", "")
    if trend_summary and y < SIZE - 220:
        y += 28
        draw.line([(MARGIN + 100, y), (SIZE - MARGIN - 100, y)], fill=(150, 120, 200), width=1)
        y += 22
        ts_font = _find_font(26)
        ts_all = _wrap(trend_summary, ts_font, SIZE - MARGIN * 2)
        ts_lines = ts_all[:2]
        for ti, tline in enumerate(ts_lines):
            if ti == 1 and len(ts_all) > 2:
                tline = tline + "…"
            tw = int(draw.textlength(tline, ts_font))
            draw.text(((SIZE - tw) // 2, y), tline, font=ts_font, fill=(200, 180, 240))
            y += 36

    # 날짜
    draw.text(
        (MARGIN, SIZE - MARGIN - 40),
        date_str,
        font=_find_font(30),
        fill=C_ACCENT_LITE,
    )
    # 하단 라인
    draw.line([(MARGIN, SIZE - MARGIN), (SIZE - MARGIN, SIZE - MARGIN)],
              fill=C_ACCENT_LITE, width=2)

    return img


# ── 슬라이드 2: 트렌드 TOP 3 ─────────────────────────────────────────────────
def make_slide2(data: dict) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), C_WHITE)
    draw = ImageDraw.Draw(img)

    # 헤더 바
    draw.rectangle([0, 0, SIZE, 138], fill=C_PURPLE)
    _draw_centered(draw, 42, "이번 주 트렌드 TOP 3", _find_font(52, bold=True), C_WHITE)

    trends = data.get("trends", [])[:3]
    num_font   = _find_font(38, bold=True)
    title_font = _find_font(30, bold=True)
    desc_font  = _find_font(26)
    brand_font = _find_font(26)

    card_h = 228
    gap = 18
    card_starts = [152, 152 + card_h + gap, 152 + (card_h + gap) * 2]

    for i, trend in enumerate(trends):
        y0 = card_starts[i]

        # 카드 배경
        draw.rounded_rectangle([MARGIN, y0, SIZE - MARGIN, y0 + card_h],
                                radius=14, fill=C_PURPLE_CARD, outline=C_DIVIDER, width=1)

        # 번호 원
        cx, cy, cr = MARGIN + 46, y0 + 40, 32
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=C_PURPLE)
        num_str = str(i + 1)
        nw = int(draw.textlength(num_str, font=num_font))
        draw.text((cx - nw // 2, cy - 20), num_str, font=num_font, fill=C_WHITE)

        # 제목
        if ":" in trend:
            title_raw = trend.split(":")[0].strip()
        else:
            title_raw = trend[:40]

        tx = MARGIN + 96
        title_lines = _wrap(title_raw, title_font, SIZE - tx - MARGIN - 12)[:2]
        ty = y0 + 14
        for line in title_lines:
            draw.text((tx, ty), line, font=title_font, fill=C_DARK)
            ty += 38

        # 카드 내 구분선
        draw.line([(MARGIN + 16, ty + 6), (SIZE - MARGIN - 16, ty + 6)],
                  fill=C_DIVIDER, width=1)

        # 설명: 원본 텍스트 최대 3줄 (Gemini 요약 없이 자연스럽게 wrap)
        if ":" in trend:
            desc_raw = trend.split(":", 1)[1].strip()
        else:
            desc_raw = trend
        desc_lines = _wrap(desc_raw, desc_font, SIZE - MARGIN * 2 - 40)[:3]
        dy = ty + 18
        for line in desc_lines:
            draw.text((MARGIN + 24, dy), line, font=desc_font, fill=C_MID)
            dy += 34

    # 브랜드
    _draw_centered(draw, SIZE - 52, "@auto.markai", brand_font, C_PURPLE)

    return img


# ── 슬라이드 3: 다음 주 추천 키워드 ─────────────────────────────────────────
def make_slide3(data: dict) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), C_PURPLE_LITE)
    draw = ImageDraw.Draw(img)

    # 헤더 바
    draw.rectangle([0, 0, SIZE, 138], fill=C_PURPLE)
    _draw_centered(draw, 42, "다음 주 공략 키워드", _find_font(52, bold=True), C_WHITE)

    next_kws = data.get("next_week_keywords", [])[:3]
    kw_font     = _find_font(38, bold=True)
    reason_font = _find_font(26)
    num_font    = _find_font(28, bold=True)
    card_colors = [C_PURPLE, C_PURPLE_MID, (140, 100, 200)]

    card_y_starts = [176, 416, 656]
    card_h = 196

    for i, item in enumerate(next_kws):
        kw     = item.get("keyword", "") if isinstance(item, dict) else item
        reason = item.get("reason", "")   if isinstance(item, dict) else ""

        cy = card_y_starts[i]
        # 카드 배경
        draw.rounded_rectangle([MARGIN, cy, SIZE - MARGIN, cy + card_h],
                                radius=18, fill=C_WHITE)
        # 왼쪽 컬러 바
        draw.rounded_rectangle([MARGIN, cy, MARGIN + 8, cy + card_h],
                                radius=4, fill=card_colors[i])

        # 번호
        num_str = f"0{i + 1}"
        draw.text((MARGIN + 22, cy + 20), num_str,
                  font=num_font, fill=card_colors[i])

        # 키워드
        kw_lines = _wrap(kw, kw_font, SIZE - MARGIN * 2 - 60)[:2]
        ky = cy + 56
        for line in kw_lines:
            draw.text((MARGIN + 22, ky), line, font=kw_font, fill=C_DARK)
            ky += 48

        # 이유: wrap으로 최대 2줄 표시 (34자 하드컷 제거)
        if reason:
            reason_lines = _wrap(reason, reason_font, SIZE - MARGIN * 2 - 60)[:2]
            ry = cy + card_h - 36 - (len(reason_lines) - 1) * 30
            for rline in reason_lines:
                draw.text((MARGIN + 22, ry), rline, font=reason_font, fill=C_MID)
                ry += 30

    # 하단 메시지
    _draw_centered(draw, SIZE - 68, "매주 월요일 네이버 실시간 데이터 업데이트",
                   _find_font(28), C_PURPLE)
    _draw_centered(draw, SIZE - 34, "@auto.markai", _find_font(24), C_MID)

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
    check_font  = _find_font(30, bold=True)
    for benefit in benefits:
        # 체크 아이콘 (좌측 고정)
        draw.text((bx + 44, y), "v", font=check_font, fill=(160, 230, 140))
        draw.text((bx + 88, y), benefit, font=bullet_font, fill=C_WHITE)
        y += 56

    y += 20
    # 구분선 2
    draw.line([(bx + 56, y), (bx + bw - 56, y)], fill=(200, 180, 255), width=1)
    y += 40

    # CTA 버튼 스타일
    cta_font = _find_font(44, bold=True)
    _draw_centered(draw, y, f"{ig_username} 팔로우", cta_font, C_WHITE)

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
