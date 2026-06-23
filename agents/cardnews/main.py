import argparse
import base64
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import google.genai as genai
from google.genai import types
from dotenv import load_dotenv
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))
from utils.gemini_retry import gemini_retry

CLIENT = None
_FONT_DIR = ROOT / "assets" / "fonts"


def _client() -> genai.Client:
    global CLIENT
    if CLIENT is None:
        CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return CLIENT


def _safe_keyword(keyword: str) -> str:
    return re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)


def _font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    name_map = {
        "regular": "NanumGothic-Regular.ttf",
        "bold":    "NanumGothic-Bold.ttf",
        "xl":      "NanumGothic-ExtraBold.ttf",
    }
    try:
        return ImageFont.truetype(str(_FONT_DIR / name_map[weight]), size)
    except Exception:
        return ImageFont.load_default()


def _shadow_text(draw: ImageDraw.ImageDraw, x: int, y: int, text: str,
                 font: ImageFont.FreeTypeFont,
                 color=(255, 255, 255, 255),
                 shadow=(0, 0, 0, 160)) -> int:
    """그림자 포함 텍스트 렌더링, 텍스트 높이 반환."""
    draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=color)
    bbox = draw.textbbox((x, y), text, font=font)
    return bbox[3] - bbox[1]


def _wrap_korean(draw: ImageDraw.ImageDraw, text: str,
                 font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """한국어 포함 텍스트 줄바꿈 (글자 단위)."""
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        w = draw.textbbox((0, 0), test, font=font)[2]
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _gradient_banner(draw: ImageDraw.ImageDraw, x0: int, y0: int,
                     x1: int, y1: int, top_alpha: int, bottom_alpha: int) -> None:
    """수직 그라디언트 반투명 배너."""
    h = y1 - y0
    for dy in range(h):
        a = int(top_alpha + (bottom_alpha - top_alpha) * dy / max(h - 1, 1))
        draw.rectangle([(x0, y0 + dy), (x1, y0 + dy + 1)], fill=(0, 0, 0, a))


def _apply_overlay(img_bytes: bytes, slide_idx: int,
                   data: dict, keyword: str, file_date: str) -> bytes:
    """Imagen 4 raw 이미지에 슬라이드별 마케팅 텍스트 오버레이 적용."""
    import io
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    W, H = img.size

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    PAD       = W // 18
    BANNER_H  = H // 5
    LINE_GAP  = W // 55

    # 폰트 크기 (이미지 너비 기준)
    SZ_LABEL = max(22, W // 34)
    SZ_BODY  = max(26, W // 28)
    SZ_TITLE = max(38, W // 18)
    SZ_XL    = max(50, W // 13)

    # ── 상단 배너 (위 불투명 → 아래 투명) ──────────────────────────────────
    _gradient_banner(draw, 0, 0, W, BANNER_H, top_alpha=210, bottom_alpha=0)
    # ── 하단 배너 (위 투명 → 아래 불투명) ──────────────────────────────────
    _gradient_banner(draw, 0, H - BANNER_H, W, H, top_alpha=0, bottom_alpha=220)

    ACCENT_GREEN  = (120, 255, 160, 255)
    ACCENT_AMBER  = (255, 210, 80,  255)
    ACCENT_BLUE   = (140, 210, 255, 255)
    WHITE         = (255, 255, 255, 255)
    WHITE_DIM     = (200, 200, 200, 210)

    MAX_TEXT_W = W - PAD * 2  # 텍스트 최대 폭 (좌우 패딩 제외)

    def _fit_text(text: str, font: ImageFont.FreeTypeFont) -> str:
        """텍스트가 MAX_TEXT_W를 초과하면 픽셀 기준으로 잘라 '…' 추가."""
        if draw.textbbox((0, 0), text, font=font)[2] <= MAX_TEXT_W:
            return text
        while text and draw.textbbox((0, 0), text + "…", font=font)[2] > MAX_TEXT_W:
            text = text[:-1]
        return text + "…"

    # ────────────────────────────────────────────────────────────────────────
    # 슬라이드 1 — 커버 (키워드 대제목 + 트렌드 요약)
    # ────────────────────────────────────────────────────────────────────────
    if slide_idx == 1:
        # 상단: 레이블 + 키워드 (픽셀 폭 기준으로 잘림 방지)
        y = PAD
        y += _shadow_text(draw, PAD, y, "📊  마케팅 트렌드 분석",
                          _font(SZ_LABEL, "bold"), ACCENT_GREEN) + LINE_GAP
        kw_display = _fit_text(f"#{keyword}", _font(SZ_XL, "xl"))
        y += _shadow_text(draw, PAD, y, kw_display,
                          _font(SZ_XL, "xl"), WHITE) + LINE_GAP * 2
        # 키워드 아래: 관련 키워드 태그 (소)
        kws = [k.get("word", "") for k in data.get("keywords", [])[:3]]
        if kws:
            tags_line = _fit_text("  ".join(f"#{w}" for w in kws), _font(SZ_LABEL, "regular"))
            _shadow_text(draw, PAD, y, tags_line,
                         _font(SZ_LABEL, "regular"), WHITE_DIM)

        # 하단: 트렌드 요약 (최대 2줄, 픽셀 폭 기준 wrapping)
        summary = data.get("trend_summary", "")
        lines = _wrap_korean(draw, summary, _font(SZ_BODY, "regular"), MAX_TEXT_W)[:2]
        y_b = H - BANNER_H + PAD // 2
        for line in lines:
            y_b += _shadow_text(draw, PAD, y_b, line,
                                _font(SZ_BODY, "regular"), WHITE) + LINE_GAP

        # 날짜 (우하단)
        date_txt = file_date
        date_font = _font(SZ_LABEL - 4, "regular")
        date_w = draw.textbbox((0, 0), date_txt, font=date_font)[2]
        _shadow_text(draw, W - date_w - PAD, H - PAD - SZ_LABEL,
                     date_txt, date_font, WHITE_DIM)

    # ────────────────────────────────────────────────────────────────────────
    # 슬라이드 2 — 주요 트렌드 3가지
    # ────────────────────────────────────────────────────────────────────────
    elif slide_idx == 2:
        # 상단
        y = PAD
        y += _shadow_text(draw, PAD, y, "🔥  지금 주목해야 할 트렌드",
                          _font(SZ_LABEL, "bold"), ACCENT_AMBER) + LINE_GAP
        _shadow_text(draw, PAD, y, _fit_text(keyword, _font(SZ_TITLE, "bold")),
                     _font(SZ_TITLE, "bold"), WHITE)

        # 하단: 트렌드 핵심 문구 1줄씩 — 픽셀 폭 기준으로 잘림 처리
        trends = [str(t) for t in data.get("trends", [])[:3]]
        y_b = H - BANNER_H + PAD // 2
        for t in trends:
            short = t.split(".")[0].split("：")[0].split(":")[0].strip()
            short = _fit_text(f"• {short}", _font(SZ_BODY, "bold"))
            y_b += _shadow_text(draw, PAD, y_b, short,
                                _font(SZ_BODY, "bold"), WHITE) + LINE_GAP

    # ────────────────────────────────────────────────────────────────────────
    # 슬라이드 3 — 핵심 인사이트
    # ────────────────────────────────────────────────────────────────────────
    elif slide_idx == 3:
        # 상단
        y = PAD
        y += _shadow_text(draw, PAD, y, "💡  핵심 인사이트",
                          _font(SZ_LABEL, "bold"), ACCENT_BLUE) + LINE_GAP
        _shadow_text(draw, PAD, y, _fit_text(keyword, _font(SZ_TITLE, "bold")),
                     _font(SZ_TITLE, "bold"), WHITE)

        # 하단: 인사이트 핵심 문구 1줄씩 — 픽셀 폭 기준으로 잘림 처리
        insights = [str(ins) for ins in data.get("insights", [])[:3]]
        y_b = H - BANNER_H + PAD // 2
        for ins in insights:
            short = ins.split(".")[0].split("：")[0].split(":")[0].strip()
            short = _fit_text(f"▶  {short}", _font(SZ_BODY, "bold"))
            y_b += _shadow_text(draw, PAD, y_b, short,
                                _font(SZ_BODY, "bold"), WHITE) + LINE_GAP

    # ────────────────────────────────────────────────────────────────────────
    # 슬라이드 4 — CTA (팔로우 유도)
    # ────────────────────────────────────────────────────────────────────────
    elif slide_idx == 4:
        # 상단: 브랜드 + 슬로건
        y = PAD
        y += _shadow_text(draw, PAD, y, "✨  @auto.markai",
                          _font(SZ_LABEL, "bold"), ACCENT_GREEN) + LINE_GAP
        y += _shadow_text(draw, PAD, y, "마케팅 자동화",
                          _font(SZ_XL, "xl"), WHITE) + LINE_GAP // 2
        _shadow_text(draw, PAD, y, "트렌드 분석 에이전트",
                     _font(SZ_TITLE - 4, "bold"), WHITE_DIM)

        # 하단: 팔로우 CTA + 해시태그 (최대 폭 초과 시 키워드 수 축소)
        y_b = H - BANNER_H + PAD // 2
        y_b += _shadow_text(draw, PAD, y_b, "팔로우하고 매일 트렌드를 받아보세요 →",
                            _font(SZ_BODY, "bold"), ACCENT_GREEN) + LINE_GAP
        kws = [k.get("word", "") for k in data.get("keywords", [])[:5]]
        if kws:
            tag_font = _font(SZ_LABEL, "regular")
            # 태그가 MAX_TEXT_W를 초과하면 키워드 수를 하나씩 줄임
            while kws:
                tags = "  ".join(f"#{w}" for w in kws)
                if draw.textbbox((0, 0), tags, font=tag_font)[2] <= MAX_TEXT_W:
                    break
                kws = kws[:-1]
            if kws:
                _shadow_text(draw, PAD, y_b, tags,
                             tag_font, WHITE_DIM)

    # ── 합성 ────────────────────────────────────────────────────────────────
    result = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@gemini_retry
def _generate_prompts(data: dict, keyword: str) -> list:
    """분석 데이터 → 인스타 홍보 이미지 영문 프롬프트 4개 생성"""
    trend_summary = data.get("trend_summary", "")
    trends        = data.get("trends", [])[:3]
    kw_list       = [k.get("word", "") for k in data.get("keywords", [])[:5]]

    system_prompt = f"""You are a professional Instagram marketing image designer.
Based on the following Korean marketing trend data, generate 4 distinct promotional image prompts in English.

Keyword (Korean): {keyword}
Trend summary: {trend_summary}
Key trends: {", ".join(str(t) for t in trends)}
Related keywords: {", ".join(kw_list)}

Requirements for each prompt:
- 3:4 portrait format (Instagram feed optimized)
- CRITICAL: absolutely no text, no letters, no words, no numbers, no Korean characters, no Latin characters, no symbols of any kind
- Modern, trendy aesthetic with clean visual communication
- Different visual angles: (1) flat design with icons/shapes only, (2) lifestyle scene without readable signage, (3) abstract/geometric, (4) product/brand mood
- Bright, clean, professional look suitable for business marketing
- High quality, photorealistic or premium illustration style
- If showing UI/screens, display only blurred or abstract patterns, never readable text

Output ONLY a valid JSON array of 4 strings:
["prompt1", "prompt2", "prompt3", "prompt4"]"""

    resp = _client().models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=system_prompt,
    )

    text = resp.text.strip()
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            prompts = json.loads(match.group())
            if isinstance(prompts, list) and len(prompts) >= 1:
                while len(prompts) < 4:
                    prompts.append(prompts[0])
                return prompts[:4]
        except json.JSONDecodeError:
            pass

    base = (
        f"Professional Korean marketing promotional image for '{keyword}', "
        "modern minimalist style, bright clean background, no text, "
        "3:4 portrait ratio, high quality"
    )
    return [base, base, base, base]


def _generate_image(prompt: str, index: int, max_retries: int = 3) -> bytes | None:
    """Imagen 4로 이미지 1장 생성 -> PNG bytes 반환 (빈 응답 시 재시도)"""
    import time
    for attempt in range(1, max_retries + 1):
        try:
            response = _client().models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="3:4",
                    safety_filter_level="BLOCK_LOW_AND_ABOVE",
                    person_generation="ALLOW_ADULT",
                ),
            )
            if response.generated_images:
                return response.generated_images[0].image.image_bytes
            print(f"  [{index}/4] empty response (attempt {attempt}/{max_retries}), retrying...")
            time.sleep(2)
        except Exception as e:
            print(f"  [{index}/4] failed (attempt {attempt}/{max_retries}): {e}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(3)
    print(f"  [{index}/4] failed after {max_retries} attempts", file=sys.stderr)
    return None


def _upload_to_imgbb(filepath: Path, api_key: str) -> str | None:
    """imgbb.com에 이미지를 업로드하고 직접 링크(HTTPS)를 반환."""
    try:
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": api_key, "image": b64, "name": filepath.stem},
            timeout=30,
        )
        if res.ok:
            return res.json()["data"]["url"]
        print(f"  [imgbb] 업로드 실패 {res.status_code}: {res.text[:120]}", file=sys.stderr)
    except Exception as e:
        print(f"  [imgbb] 업로드 오류: {e}", file=sys.stderr)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Imagen 4 홍보 이미지 생성기 (오버레이 포함)")
    parser.add_argument("--keyword",  required=True)
    parser.add_argument("--date", dest="target_date", default=None)
    args = parser.parse_args()

    keyword     = args.keyword
    target_date = args.target_date
    safe_kw     = _safe_keyword(keyword)
    data_dir    = ROOT / "data"

    # 분석 파일 탐색
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

    print(f"[promo-image] 데이터: {path.name}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    file_date = target_date or date.today().isoformat()

    # 프롬프트 생성
    print("[promo-image] 이미지 프롬프트 생성 중...")
    prompts = _generate_prompts(data, keyword)
    for i, p in enumerate(prompts, 1):
        print(f"  프롬프트 {i}: {p[:90]}...")

    # Imagen 4 이미지 생성 + 오버레이 적용
    print("[promo-image] Imagen 4 이미지 생성 + 오버레이 적용 중 (4장)...")
    saved = []
    for i, prompt in enumerate(prompts, 1):
        print(f"  [{i}/4] 생성 중...")
        raw_bytes = _generate_image(prompt, i)
        if raw_bytes:
            print(f"  [{i}/4] 오버레이 적용 중...")
            try:
                final_bytes = _apply_overlay(raw_bytes, i, data, keyword, file_date)
            except Exception as e:
                print(f"  [{i}/4] 오버레이 실패 ({e}) — 원본 사용", file=sys.stderr)
                final_bytes = raw_bytes
            out = output_dir / f"cardnews_{safe_kw}_{file_date}_{i}.png"
            out.write_bytes(final_bytes)
            print(f"  [{i}/4] 저장 완료: {out.name}")
            saved.append(out)
        else:
            print(f"  [{i}/4] 건너뜀")

    if not saved:
        print("[ERROR] 이미지를 하나도 생성하지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"[promo-image] 완료 - {len(saved)}장 저장 (오버레이 적용됨)")

    # imgbb 업로드: IMGBB_API_KEY 설정 시 HTTPS URL 파일 생성
    imgbb_key = os.environ.get("IMGBB_API_KEY", "").strip()
    if imgbb_key:
        print("[promo-image] imgbb 업로드 중 (Instagram HTTPS 이미지 호스팅)...")
        urls: dict[str, str] = {}
        for i, p in enumerate(saved, 1):
            url = _upload_to_imgbb(p, imgbb_key)
            if url:
                urls[str(i)] = url
                print(f"  [{i}/4] imgbb URL: {url}")
            else:
                print(f"  [{i}/4] 업로드 실패 — CARDNEWS_BASE_URL 폴백 사용")
        if urls:
            urls_path = output_dir / f"cardnews_urls_{safe_kw}_{file_date}.json"
            with open(urls_path, "w", encoding="utf-8") as f:
                json.dump(urls, f, ensure_ascii=False, indent=2)
            print(f"[promo-image] imgbb URL 저장: {urls_path.name}")


if __name__ == "__main__":
    main()
