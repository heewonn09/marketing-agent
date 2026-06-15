import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import google.genai as genai
from google.genai import types
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))
from utils.gemini_retry import gemini_retry

CLIENT = None


def _client() -> genai.Client:
    global CLIENT
    if CLIENT is None:
        CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return CLIENT


def _safe_keyword(keyword: str) -> str:
    return re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)


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
                # 4개 보장
                while len(prompts) < 4:
                    prompts.append(prompts[0])
                return prompts[:4]
        except json.JSONDecodeError:
            pass

    # 파싱 실패 시 기본 프롬프트
    base = (
        f"Professional Korean marketing promotional image for '{keyword}', "
        "modern minimalist style, bright clean background, no text, "
        "4:5 portrait ratio, high quality"
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Imagen 3 홍보 이미지 생성기")
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

    # Imagen 3 이미지 생성
    print("[promo-image] Imagen 3 이미지 생성 중 (4장)...")
    saved = []
    for i, prompt in enumerate(prompts, 1):
        print(f"  [{i}/4] 생성 중...")
        img_bytes = _generate_image(prompt, i)
        if img_bytes:
            out = output_dir / f"cardnews_{safe_kw}_{file_date}_{i}.png"
            out.write_bytes(img_bytes)
            print(f"  [{i}/4] 저장 완료: {out.name}")
            saved.append(out)
        else:
            print(f"  [{i}/4] 건너뜀")

    if saved:
        print(f"[promo-image] 완료 - {len(saved)}장 저장")
    else:
        print("[ERROR] 이미지를 하나도 생성하지 못했습니다.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
