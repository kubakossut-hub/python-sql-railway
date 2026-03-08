# ── JARVIS – Dockerfile ──────────────────────────────────────────────────────
# Jeden kontener: nginx (port 80, public) + FastAPI (port 8000, internal)

FROM python:3.12-slim

# Zainstaluj nginx + apache2-utils (htpasswd) + gettext (envsubst)
RUN apt-get update && apt-get install -y --no-install-recommends \
      nginx \
      apache2-utils \
      gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Zainstaluj zależności Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Skopiuj kod aplikacji
COPY app/ ./app/

# Skopiuj pliki HTML
COPY html/ /var/www/jarvis/html/

# Skopiuj szablon nginx
COPY nginx/jarvis.conf.template /etc/nginx/templates/jarvis.conf.template

# Skopiuj skrypt startowy
COPY start.sh .
RUN chmod +x start.sh

# Railway używa zmiennej PORT (domyślnie 8080 dla zewnętrznego ruchu)
# Nginx słucha na 80 wewnątrz kontenera; Railway proxy przekazuje na 80
EXPOSE 80

# Healthcheck – Railway używa tego do monitorowania
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -sf http://localhost/health || exit 1

CMD ["./start.sh"]
