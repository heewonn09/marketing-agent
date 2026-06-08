import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def find_analyzed_file(keyword: str, data_dir: Path) -> Path:
    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    pattern = f"analyzed_{safe_keyword}_*.json"
    matches = sorted(data_dir.glob(pattern), reverse=True)
    if not matches:
        print(
            f"오류: '{pattern}' 파일을 {data_dir}에서 찾을 수 없습니다.\n"
            "먼저 에이전트 2(analyzer)를 실행해 analyzed 파일을 생성하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="마케팅 콘텐츠 생성기 (에이전트 3)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--keyword", help="키워드 (data/analyzed_<키워드>_*.json 자동 탐색)")
    group.add_argument("--input", help="analyzed JSON 파일 경로 직접 지정")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.parent

    if args.input:
        input_path = Path(args.input)
    else:
        input_path = find_analyzed_file(args.keyword, project_root / "data")

    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"입력 파일: {input_path}")

    with open(input_path, encoding="utf-8") as f:
        analyzed_data = json.load(f)

    keyword = analyzed_data.get("keyword", args.keyword or "unknown")
    print(f"키워드 '{keyword}' 콘텐츠 생성 중...")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from agents.writer.generator import generate_content
    content = generate_content(analyzed_data)

    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    safe_keyword = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = output_dir / f"content_{safe_keyword}_{date_str}.json"

    result = {
        "keyword": keyword,
        "generated_at": datetime.now().isoformat(),
        "source_file": input_path.name,
        **content,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    def safe_print(text):
        print(text.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))

    safe_print(f"생성 완료 → {output_path}")
    safe_print(f"  네이버 블로그 제목: {content['naver_blog']['title']}")
    safe_print(f"  인스타 캡션: {content['instagram']['caption'][:50]}...")
    safe_print(f"  광고 헤드라인: {content['ad_copy']['headline']}")


if __name__ == "__main__":
    main()
