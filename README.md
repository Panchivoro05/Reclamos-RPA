# Plataforma de Atención Automatizada de Reclamos mediante RPA

Trabajo final de **Arquitectura de Soluciones Móviles** (USIL). Caso de estudio: **BurgerYa**,
cadena de comida rápida con delivery en Lima.

El cliente registra desde la app móvil un reclamo sobre su pedido (producto equivocado, pedido
incompleto, producto en mal estado o demora), con descripción y foto. La API lo valida, lo guarda
en PostgreSQL y lo deja listo para el procesamiento automático.

Un **worker de Celery** toma cada reclamo de la cola (Valkey), aplica las reglas de negocio y los
controles antifraude, y lanza un **bot RPA** que registra la compensación en **SISCAJA**, el
sistema de caja antiguo de BurgerYa, que no tiene API: el bot lo opera por su interfaz web, como lo
haría un cajero. El cliente ve cada paso en la app y, al final, el video del bot resolviendo su
reclamo. Los casos dudosos se escalan a un agente humano.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Base del proyecto, pedidos y reclamos (API + app) | ✅ |
| 2 | Sistema de caja antiguo + bot RPA | ✅ |
| 3 | Automatización de punta a punta (Celery) | ✅ |
| 4 | Tiempo real y notificaciones | Pendiente |
| 5 | IA con Gemini | Pendiente |
| 6 | Panel web de supervisión | Pendiente |
| 7 | DevOps completo | Pendiente |

## Estructura

```
app-movil/     App del cliente (React Native + Expo SDK 58, Expo Router)
backend/       API FastAPI + worker Celery + SQLAlchemy + Alembic + pruebas (pytest)
sistema-caja/  Sistema de caja antiguo SISCAJA (Flask + Jinja2 + SQLite, sin API)
bot-rpa/       Bot RPA que opera SISCAJA (Robot Framework + Browser Library)
infra/         Docker Compose (PostgreSQL 16, Valkey 8 y el worker)
.github/       CI: backend, sistema de caja, bot (con navegador real) y app
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
npm start          # Expo en el puerto 8082
```

Escanea el código QR con Expo Go (Android) o con la cámara (iOS).

Si cambias `app-movil/.env`, reinicia limpiando la caché con `npm start -- -c`.

Expo usa el puerto **8082** (no el 8081 por defecto) para no chocar con otros proyectos que ya
ocupen el 8081 en la misma PC.

### 5. Sistema de caja antiguo (SISCAJA)

Simula el sistema interno heredado de BurgerYa: solo tiene pantallas web y **no tiene API**; el bot
RPA lo opera por la interfaz. En otra terminal:

```bash
cd sistema-caja
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
flask --app caja init-db                           # crea las tablas y el operador
flask --app caja sincronizar                       # copia los pedidos desde PostgreSQL
flask --app caja run --host 127.0.0.1 --port 5050
```

`flask --app caja sincronizar` simula el proceso por lotes que comparte los datos de ventas con
caja: lee los pedidos del backend en una sesión de **solo lectura** y los copia a SQLite. Se puede
repetir (actualiza sin duplicar) y nunca borra compensaciones. Ejecútalo después de
`python -m app.seed` para que caja tenga las mismas fechas.

Abre <http://127.0.0.1:5050> e ingresa con `CAJA_OPERADOR_USUARIO` y `CAJA_OPERADOR_CLAVE` del
`.env`. Escucha solo en `127.0.0.1`: es un sistema interno y no debe verse desde la red.

### 6. Bot RPA

Opera SISCAJA por su interfaz web con Robot Framework + Browser Library (Playwright), como lo
haría un cajero. Necesita SISCAJA corriendo. En otra terminal:

```bash
cd bot-rpa
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
rfbrowser init chromium        # descarga Playwright y Chromium (una sola vez, ~300 MB)

# Demo: abre el navegador y se ve al bot mover el cursor, escribir y hacer clic
python -m bot_rpa --pedido BY-000101 --solucion reembolso_parcial --monto 10 \
  --motivo "Faltó una hamburguesa en el pedido" --visible
```

- Soluciones: `reenvio`, `reembolso_parcial`, `reembolso_total` y `cupon` (`--monto` solo en
  parcial y cupón).
- `--total-esperado 82.50` y `--items-esperados '[{"producto": "Nuggets x6", "cantidad": 1}]'`
  hacen que el bot compare lo que ve en caja con lo que dice el reclamo.
- Sin `--visible` corre oculto (unos 7 s), como lo hará el worker de la fase 3.
- Cada ejecución deja en `bot-rpa/salidas/<fecha>_<pedido>/`: `resultado.json`, `capturas/`
  (una por paso, con el cursor y el paso visibles), `video.webm` y el log de Robot.
- Playwright funcionó directamente en Fedora 44; si `rfbrowser init` fallara en otra versión,
  se puede ejecutar el bot en un contenedor `mcr.microsoft.com/playwright`.

### 7. Worker (Celery): la automatización de punta a punta

Con la API, SISCAJA y el bot listos, el worker procesa cada reclamo nuevo solo. Elige **una**
forma de ejecutarlo (dos workers a la vez se reparten los reclamos):

```bash
# a) En Fedora, con el navegador del bot VISIBLE (para la demo)
cd backend && source .venv/bin/activate
BOT_VISIBLE=true celery -A app.worker worker -B --loglevel info

# b) En Fedora, oculto (como en producción)
celery -A app.worker worker -B --loglevel info

# c) En Docker (siempre oculto). Desde la raíz:
docker compose -f infra/compose.yml --profile worker up -d --build
docker compose -f infra/compose.yml logs -f worker
```

- `-B` activa Celery Beat: cada minuto rescata los reclamos que quedaron en "recibido" porque
  Valkey no respondía al crearlos.
- `BOT_MODO=simulado` resuelve sin SISCAJA ni navegador (útil para probar la app sola).
- La imagen de Docker usa `mcr.microsoft.com/playwright` (unos 4 GB) y corre con tu uid/gid
  (`WORKER_UID`, `WORKER_GID`) para que la evidencia en `backend/uploads` quede a tu nombre.
- Para una demo limpia: `python -m app.seed --reiniciar-reclamos` (borra todos los reclamos y su
  evidencia; deja pedidos, clientes y reglas). En SISCAJA:
  `rm data/caja.db && flask --app caja init-db && flask --app caja sincronizar`.

### 8. firewalld (si el celular no llega a la PC)

La zona por defecto de **Fedora Workstation** ya permite los puertos 1025 a 65535. En otras zonas
(por ejemplo, Fedora Server), abre la API y Expo:

```bash
sudo firewall-cmd --add-port={8000,8082}/tcp --permanent && sudo firewall-cmd --reload
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
| GET | `/reclamos/{codigo}` | Detalle con ítems, línea de tiempo y `resolucion` (compensación, número de operación y video) |
| GET | `/reclamos/{codigo}/video` | Video del bot registrando la compensación (solo para su dueño) |
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

## Procesamiento automático (fase 3)

```
recibido → en_validacion → validado → en_resolucion → resuelto
                 └──────────→ escalado ←──────────┘
```

| Estado | Lo hace | Mensaje que ve el cliente |
|---|---|---|
| `en_validacion` | worker | "Estamos revisando tu reclamo." |
| `validado` | reglas | "¡Tu reclamo fue aprobado! Te corresponde un reembolso de S/ 8.90." |
| `en_resolucion` | bot | "Estamos registrando tu compensación en nuestro sistema de caja." |
| `resuelto` | bot | "¡Listo! Registramos un reembolso de S/ 8.90. Número de operación: CMP-000001." |
| `escalado` | reglas o bot | "Tu caso necesita una revisión adicional. Un agente de BurgerYa lo atenderá pronto." |

El motivo real del escalamiento (por ejemplo, "Supera el monto máximo automático: S/ 55.80 >
S/ 40.00") se guarda en `reclamos.motivo_escalamiento` para el agente; el cliente nunca lo ve.

### Reglas y controles antifraude (configurables)

Viven en la base de datos, no en el código. En la fase 6 se editarán desde el panel web; mientras
tanto, con SQL:

| Tipo | Solución | Monto | Foto |
|---|---|---|---|
| `producto_equivocado` | `reenvio` | S/ 0 (se reenvía el producto) | Obligatoria |
| `pedido_incompleto` | `reembolso_parcial` | Valor de los productos afectados | No |
| `mal_estado` | `reembolso_parcial` | Valor de los productos afectados | Obligatoria |
| `demora` | `cupon` | S/ 10 fijo | No |

Controles (tabla `politica_antifraude`): monto máximo de compensación automática **S/ 40** y
máximo **3 reclamos por cliente en 30 días**. Un reclamo que no pasa algún control se escala.

```sql
-- Ejemplos (psql: docker exec -it reclamos-rpa-postgres-1 psql -U reclamos)
UPDATE politica_antifraude SET monto_maximo_automatico = 60;
UPDATE reglas_resolucion SET base_monto = 'porcentaje_total', valor = 15 WHERE tipo = 'demora';
UPDATE reglas_resolucion SET requiere_foto = true WHERE tipo = 'pedido_incompleto';
```

`requiere_foto` también lo usan la API y la app al registrar el reclamo: la regla vive en un
solo lugar.

### Reintentos y evidencia

- Errores técnicos del bot (caja caída, tiempo agotado): 2 reintentos (30 s y 60 s); si siguen
  fallando, se escala. Errores de negocio (datos que no coinciden, monto rechazado): se escala
  de inmediato.
- Cada intento queda en `ejecuciones_bot`, con su evidencia copiada en
  `backend/uploads/evidencias/<reclamo>/intento-<n>/` (capturas, `video.webm`, `resultado.json`).
- El motivo en SISCAJA empieza con el código del reclamo. Si un reintento encuentra esa
  operación en el historial del pedido, la reutiliza: **nunca se compensa dos veces**.

## SISCAJA y bot RPA

### Reglas de una compensación en SISCAJA

| Tipo | Monto |
|---|---|
| `reenvio` | S/ 0.00 (se reenvía el producto) |
| `reembolso_parcial` | Mayor que 0 y hasta el saldo reembolsable |
| `reembolso_total` | El saldo reembolsable completo |
| `cupon` | Mayor que 0 y hasta el total del pedido; no descuenta saldo |

El saldo reembolsable es el total del pedido menos los reembolsos anteriores. Los pedidos
cancelados no admiten compensaciones. Cada registro genera un número de operación `CMP-000001`.

### Resultado del bot (`resultado.json`)

```json
{
  "exito": true,
  "codigo_error": null,
  "mensaje": "Compensacion registrada en SISCAJA.",
  "numero_operacion": "CMP-000001",
  "monto_registrado": "S/ 10.00",
  "pasos": [{"paso": "login", "descripcion": "...", "captura": "capturas/01_login.png"}],
  "video": "video.webm",
  "duracion_s": 7.2
}
```

| `codigo_error` | Cuándo |
|---|---|
| `credenciales_invalidas` | SISCAJA rechazó al operador |
| `pedido_inexistente` | El pedido no está en caja |
| `datos_no_coinciden` | Los ítems o el total en caja no coinciden con lo esperado |
| `pedido_no_compensable` | El pedido está cancelado |
| `compensacion_rechazada` | SISCAJA rechazó la compensación (por ejemplo, monto excedido) |
| `tiempo_agotado` / `error_inesperado` | El bot no terminó o falló algo ajeno al negocio |

## Calidad

```bash
# Backend (las pruebas crean y usan su propia base de datos: reclamos_test)
cd backend && source .venv/bin/activate
ruff check . && ruff format --check . && pytest

# Sistema de caja (sus pruebas de sincronización usan la base siscaja_test de PostgreSQL)
cd sistema-caja && source .venv/bin/activate
ruff check . && ruff format --check . && pytest

# Bot RPA: levanta su propio SISCAJA de prueba y ejecuta el bot con un navegador real (~50 s)
cd bot-rpa && source .venv/bin/activate
ruff check . && ruff format --check . && robocop check robot && pytest
pytest -m "not e2e"     # solo las pruebas rápidas, sin navegador

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
- **SISCAJA sin API, a propósito:** solo HTML y formularios (una prueba lo verifica). El bot
  debe operarlo por la pantalla; esa es la razón de usar RPA. Cada elemento tiene un `id`
  estable para que el bot lo ubique aunque cambie el diseño.
- **Montos en céntimos en SISCAJA** (enteros en SQLite) y `BEGIN IMMEDIATE` al registrar:
  dos compensaciones simultáneas no pueden pasar el saldo ni repetir el número de operación.
- **Las reglas de compensación viven en SISCAJA,** no en el bot: igual que un cajero, el bot
  intenta y, si la pantalla lo rechaza, reporta el error.
- **Sincronización por lotes y de solo lectura:** `flask --app caja sincronizar` lee ventas en
  una sesión `read_only` de PostgreSQL. En CI se sincroniza contra la base real del backend para
  detectar si cambia una columna.
- **Bot visible:** Playwright no dibuja el mouse; el bot inyecta desde afuera un cursor que sigue
  los eventos reales del mouse, resalta el elemento activo y muestra el paso en un banner.
  Aparece en vivo (`--visible`), en las capturas y en el video.
- **El robot corre en un proceso aparte** con tiempo límite: si el navegador se cuelga, no
  arrastra al worker. La clave viaja por variable de entorno y se escribe con `Type Secret`
  (no queda en ningún log; una prueba lo verifica).
- **Worker con Celery y Valkey:** la API solo guarda y encola (responde rápido aunque el bot tarde
  40 s). Valkey habla el protocolo de Redis, por eso Celery usa su transporte `redis://`.
- **Un reclamo a la vez** (concurrencia 1): SISCAJA es "una terminal de caja".
- **`acks_late`:** el mensaje se confirma al terminar; si el worker muere a mitad, Celery lo
  vuelve a entregar. Y el procesamiento retoma desde el estado guardado, sin repetir pasos.
- **Bloqueo de fila (`SELECT ... FOR UPDATE`)** en cada cambio de estado, pero no mientras el bot
  trabaja: dos procesos nunca avanzan el mismo reclamo a la vez.
- **Si Valkey está caído,** el cliente igual registra su reclamo; Celery Beat lo rescata.
- **Reglas en tablas y funciones puras:** cada control se prueba por separado y el agente ve todos
  los motivos del escalamiento, no solo el primero. La IA (fase 5) nunca decidirá montos.
- **El bot corre como programa aparte** (su propio entorno Python): el backend no carga Robot ni
  Playwright; se comunican por línea de comandos y JSON. En las pruebas, un bot simulado.
- **Video para el cliente:** la evidencia del bot (con el cursor visible) se sirve solo a su
  dueño. En Android se reproduce el WebM directamente; en iOS no (pendiente convertir a MP4 en la
  fase 7).
