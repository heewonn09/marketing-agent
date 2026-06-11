import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent

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
        y += bh + 20

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
    title_font = _find_font(36, bold=True)
    desc_font  = _find_font(28)
    brand_font = _find_font(26)

    item_y_starts = [168, 428, 688]   # 3개 항목 고정 y

    for i, trend in enumerate(trends):
        y0 = item_y_starts[i]

        # 번호 원
        cx, cy, cr = MARGIN + 34, y0 + 34, 34
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=C_PURPLE)
        num_str = str(i + 1)
        nw = int(draw.textlength(num_str, font=num_font))
        draw.text((cx - nw // 2, cy - 22), num_str, font=num_font, fill=C_WHITE)

        # 제목: 콜론 앞 또는 첫 24자
        if ":" in trend:
            title_raw = trend.split(":")[0].strip()
        else:
            title_raw = trend[:24]
        title_text = (title_raw[:22] + "…") if len(title_raw) > 22 else title_raw

        tx = MARGIN + 86
        draw.text((tx, y0 + 6), title_text, font=title_font, fill=C_DARK)

        # 설명: 2줄
        desc_lines = _wrap(trend, desc_font, SIZE - tx - MARGIN)[:2]
        dy = y0 + 54
        for line in desc_lines:
            draw.text((tx, dy), line, font=desc_font, fill=C_MID)
            dy += 36

        # 구분선
        if i < 2:
            lx_start = MARGIN + 86
            draw.line([(lx_start, y0 + 220), (SIZE - MARGIN, y0 + 220)],
                      fill=C_DIVIDER, width=1)

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

        # 이유 (짧게)
        if reason:
            short = (reason[:34] + "…") if len(reason) > 34 else reason
            draw.text((MARGIN + 22, cy + card_h - 36), short,
                      font=reason_font, fill=C_MID)

    # 하단 메시지
    _draw_centered(draw, SIZE - 68, "매주 월요일 네이버 실시간 데이터 업데이트",
                   _find_font(28), C_PURPLE)
    _draw_centered(draw, SIZE - 34, "@auto.markai", _find_font(24), C_MID)

    return img


# ── 슬라이드 4: CTA ──────────────────────────────────────────────────────────
def make_slide4(data: dict) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE))
    _gradient_bg(img, C_GRAD_BTM, C_GRAD_TOP)
    draw = ImageDraw.Draw(img)

    # 중앙 박스
    bx, by, bw, bh = 90, 260, SIZE - 180, 460
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=24,
                            fill=(90, 60, 140), outline=C_WHITE, width=2)

    # 상단 문구
    _draw_centered(draw, 140, "팔로우하면", _find_font(36), C_ACCENT_LITE)
    _draw_centered(draw, 190, "마케팅 인사이트가 자동으로", _find_font(44, bold=True), C_WHITE)

    # 박스 내 텍스트
    y = by + 80
    y = _draw_centered(draw, y, "매주 월요일", _find_font(54, bold=True), C_WHITE)
    y = _draw_centered(draw, y + 4, "네이버 데이터 분석", _find_font(40), C_ACCENT_LITE)
    y += 50
    _draw_centered(draw, y, "@auto.markai 팔로우", _find_font(52, bold=True), C_WHITE)

    # 하단 점 인디케이터
    for j in range(4):
        cx = SIZE // 2 - 54 + j * 36
        cy = SIZE - 72
        r = 8 if j == 0 else 5
        color = C_WHITE if j == 0 else C_ACCENT_LITE
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
