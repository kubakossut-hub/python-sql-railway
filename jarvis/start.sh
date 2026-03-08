#!/usr/bin/env bash
set -euo pipefail

echo "=== JARVIS start.sh ==="

# 1. Walidacja wymaganych zmiennych środowiskowych
: "${DATABASE_URL:?Ustaw DATABASE_URL}"
: "${ANTHROPIC_API_KEY:?Ustaw ANTHROPIC_API_KEY}"
: "${MAKE2_WEBHOOK_URL:?Ustaw MAKE2_WEBHOOK_URL}"
: "${MAKE9_WEBHOOK_URL:?Ustaw MAKE9_WEBHOOK_URL}"
: "${JARVIS_API_TOKEN:?Ustaw JARVIS_API_TOKEN}"
: "${NGINX_USER:?Ustaw NGINX_USER}"
: "${NGINX_PASSWORD:?Ustaw NGINX_PASSWORD}"

# 2. Wygeneruj plik .htpasswd dla HTTP Basic Auth
echo "Generowanie .htpasswd..."
echo "${NGINX_USER}:$(openssl passwd -apr1 "${NGINX_PASSWORD}")" > /etc/nginx/.htpasswd
chmod 640 /etc/nginx/.htpasswd

# 3. Wygeneruj nginx config z podstawionymi zmiennymi
echo "Generowanie nginx config..."
mkdir -p /etc/nginx/conf.d
# PORT jest ustawiany przez Railway; domyślnie 80 jesli nie ustawione
export PORT="${PORT:-80}"
envsubst '${JARVIS_API_TOKEN} ${PORT}' \
  < /etc/nginx/templates/jarvis.conf.template \
    > /etc/nginx/conf.d/jarvis.conf

    # Usun domyslne konfiguracje nginx ktore moga kolidowac
    rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf 2>/dev/null || true

    # 4. Test konfiguracji nginx
    nginx -t

    # 5. Uruchom nginx w tle
    echo "Uruchamianie nginx..."
    nginx -g 'daemon off;' &
    NGINX_PID=$!

    # 6. Uruchom FastAPI (tylko lokalnie, nginx to proxy)
    echo "Uruchamianie FastAPI na 127.0.0.1:8000..."
    uvicorn app.main:app \
      --host 127.0.0.1 \
        --port 8000 \
          --workers 2 \
            --log-level info

            # Jesli uvicorn sie zatrzyma, wylacz tez nginx
            kill "${NGINX_PID}" 2>/dev/null || true
