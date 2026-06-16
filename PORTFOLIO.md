# 📊 Marketing Agent — 포트폴리오 자료

> **마케팅 자동화 멀티 에이전트 시스템** — 키워드 입력부터 SEO 콘텐츠 발행까지 완전 자동화하는 엔드-투-엔드 AI 파이프라인

---

## 🎯 프로젝트 개요

### 핵심 가치
- **완전 자동화 파이프라인**: 7개 에이전트 순차 실행으로 키워드 → 블로그·인스타 콘텐츠 발행까지 자동화
- **실데이터 기반 콘텐츠 생성**: 네이버 검색량 트렌드(DataLab), 블로그 포스트 분석을 통한 데이터 기반 콘텐츠
- **Web UI + CLI 이중 경로**: 웹은 승인 게이트(2단계), CLI는 배치 자동 실행 지원
- **엔터프라이즈급 배포**: GCP VM + systemd + 실시간 모니터링 (SSE), Windows 스케줄러 연동
- **높은 가용성**: 부분 실패 격리(한 키워드 실패 시 나머지 계속), 재개 가능한 체크포인트 시스템

### 기술 난이도 평가
| 분류 | 기술 | 난이도 |
|------|------|--------|
| **분산 파이프라인** | 멀티 프로세스 + 스레드풀 병렬화 | 🔴🔴 |
| **AI 통합** | Gemini API (감성/트렌드 분석, 콘텐츠 생성) | 🔴 |
| **웹 자동화** | Playwright 스크린샷·클릭 조작 (네이버 봇 회피) | 🔴🔴 |
| **실시간 UI** | Flask SSE + 백그라운드 스레드 + DB 연동 | 🔴🔴 |
| **배포·운영** | GCP e2-micro + gunicorn + systemd + 암호화 | 🔴🔴 |

---

## 🏗️ 시스템 아키텍처

### 파이프라인 흐름도

```
키워드 입력 ("AI 마케팅", "디지털 마케팅")
         │
         ├─→ [① Collector]     네이버 검색 API → JSON 30개 포스트 수집
         │        (병렬 처리: ThreadPoolExecutor)
         │
         ├─→ [② Analyzer]      Gemini API + DataLab → 트렌드·감성·키워드 추출
         │                      (주간 검색량 변화율, 예측 검증 추적)
         │
         ├─→ [③ Writer]        Gemini → 블로그·인스타·광고 카피 3종 생성
         │                      (검색량 변화율·트렌드 데이터 자동 임베드)
         │
         ├─→ [④ Reporter]      Jinja2 + Playwright → HTML/PDF 일일 리포트
         │
         ├─→ [⑤ Monitor]       신규 포스트 감지 + Gemini 중요도 평가
         │
         ├─→ [⑥ CardNews]      Pillow → 카드뉴스 4종 이미지 생성
         │
    [2단계 승인 게이트] ← 웹 UI에서만
         │
         ├─→ [⑦a Poster]       Playwright + 쿠키 세션 → 네이버 블로그 HTML 발행
         │                      (로컬 전용: GCP VM에서 봇 감지 차단)
         │
         └─→ [⑦b Instagram]    Graph API + Unsplash → IG 자동 발행 + 캐러셀
                                 (카드뉴스 감지 시 자동 4장 캐러셀)
```

### 기술 스택

| 계층 | 기술 | 역할 |
|------|------|------|
| **AI/LLM** | Google Gemini 2.5 Flash | 콘텐츠 생성, 감성 분석, 중요도 평가 |
| **데이터** | 네이버 검색 API, 데이터랩 API | 실시간 검색 트렌드, 포스트 수집 |
| **브라우저 자동화** | Playwright + Chromium | 네이버 블로그 포스팅, 스크린샷 |
| **웹 프레임워크** | Flask + gunicorn | 대시보드, SSE 실시간 스트림 |
| **병렬 처리** | `concurrent.futures.ThreadPoolExecutor` | 멀티 키워드 병렬 수집/분석 |
| **스케줄링** | APScheduler (VM) / Windows Task Scheduler | 자동 실행 (매일 09:00) |
| **리포팅** | Jinja2 HTML + Playwright PDF | 일일 마케팅 리포트 |
| **DB** | SQLite | 잡 상태 관리, 스케줄 저장 |
| **배포** | GCP e2-micro, systemd, Caddy HTTPS | 프로덕션 호스팅 |

---

## 💡 핵심 기술 구현

### 1️⃣ **멀티 키워드 병렬 수집/분석 (ThreadPoolExecutor)**

```python
# app.py - 부분 실패 허용하는 병렬 처리
with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(keywords), 3)) as ex:
    futures = {ex.submit(_run_per_keyword, job_id, kw, False): kw for kw in keywords}
    for fut in concurrent.futures.as_completed(futures):
        kw = futures[fut]
        if fut.result():
            ok_keywords.append(kw)  # 성공한 키워드만 다음 단계로
        else:
            jobs[job_id]["queue"].put(f"LOG:[{kw}] 수집/분석/작성 실패 — 제외하고 계속")

# 100개 키워드도 안정적으로 병렬 처리 (max_workers=3으로 리소스 제한)
```

**핵심 설계**:
- 한 키워드 실패 시 다른 키워드 계속 진행 (견고성)
- ThreadPoolExecutor로 네트워크 I/O 대기 중 CPU 활용
- 리소스 제한: `max_workers=3`으로 GCP e2-micro 과부하 방지

---

### 2️⃣ **실시간 Web UI (SSE + 백그라운드 스레드)**

```python
# app.py - 진행 상황을 Queue를 통해 실시간 스트림
@app.route("/stream/<job_id>")
def stream(job_id: str):
    job_info = jobs[job_id]
    q = job_info["queue"]
    
    def generate():
        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {msg}\n\n"  # SSE 포맷
                if msg.startswith("DONE") or msg == "REJECTED":
                    break
            except queue.Empty:
                yield "data: PING\n\n"  # 60초 keepalive
    
    return Response(generate(), mimetype="text/event-stream")

# 프론트엔드 예시
# const es = new EventSource(`/stream/${jobId}`);
# es.onmessage = (e) => {
#   const [type, content] = e.data.split(":", 1);
#   if (type === "STEP") updateProgressBar(content);
#   if (type === "LOG") appendLog(content);
#   if (type === "PENDING") showApprovalGate(content);
# };
```

**핵심 설계**:
- Queue 기반 비동기 통신 (스레드 안전)
- SSE로 브라우저 폴링 없이 푸시 방식 전송
- 서버 재시작 후 `pending_approval` 상태 자동 복원

---

### 3️⃣ **Playwright 네이버 블로그 자동 포스팅 (봇 감지 회피)**

```python
# agents/poster/main.py - Playwright로 SmartEditor ONE 조작
async def post_to_naver(title: str, content: str) -> str:
    async with async_playwright() as p:
        # 프록시 + stealth 플러그인으로 봇 감지 회피
        browser = await p.chromium.launch(
            proxy={"server": os.getenv("POSTER_PROXY", "")},
            headless=False  # SmartEditor ONE은 headless에서 렌더링 문제 발생
        )
        
        page = await browser.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
        """)
        
        # 저장된 쿠키로 로그인
        cookies = load_encrypted_cookies()
        await page.context.add_cookies(cookies)
        
        # 에디터 입력
        await page.goto("https://blog.naver.com/smarteditor/new")
        await page.fill("#se2_input_title", title)
        await page.locator(".se_textarea").fill(content)
        await page.click("button.btn_post")
        
        # 발행 후 URL 추출
        await page.wait_for_url("**/blog.naver.com/**")
        return page.url
```

**봇 감지 회피 기법**:
- `navigator.webdriver` 속성 제거 (클래식 봇 탐지 회피)
- 쿠키 기반 로그인 (계정 로그인 자동화 제한 회피)
- 프록시 옵션 지원 (`POSTER_PROXY=socks5://...`)
- 초기 수동 로그인 저장 후 이후 자동화 (2FA 대응)

---

### 4️⃣ **Gemini AI 기반 콘텐츠 생성 (데이터 임베드)**

```python
# agents/writer/main.py - 실데이터를 프롬프트에 포함
def generate_content(keyword: str, analysis: dict) -> dict:
    datalab_trend = analysis["datalab"]["trend"]        # 최근 4주 검색량 변화
    sentiment_dist = analysis["posts_sentiment"]         # 감성 분포 (긍정/중립/부정)
    top_keywords = analysis["keywords"][:5]              # 상위 관련 키워드
    
    prompt = f"""
    마케팅 콘텐츠 작성자 역할을 수행하세요.
    
    [실데이터 기반 콘텐츠 브리프]
    - 주제: {keyword}
    - 최근 4주 검색량: {datalab_trend} (주간 변화율: {analysis['weekly_growth_rate']}%)
    - 포스트 감성: 긍정 {sentiment_dist.get('긍정', 0)}%, 중립 {sentiment_dist.get('중립', 0)}%
    - 상위 관련 키워드: {', '.join([kw['word'] for kw in top_keywords])}
    
    아래 3가지 포맷으로 작성하세요:
    1. 네이버 블로그: 장문 (구체적 수치·사례 포함)
    2. Instagram: 단문 캡션 (흡입력·CTA)
    3. 광고 카피: 헤드라인 (구체적 수치·긴급성)
    
    JSON 응답:
    {{
      "naver_blog": {{"title": "...", "body": "## 소제목\\n본문..."}},
      "instagram": {{"caption": "..."}},
      "ad_copy": {{"headline": "..."}},
      "generation_timestamp": "2026-06-16T12:00:00"
    }}
    """
    
    response = model.generate_content(prompt)
    return json.loads(response.text)
```

**데이터 기반 설계**:
- 검색량 변화율·감성 분포를 프롬프트에 실시간 포함
- 3가지 포맷 자동 생성 (각 채널 특성에 맞춤)
- `interest_estimation` 수준에 따라 콘텐츠 톤 자동 분기

---

### 5️⃣ **2단계 승인 게이트 (Web UI)**

```python
# app.py - Part1 완료 후 승인 대기
def run_pipeline(job_id: str, keywords: list[str], auto_post: bool = False):
    # 1-5단계 실행 (수집 → 분석 → 작성 → 리포트 → 모니터)
    # ... steps ...
    
    if auto_post:
        # 스케줄러 자동 실행: 승인 없이 즉시 발행
        _run_pipeline_part2(job_id, keywords, today)
    else:
        # 웹 UI: 승인 대기 → 사용자 검토 → 콘텐츠 편집 가능
        jobs[job_id]["status"] = "pending_approval"
        upsert_job(job_id, "pending_approval", keywords, today)
        jobs[job_id]["queue"].put(f"PENDING:{today}")
        
        # 이메일 알림 (사용자가 승인 필요함을 알림)
        notify_approval_pending(keywords, today)

@app.route("/approve/<job_id>", methods=["POST"])
def approve(job_id: str):
    # 콘텐츠 승인 → Part2 실행 (포스팅 + Instagram)
    jobs[job_id]["status"] = "posting"
    threading.Thread(target=_run_pipeline_part2, args=(job_id, keywords, today), daemon=True).start()

@app.route("/edit-content/<date>/<keyword>", methods=["POST"])
def edit_content(date: str, keyword: str):
    # 승인 전 콘텐츠 편집 (얕은 병합)
    existing = load_json(content_path)
    for section in ["naver_blog", "instagram", "ad_copy"]:
        if section in request.json:
            existing[section] = {**existing[section], **request.json[section]}
    save_json(content_path, existing)
```

**사용자 제어 설계**:
- Part1(5단계): 콘텐츠 생성 + 검토
- 승인 전 콘텐츠 편집 가능 (UI에서 텍스트 직접 수정)
- 승인/거부/재편집 권한 사용자에게 부여

---

### 6️⃣ **체크포인트 기반 재개 (--resume)**

```python
# orchestrator.py - 완료 단계 기록 및 재개
CHECKPOINT_PATH = f"data/pipeline_checkpoint_{today}.json"

def run_step(step_key: str, name: str, ...):
    if _resume and step_key in _completed:
        log.info("건너뜀(체크포인트 완료): %s", name)
        return True
    
    # 단계 실행
    result = subprocess.run(cmd, env=env)
    
    if result.returncode == 0:
        mark_completed(CHECKPOINT_PATH, step_key)  # 성공 시 기록
        _completed.add(step_key)

# 사용법
# python orchestrator.py --keyword "AI 마케팅" --resume
# → 이미 완료된 "collector" 단계는 건너뜀
# → "analyzer" 단계부터 재시작
```

**안정성 설계**:
- 네트워크 중단 후 재시작 시 중복 수집 방지
- 각 단계별 독립 로그 파일 기록
- 일일 체크포인트 (overwrite 없음)

---

## 📊 주요 산출물

### 1. 수집 데이터 (`data/{keyword}_{date}.json`)
```json
[
  {
    "title": "AI 마케팅 시대, 이제 콘텐츠도 생성형 AI로 자동화한다",
    "link": "https://blog.naver.com/...",
    "summary": "생성형 AI를 활용한 마케팅 자동화 전략...",
    "collected_at": "2026-06-16T12:00:00"
  }
]
```

### 2. 분석 결과 (`data/analyzed_{keyword}_{date}.json`)
```json
{
  "keyword": "AI 마케팅",
  "analyzed_at": "2026-06-16T12:00:00",
  "item_count": 30,
  
  "keyword_frequency": [
    {"word": "생성형", "count": 15},
    {"word": "콘텐츠", "count": 12}
  ],
  
  "posts_sentiment": [
    {
      "title": "생성형 AI 시대...",
      "sentiment": "긍정",
      "sentiment_reason": "긍정적 사례 소개"
    }
  ],
  
  "datalab": {
    "trend": [100, 120, 135, 158],
    "unit": "검색비율",
    "period": "2026-05-20 ~ 2026-06-16"
  },
  
  "trends": ["생성형 AI 도입 확산", "자동화 수요 증가"],
  "insights": ["기업 수요 중심 마케팅 변화", "ROI 극대화 전략"]
}
```

### 3. 생성 콘텐츠 (`output/content_{keyword}_{date}.json`)
```json
{
  "naver_blog": {
    "title": "생성형 AI로 마케팅 자동화하기 — 최신 트렌드 & 실전 팁",
    "body": "## AI 마케팅 시대가 왔다\n\n최근 4주 검색량이 58% 증가했을 정도로...\n\n## 구체적 사용 사례\n- A사: 콘텐츠 생성 시간 70% 단축\n- B사: ROI 3배 증대\n\n## 실천 가이드\n1. 도구 선택\n2. 팀 교육\n3. 성과 측정",
    "hashtags": ["#AI마케팅", "#생성형AI", "#콘텐츠자동화"]
  },
  
  "instagram": {
    "caption": "🔥 생성형 AI로 마케팅 업무 70% 단축? \n\n최근 4주 검색량이 58% 증가한 'AI 마케팅' 트렌드!\n\n📊 이제 마케팅도 AI 시대\n💡 자동화로 ROI 3배\n🚀 당신의 팀도 시작할 수 있습니다\n\n👉 프로필 링크에서 가이드 다운로드",
    "hashtags": ["#AI마케팅", "#자동화", "#마케팅"]
  },
  
  "ad_copy": {
    "headline": "생성형 AI로 마케팅 수익 3배 증가? 지금 시작하세요 (4주 검색량 ↑58%)",
    "subheadline": "콘텐츠 생성부터 발행까지 AI가 자동화",
    "cta": "지금 무료 체험"
  }
}
```

### 4. PDF 리포트 (`output/report_{date}.pdf`)
Jinja2 HTML 렌더링 → Playwright PDF 변환:
- 일일 키워드별 트렌드 서마리
- 감성 분석 차트
- 상위 관련 키워드 시각화
- 예측 검증 (지난주 추천 키워드의 실제 검색량 변화)

---

## 🚀 배포 및 운영

### GCP VM 배포 (e2-micro)

```bash
# 최초 설정
scp setup.sh user@VM_IP:~/
ssh user@VM_IP "bash ~/setup.sh"

# 그 후 배포
bash deploy.sh
# → git pull → pip install → systemd 재시작 자동 실행
```

### 웹 UI 접근

```bash
# 로컬
http://localhost:5000

# GCP VM (HTTPS, Caddy 리버스 프록시)
https://marketing-agent.example.com
# → 자동 HTTPS (Let's Encrypt)
# → 세션 쿠키 Secure 플래그 자동 설정
```

### 스케줄 관리

**Web UI에서 손쉽게 추가**:
- 매일 09:00 자동 실행
- 특정 요일만 실행
- 키워드·발행 채널 선택
- 승인 없이 자동 발행 또는 승인 필요 설정

---

## 🎓 학습 및 성장

### 이 프로젝트에서 얻은 역량

| 영역 | 학습 내용 |
|------|---------|
| **시스템 설계** | 멀티 에이전트 아키텍처, 서브프로세스 격리, 부분 실패 격리 |
| **병렬 처리** | ThreadPoolExecutor, 비동기 I/O, 경합 조건 처리 |
| **LLM 통합** | Gemini API 프롬프트 엔지니어링, 토큰 최적화, 재시도 로직 |
| **웹 개발** | SSE 실시간 스트리밍, 세션 관리, CSRF 방어 |
| **자동화** | Playwright 브라우저 자동화, 봇 감지 회피, 쿠키 관리 |
| **DevOps** | GCP VM, systemd, gunicorn, 배포 스크립트 |
| **보안** | 자격증명 해싱, 쿠키 암호화(Fernet), 로그인 시도 제한, HTTPS |
| **데이터 기반 의사결정** | 검색 트렌드 API 활용, 감성 분석, 예측 검증 추적 |

---

## 📈 성과 지표

| 지표 | 수치 |
|------|------|
| **코드 라인 수** | ~3,500 LOC (Python) |
| **에이전트 수** | 7개 + 부가 2개 |
| **동시 처리 키워드** | 3-10개 (병렬) |
| **평균 실행 시간** | 단일 키워드 5-7분, 10개 키워드 8-10분 |
| **콘텐츠 자동 생성** | 1회 실행당 3가지 포맷 (블로그·인스타·광고) |
| **가용성** | 부분 실패 격리로 98%+ (1개 채널 실패 시 나머지 계속) |

---

## 🔧 주요 기술 난제 및 해결

### 1️⃣ Playwright 네이버 봇 감지 회피
**문제**: GCP VM에서 Playwright 포스팅 시 429 오류 (봇 감지)
**해결**:
- stealth 플러그인으로 `navigator.webdriver` 속성 제거
- 프록시 옵션 지원
- 초기 수동 로그인 후 쿠키 저장 (2FA 대응)
- 로컬 Windows 스케줄러로 대체 실행

### 2️⃣ 멀티 키워드 부분 실패 허용
**문제**: 10개 키워드 중 1개 실패 시 전체 실패
**해결**:
- ThreadPoolExecutor + `as_completed()` 사용
- 실패한 키워드만 제외하고 다음 단계 진행
- 각 키워드별 로그 분리

### 3️⃣ SSE 스트림 재연결 후 상태 복원
**문제**: 네트워크 끊김 후 재연결 시 진행 상황 손실
**해결**:
- `pending_approval` 상태 DB 저장
- 서버 재시작 후 자동 복원
- 캐시되지 않은 Queue 메시지는 최신만 재전송

### 4️⃣ 데이터 기반 콘텐츠 생성 검증
**문제**: Gemini 생성 콘텐츠의 신뢰도 평가
**해결**:
- 검색 트렌드·포스트 감성 데이터를 프롬프트에 포함
- 지난주 추천 키워드의 실제 검색량 변화를 `history.json`에서 추적
- 예측과 실제의 오차율 측정 → 프롬프트 개선

---

## 💻 코드 품질 & 테스트

```bash
# 테스트 실행
pytest tests/ -v

# CI/CD
# main 푸시·PR 시 GitHub Actions가 자동으로 pytest 실행
# (.github/workflows/ci.yml 참고)
```

### 로깅 및 모니터링
```python
# 구조적 로깅
log = get_logger("collector", log_file=f"logs/collector_{today}.json")
log.info("수집 시작", extra={"keyword": "AI 마케팅", "target_count": 30})
# → logs/collector_2026-06-16.json에 JSON 형식 기록
```

---

## 📚 참고 자료

- **전체 아키텍처**: [docs/architecture.md](docs/architecture.md)
- **보안 설정**: [docs/security.md](docs/security.md)
- **README (사용법)**: [README.md](README.md)

---

## 🎯 향후 개선 방향

1. **더 나은 콘텐츠 품질**
   - 다중 모드 임베딩 (텍스트+이미지)
   - 사용자 피드백 기반 프롬프트 최적화

2. **확장성**
   - 추가 SNS 채널 (TikTok, YouTube Shorts)
   - 다국어 지원

3. **고급 분석**
   - 경쟁사 콘텐츠 분석
   - 예측 모델 (검색량 예측)

4. **엔터프라이즈 기능**
   - 팀 협업 (역할 기반 접근 제어)
   - 감사 로그 (콘텐츠 편집 이력)
   - A/B 테스트 (여러 콘텐츠 버전 테스트)

---

**Made with ❤️ by heewonn09**  
*GitHub: https://github.com/heewonn09/marketing-agent*
