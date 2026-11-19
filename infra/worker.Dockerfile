# Worker de Celery + bot RPA en un contenedor.
# Base: imagen oficial de Playwright (Node + navegadores) en la versión que pide Browser 21.
# Construir desde la raíz:  docker compose -f infra/compose.yml --profile worker build
FROM mcr.microsoft.com/playwright:v1.64.1-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

# El worker escribe la evidencia en backend/uploads (montado desde el host): pwuser toma el
# uid/gid del usuario de Fedora para que los archivos queden a su nombre (por defecto 1000).
ARG UID=1000
ARG GID=1000
RUN (userdel -r ubuntu 2>/dev/null || true) && (groupdel ubuntu 2>/dev/null || true) \
    && groupmod -g "$GID" pwuser && usermod -u "$UID" -g "$GID" pwuser

WORKDIR /app

# Bot RPA en su propio entorno (como en desarrollo). Instalación editable: el bot busca sus
# archivos .robot junto al paquete. Los navegadores ya vienen en la imagen (--skip-browsers).
COPY bot-rpa/pyproject.toml bot-rpa/
COPY bot-rpa/bot_rpa bot-rpa/bot_rpa
COPY bot-rpa/robot bot-rpa/robot
RUN python3.12 -m venv /opt/bot \
    && /opt/bot/bin/pip install -e ./bot-rpa \
    && /opt/bot/bin/rfbrowser init --skip-browsers

# Backend (el worker usa sus modelos y servicios).
COPY backend/pyproject.toml backend/
COPY backend/app backend/app
RUN python3.12 -m venv /opt/backend && /opt/backend/bin/pip install ./backend

# Usuario sin privilegios que trae la imagen de Playwright.
RUN mkdir -p /app/uploads /app/bot-rpa/salidas && chown -R pwuser:pwuser /app
USER pwuser

ENV PATH="/opt/backend/bin:$PATH" \
    WORKER_BOT_DIR=/app/bot-rpa \
    WORKER_BOT_PYTHON=/opt/bot/bin/python \
    UPLOAD_DIR=/app/uploads \
    BOT_VISIBLE=false

WORKDIR /app/backend
CMD ["celery", "-A", "app.worker", "worker", "-B", "--loglevel", "info"]
