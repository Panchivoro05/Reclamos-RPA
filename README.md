# Plataforma de Atención Automatizada de Reclamos mediante RPA

Trabajo final de **Arquitectura de Soluciones Móviles** (USIL). Caso de estudio: **BurgerYa**,
cadena de comida rápida con delivery en Lima.

El cliente registra desde la app móvil un reclamo sobre su pedido (producto equivocado, pedido
incompleto, producto en mal estado o demora), con descripción y foto. La API lo valida, lo guarda
en PostgreSQL y lo deja listo para el procesamiento automático (worker + bot RPA en las fases
siguientes).

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Base del proyecto, pedidos y reclamos (API + app) | ✅ |
| 2 | Sistema de caja antiguo + bot RPA | Pendiente |
| 3 | Automatización de punta a punta (Celery) | Pendiente |
| 4 | Tiempo real y notificaciones | Pendiente |
| 5 | IA con Gemini | Pendiente |
| 6 | Panel web de supervisión | Pendiente |
| 7 | DevOps completo | Pendiente |

## Estructura

```
app-movil/   App del cliente (React Native + Expo SDK 58, Expo Router)
backend/     API FastAPI + SQLAlchemy + Alembic + pruebas (pytest)
infra/       Docker Compose (PostgreSQL 16, Valkey 8)
.github/     CI: ruff + pytest del backend, lint + typecheck + Jest de la app
```

## Requisitos (Fedora)

```bash
sudo dnf install git nodejs python3.12
```

- **Docker Engine** con el plugin `docker compose` (paquete `docker-ce` del repositorio oficial
  de Docker). Tu usuario debe estar en el grupo `docker`:
  ```bash
  sudo systemctl enable --now docker
  sudo usermod -aG docker $USER   # luego cierra sesión y vuelve a entrar
  groups                          # debe aparecer "docker"
  ```
- **Expo Go** instalado en el celular. El celular y la PC deben estar en la **misma red Wi-Fi**.

## Puesta en marcha

Todos los comandos parten de la raíz del repositorio.

### 1. Configuración

```bash
cp .env.example .env                       # backend e infraestructura
cp app-movil/.env.example app-movil/.env   # app móvil
```

En `app-movil/.env`, cambia `EXPO_PUBLIC_API_URL` por la IP de tu PC en la red local. El celular
no puede usar `localhost`:

```bash
ip -4 -o addr show scope global      # por ejemplo: enp0s3 192.168.18.94/24
# EXPO_PUBLIC_API_URL=http://192.168.18.94:8000
```

### 2. Infraestructura (PostgreSQL y Valkey)

```bash
docker compose -f infra/compose.yml up -d
```

Los puertos se publican solo en `127.0.0.1`: Docker se salta las reglas de firewalld, así que la
base de datos y Valkey no quedan expuestos a la red.

### 3. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head          # crea las tablas
python -m app.seed            # menú, 2 clientes demo y 8 pedidos
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Documentación interactiva: <http://localhost:8000/docs>
- `--host 0.0.0.0` es necesario para que el celular llegue a la API.
- `python -m app.seed` se puede ejecutar cuantas veces quieras: no duplica datos y recalcula las
  fechas de los pedidos respecto de la hora actual. Ejecútalo antes de una demo para que el pedido
  "entregado hace 30 minutos" siga dentro del plazo de reclamo.

### 4. App móvil

En otra terminal:

```bash
cd app-movil
npm install
npx expo start
```

Escanea el código QR con Expo Go (Android) o con la cámara (iOS).

Si cambias `app-movil/.env`, reinicia con `npx expo start -c`.

### 5. firewalld (si el celular no llega a la PC)

La zona por defecto de **Fedora Workstation** ya permite los puertos 1025 a 65535. En otras zonas
(por ejemplo, Fedora Server), abre la API y Expo:

```bash
sudo firewall-cmd --add-port={8000,8081}/tcp --permanent && sudo firewall-cmd --reload
```

Si Fedora corre en una máquina virtual, el adaptador de red debe estar en modo **puente**
(bridged), no NAT.

## Datos de prueba

| Cliente | Correo |
|---|---|
| María Quispe | `cliente1@burgerya.pe` |
| Jorge Ramírez | `cliente2@burgerya.pe` |

| Pedido | Cliente | Estado | Sirve para probar |
|---|---|---|---|
| BY-000101 | cliente1 | Entregado hace 30 min | Reclamo válido (todos los tipos) |
| BY-000102 | cliente1 | En camino | Solo admite "demora" |
| BY-000103 | cliente1 | Entregado hace 3 días | Fuera de plazo |
| BY-000104 | cliente1 | Entregado hace 5 h | Dentro de plazo |
| BY-000105 | cliente1 | Cancelado | No admite reclamos |
| BY-000106 | cliente2 | Entregado hace 1 h | Pedido ajeno para cliente1 (404) |
| BY-000107 | cliente2 | En preparación | No admite reclamos todavía |
| BY-000108 | cliente2 | Entregado hace 2 días | Fuera de plazo |

## Autenticación

Se elige con `AUTH_MODE` (backend) y `EXPO_PUBLIC_AUTH_MODE` (app):

- **`dev`** (por defecto): la app muestra los clientes demo y envía el encabezado
  `X-Dev-User: <correo>`. Solo para desarrollo y pruebas.
- **`firebase`**: login con correo y contraseña de Firebase Authentication. La app envía el ID
  token y el backend lo valida con `firebase-admin` (`FIREBASE_CREDENTIALS_PATH` apunta al JSON de
  la cuenta de servicio, fuera del repositorio). Si el cliente no existe, se crea con los datos del
  token. La sesión de Firebase dura mientras la app esté abierta.

## API (`/api/v1`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de la API y la base de datos |
| GET | `/me` | Cliente con sesión |
| GET | `/pedidos` | Pedidos del cliente, del más reciente al más antiguo |
| GET | `/pedidos/{codigo}` | Detalle con ítems y tipos de reclamo disponibles |
| POST | `/reclamos` | Registra un reclamo (multipart: `pedido_codigo`, `tipo`, `descripcion`, `items`, `foto`) |
| GET | `/reclamos` | Reclamos del cliente |
| GET | `/reclamos/{codigo}` | Detalle con ítems y línea de tiempo |
| GET | `/archivos/{nombre}` | Foto de un reclamo (solo para su dueño) |

Los errores tienen la forma `{"detail": "<mensaje para el cliente>", "codigo": "<código estable>"}`:
400 (datos mal formados), 401 (sin sesión), 404 (no existe o no es tuyo), 409 (reclamo duplicado),
413 (foto de más de 5 MB) y 422 (no cumple una regla de negocio).

### Reglas de un reclamo

- El pedido existe y pertenece al cliente.
- El pedido está entregado; si está en camino, solo se acepta "demora".
- Está dentro del plazo: `RECLAMO_PLAZO_HORAS` desde la entrega (24 por defecto).
- Los productos pertenecen al pedido y las cantidades no superan las pedidas.
- No hay otro reclamo abierto del mismo tipo para ese pedido (también lo garantiza un índice único
  parcial en PostgreSQL, aunque lleguen dos peticiones a la vez).
- "Producto equivocado" y "mal estado" requieren foto (JPG, PNG o WEBP, máximo 5 MB; el formato se
  verifica por el contenido del archivo, no por su extensión).

## Calidad

```bash
# Backend (las pruebas crean y usan su propia base de datos: reclamos_test)
cd backend && source .venv/bin/activate
ruff check . && ruff format --check . && pytest

# App móvil
cd app-movil
npm run lint && npm run typecheck && npm test
```

GitHub Actions ejecuta lo mismo en cada push a `main` y en cada pull request.

## Decisiones técnicas

- **Backend por capas:** los routers (`app/api/`) solo traducen HTTP; las reglas de negocio están
  en `app/services/`, lo que permite probarlas y reutilizarlas desde el worker de la fase 3.
- **Pedido ajeno = 404, no 403:** responder "no existe" evita revelar que ese código pertenece a
  otro cliente.
- **Correlativo con secuencia de PostgreSQL:** los códigos `RC-AAAA-NNNNNN` nunca se repiten,
  aunque se registren reclamos al mismo tiempo. Pueden quedar huecos si un registro falla.
- **Fotos detrás de la interfaz `AlmacenamientoArchivos`:** hoy se guardan en disco
  (`UPLOAD_DIR`); para pasar a Firebase Storage basta otra implementación.
- **Fechas en UTC en la base de datos;** la app las muestra en hora de Lima (UTC-5 fijo, Perú no
  usa horario de verano). Los montos viajan como texto (`"82.50"`) para no perder precisión.
- **La app consulta al backend qué reclamos se permiten** (`tipos_reclamo_disponibles`) y valida
  el formulario con Zod antes de enviar; el backend vuelve a validar todo.
- **Sesión de la app en SecureStore** (Keychain/Keystore) y rutas protegidas de Expo Router: sin
  sesión, las pantallas privadas no existen; un 401 devuelve al login.
- **Expo SDK 58:** el `fetch` global es `expo/fetch`; la foto se adjunta con `File` de
  `expo-file-system` (el antiguo objeto `{uri, name, type}` ya no funciona).
