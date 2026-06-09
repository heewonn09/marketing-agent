#!/bin/bash
# 로컬에서 실행하는 배포 스크립트 — SSH로 VM에 접속해 코드 업데이트
# 사용법: bash deploy.sh
set -euo pipefail

# ── 설정 ────────────────────────────────────────────────────────────────────
VM_IP="34.11.175.125"
VM_USER="jhjttmtmtmjgt"
APP_DIR="/home/$VM_USER/marketing-agent"
SERVICE_NAME="marketing-agent"
# ────────────────────────────────────────────────────────────────────────────

echo "======================================================"
echo "  배포 시작: $VM_USER@$VM_IP"
echo "======================================================"

ssh -o StrictHostKeyChecking=no "$VM_USER@$VM_IP" \
    APP_DIR="$APP_DIR" SERVICE_NAME="$SERVICE_NAME" \
    'bash -s' << 'REMOTE'
set -euo pipefail

echo ""
echo "--- [1/4] git pull ---"
cd "$APP_DIR"
git pull origin main

echo ""
echo "--- [2/4] pip install ---"
./venv/bin/pip install -r requirements.txt -q

echo ""
echo "--- [3/4] playwright install chromium ---"
./venv/bin/playwright install chromium

echo ""
echo "--- [4/4] 서비스 재시작 ---"
sudo systemctl restart "$SERVICE_NAME"
sleep 3
sudo systemctl status "$SERVICE_NAME" --no-pager -l
REMOTE

echo ""
echo "======================================================"
echo "  배포 완료!"
echo "  앱 주소: http://$VM_IP:5000"
echo "  로그:    ssh $VM_USER@$VM_IP 'sudo journalctl -u $SERVICE_NAME -f'"
echo "======================================================"
