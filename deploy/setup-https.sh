#!/bin/bash
# HTTPS 설정 스크립트 (GCP VM에서 실행)
# 사전 조건: GCP 방화벽에 포트 80/443 허용 + 도메인이 이 VM IP를 가리켜야 함
#
# 사용법: sudo bash setup-https.sh <도메인>
# 예:     sudo bash setup-https.sh market.example.com
#
# 도메인 없는 경우(IP만): sudo bash setup-https.sh --self-signed

set -e

DOMAIN="${1:-}"
APP_DIR="$(dirname "$(readlink -f "$0")")/.."

if [ -z "$DOMAIN" ]; then
    echo "사용법: sudo bash $0 <도메인 또는 --self-signed>"
    exit 1
fi

echo "=== nginx 설치 ==="
apt-get update -q
apt-get install -y nginx

echo "=== 방화벽 확인 (ufw) ==="
ufw allow 'Nginx Full' || true

if [ "$DOMAIN" = "--self-signed" ]; then
    echo "=== 자가 서명 인증서 생성 (테스트용) ==="
    mkdir -p /etc/letsencrypt/live/selfsigned
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/letsencrypt/live/selfsigned/privkey.pem \
        -out    /etc/letsencrypt/live/selfsigned/fullchain.pem \
        -subj   "/CN=marketing-agent-test" 2>/dev/null
    DOMAIN="selfsigned"
    echo "자가 서명 인증서 생성 완료 (브라우저 경고 무시 필요)"
else
    echo "=== certbot 설치 및 인증서 발급: $DOMAIN ==="
    apt-get install -y certbot python3-certbot-nginx
    certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos -m admin@"$DOMAIN" \
        --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx"
    echo "=== 인증서 자동 갱신 설정 ==="
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --pre-hook 'systemctl stop nginx' --post-hook 'systemctl start nginx'") | crontab -
fi

echo "=== nginx 설정 적용 ==="
mkdir -p /var/www/certbot
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/marketing-agent
sed -i "s/__DOMAIN__/$DOMAIN/g" /etc/nginx/sites-available/marketing-agent
ln -sf /etc/nginx/sites-available/marketing-agent /etc/nginx/sites-enabled/marketing-agent
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

echo ""
echo "=== HTTPS 설정 완료 ==="
if [ "$DOMAIN" = "selfsigned" ]; then
    echo "접속 URL: https://$(hostname -I | awk '{print $1}')"
    echo "주의: 자가 서명 인증서 — 브라우저에서 경고가 표시됩니다."
else
    echo "접속 URL: https://$DOMAIN"
    echo ".env에 아래를 추가해 HTTPS 쿠키/리디렉트 활성화:"
    echo "  FORCE_HTTPS=1"
    echo "  CARDNEWS_BASE_URL=https://$DOMAIN"
fi

echo ""
echo "systemctl status nginx  # nginx 상태 확인"
echo "journalctl -u nginx -f  # nginx 로그 확인"
