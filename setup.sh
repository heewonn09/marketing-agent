#!/bin/bash
# VM 최초 설정 스크립트 — Debian 12 (GCP e2-micro)
# 사용법: bash setup.sh
set -euo pipefail

# ── 설정 ────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/heewonn09/marketing-agent.git"
APP_DIR="$HOME/marketing-agent"
SERVICE_NAME="marketing-agent"
PYTHON="python3.11"
# ────────────────────────────────────────────────────────────────────────────

echo "======================================================"
echo "  Marketing Agent VM Setup"
echo "  사용자: $USER  |  앱 경로: $APP_DIR"
echo "======================================================"

# 1. 시스템 패키지 설치
echo ""
echo "[1/7] 시스템 패키지 설치..."
sudo apt-get update -q
sudo apt-get install -y python3.11 python3.11-venv python3-pip git curl

# 2. 저장소 클론
echo ""
echo "[2/7] 저장소 클론..."
if [ -d "$APP_DIR/.git" ]; then
    echo "  이미 존재함. git pull 실행..."
    git -C "$APP_DIR" pull origin main
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# 3. Python 가상환경 + 패키지 설치
echo ""
echo "[3/7] Python 가상환경 생성 및 패키지 설치..."
$PYTHON -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
echo "  패키지 설치 완료"

# 4. Playwright 시스템 의존성 설치 (root 필요)
echo ""
echo "[4/7] Playwright 시스템 의존성 설치..."
sudo ./venv/bin/playwright install-deps chromium

# 5. Playwright Chromium 바이너리 다운로드
echo ""
echo "[5/7] Playwright Chromium 다운로드..."
./venv/bin/playwright install chromium
echo "  Chromium 설치 완료"

# 6. 필요 디렉토리 생성
echo ""
echo "[6/7] 디렉토리 생성..."
mkdir -p data output

# 7. systemd 서비스 등록
echo ""
echo "[7/7] systemd 서비스 등록..."
sudo sed \
    -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__USER__|$USER|g" \
    "$APP_DIR/marketing-agent.service" \
    | sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "  서비스 등록 완료 (아직 시작 안 함)"

# .env 파일 안내
echo ""
echo "======================================================"
echo "  설정 완료! 다음 단계를 완료하세요:"
echo "======================================================"

if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << 'ENVEOF'
GEMINI_API_KEY=여기에_Gemini_API_키_입력
NAVER_CLIENT_ID=여기에_네이버_Client_ID_입력
NAVER_CLIENT_SECRET=여기에_네이버_Client_Secret_입력
SCHEDULED_KEYWORDS=AI 마케팅,디지털 마케팅
ENVEOF
    echo ""
    echo "  ★ .env 파일이 생성됐습니다. 실제 API 키를 입력하세요:"
    echo "      nano $APP_DIR/.env"
else
    echo "  .env 파일이 이미 존재합니다."
fi

echo ""
echo "  API 키 입력 후 서비스 시작:"
echo "      sudo systemctl start $SERVICE_NAME"
echo ""
echo "  로그 확인:"
echo "      sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "  ★ GCP 방화벽 포트 5000 개방 필요 (콘솔 또는 아래 명령):"
echo "      gcloud compute firewall-rules create allow-marketing-agent \\"
echo "        --allow tcp:5000 --source-ranges 0.0.0.0/0"
echo ""
echo "  접속 URL: http://34.11.175.125:5000"
echo "======================================================"
