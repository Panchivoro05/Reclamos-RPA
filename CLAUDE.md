# Plataforma de Atención Automatizada de Reclamos mediante RPA

Trabajo final del curso **Arquitectura de Soluciones Móviles** (USIL). Desarrollador único con apoyo de Claude Code.
Caso de estudio ficticio: **BurgerYa**, cadena de comida rápida con delivery en Lima.

## Qué hace el sistema

1. El cliente hace un pedido desde la app móvil (React Native + Expo).
2. Detecta un error (producto equivocado, pedido incompleto, producto en mal estado o demora) y registra un reclamo con el número de pedido, una descripción y, opcionalmente, una foto.
3. La API (FastAPI) guarda el reclamo en PostgreSQL y lo encola en Valkey.
4. Un worker de Celery toma el reclamo, pide a Gemini que lo clasifique y analice la foto, y lanza el bot RPA.
5. El bot (Robot Framework + Browser Library) opera por interfaz el **sistema de caja antiguo** (Flask, sin API): busca el pedido, lo valida y registra la compensación.
6. Cada cambio de estado se notifica por push (Expo) y WhatsApp, y la app lo muestra en vivo por WebSocket.
7. Los casos que no pasan las reglas o los controles antifraude se escalan a un agente humano en el panel web.

**Por qué RPA:** el sistema de caja no tiene API. El bot debe operarlo por su interfaz web, como lo haría una persona. **Nunca** crear un endpoint en `sistema-caja/` para que el bot lo consuma: eso anularía la justificación del proyecto.

## Estados del reclamo

`recibido` → `en_validacion` → `validado` → `en_resolucion` → `resuelto` → `cerrado`
Desde `en_validacion` o `en_resolucion` se puede pasar a `escalado` (revisión humana).
Cada cambio de estado se registra en la tabla `reclamo_eventos` (es la línea de tiempo que ve el cliente).

Tipos de reclamo: `producto_equivocado`, `pedido_incompleto`, `mal_estado`, `demora`.

## Stack (decidido, no proponer alternativas)

| Capa | Tecnología |
|---|---|
| SO (desarrollo y servidor) | Linux Fedora |
| App móvil | React Native + Expo (SDK estable actual), TypeScript estricto, Expo Router, TanStack Query, Zustand, React Hook Form + Zod, NativeWind, expo-image-picker, expo-notifications |
| Panel web | React + Vite + TypeScript, React Router, TanStack Query, Tailwind CSS + shadcn/ui, Recharts |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, SQLAlchemy 2 (estilo 2.0, tipado con `Mapped`), Alembic, httpx |
| Base de datos | PostgreSQL 16 |
| Cola | **Valkey** (no Redis) + Celery |
| RPA | Robot Framework + Browser Library (Playwright); RPA Framework para PDF |
| Sistema de caja antiguo | Flask + Jinja2 + SQLite, **sin API** |
| IA | API de Gemini con el SDK `google-genai` |
| Auth y archivos | Firebase Authentication (+ Firebase Storage más adelante) |
| Notificaciones | Expo Push Service + FCM; WhatsApp Cloud API (Meta) |
| Contenedores | **Docker Engine + Docker Compose** (plugin `docker compose`, no el antiguo `docker-compose`). Producción con Compose + `restart: unless-stopped` |
| CI/CD | GitHub Actions; EAS Build para la app |
| Calidad | ruff (lint + formato), pytest, ESLint, Prettier, Jest |
| Monitoreo | Prometheus + Grafana, Cockpit, Sentry |

## Estructura del repositorio

```
reclamos-rpa/
├── CLAUDE.md
├── README.md
├── .env.example
├── app-movil/        # React Native + Expo
├── panel-web/        # React + Vite
├── backend/          # FastAPI (app/), worker Celery, Alembic, tests/
├── bot-rpa/          # Robot Framework
├── sistema-caja/     # Flask + SQLite (sistema antiguo)
├── infra/            # compose.yml, configuración de monitoreo
└── .github/workflows/
```

Backend por capas: `app/api/` (routers), `app/models/` (SQLAlchemy), `app/schemas/` (Pydantic), `app/services/` (lógica de negocio), `app/core/` (config, seguridad, BD).
La lógica de negocio va en `services/`, nunca en los routers.

## Comandos

```bash
# Infraestructura (desde la raíz)
docker compose -f infra/compose.yml up -d

# Backend
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
alembic upgrade head
python -m app.seed               # datos de prueba
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
ruff check . && ruff format --check . && pytest

# App móvil
cd app-movil && npm install && npx expo start
npm run lint && npm run typecheck && npm test
```

## Particularidades de Fedora (importante)

- Usar Docker Engine (paquete `docker-ce` del repositorio oficial de Docker) con `docker compose`. Imágenes: `postgres:16`, `valkey/valkey:8`.
- **Puertos y firewalld:** Docker publica los puertos saltándose las reglas de firewalld. Los servicios internos (PostgreSQL, Valkey) se publican solo en `127.0.0.1` (por ejemplo `"127.0.0.1:5432:5432"`); solo la API y Expo se exponen a la red local.
- **SELinux:** todo volumen montado desde el host (bind mount) lleva `:Z`; preferir volúmenes con nombre para las bases de datos (por ejemplo `./data/pg:/var/lib/postgresql/data:Z`).
- **firewalld:** para probar desde el celular hay que abrir los puertos 8000 (API) y 8081 (Expo):
  `sudo firewall-cmd --add-port={8000,8081}/tcp --permanent && sudo firewall-cmd --reload`
- La app en el celular no puede usar `localhost`: la URL de la API se configura con `EXPO_PUBLIC_API_URL=http://<IP-de-la-PC-en-la-red-local>:8000`.
- Playwright no tiene soporte oficial en Fedora. Si `rfbrowser init` falla, ejecutar el bot en un contenedor basado en `mcr.microsoft.com/playwright`.

## Convenciones

- **Dominio en español** (tablas, campos, endpoints, pantallas: `reclamos`, `pedidos`, `estado`). Código técnico y nombres de librerías en inglés cuando sea lo natural.
- Textos visibles para el usuario en español de Perú, con tono cordial. Moneda en soles (`S/ 25.90`). Zona horaria `America/Lima`; en BD las fechas se guardan en UTC.
- Identificadores visibles: pedidos `BY-000123`, reclamos `RC-2026-000001`. Internamente usar ids enteros o UUID.
- TypeScript estricto, sin `any`. Python con anotaciones de tipo completas.
- Configuración solo por variables de entorno (`pydantic-settings`). **Ningún secreto en el repositorio**: `.env` está en `.gitignore`, mantener `.env.example` actualizado.
- Autenticación con `AUTH_MODE`:
  - `dev`: el backend acepta el encabezado `X-Dev-User: <email>` (solo desarrollo y pruebas).
  - `firebase`: valida el ID token de Firebase con `firebase-admin`.
- Toda funcionalidad nueva del backend lleva pruebas en pytest (con base de datos de prueba aislada).
- Commits pequeños con mensajes en español en modo imperativo: `agrega endpoint de reclamos`.

## Forma de trabajo

- El proyecto avanza por fases (ver `docs/fases.md` si existe). Trabajar **solo** la fase indicada en la sesión.
- Antes de implementar algo grande, proponer un plan corto y esperar confirmación.
- Al terminar una fase: ruff, pytest, lint y typecheck en verde, README actualizado, y un resumen de lo hecho y de lo que el desarrollador debe probar manualmente (por ejemplo, abrir la app en Expo Go).
- Explicar brevemente las decisiones técnicas importantes: el desarrollador debe poder defenderlas en la sustentación.
