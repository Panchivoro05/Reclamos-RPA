
# Prompts por fase para Claude Code

Copia el prompt de la fase que vas a trabajar y pégalo en Claude Code desde la raíz del repositorio (`reclamos-rpa/`), con el `CLAUDE.md` ya colocado ahí.
Usa una sesión nueva por fase. Si el prompt pide un plan, revísalo antes de decir "adelante".

---

## Antes de la primera sesión (5 minutos, lo haces tú)

```bash
sudo dnf install git nodejs python3 python3-pip
# Docker ya instalado: verifica que el servicio esté activo y que tu usuario use docker sin sudo
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # luego cierra sesión y vuelve a entrar
docker compose version
mkdir reclamos-rpa && cd reclamos-rpa && git init
# copia aquí el CLAUDE.md
sudo firewall-cmd --add-port={8000,8081}/tcp --permanent && sudo firewall-cmd --reload
```

Instala **Expo Go** en tu celular. El celular y la PC deben estar en la misma red Wi-Fi.
Crea un repositorio vacío en GitHub y conéctalo (`git remote add origin ...`).

---

## FASE 1 (hoy): base del proyecto + pedidos y reclamos

```text
Vamos a trabajar la FASE 1 del proyecto. Lee primero el CLAUDE.md.
Como el repositorio está vacío, esta fase incluye la base mínima del proyecto.

OBJETIVO DE LA FASE
Al final, el cliente abre la app en su celular (Expo Go), inicia sesión, ve sus pedidos,
entra a uno y registra un reclamo con foto. El reclamo queda guardado en PostgreSQL en
estado "recibido", con su primer evento en la línea de tiempo, y el cliente puede verlo
en "Mis reclamos".

1) BASE DEL PROYECTO
- Estructura de carpetas según CLAUDE.md (solo crea app-movil/, backend/ e infra/ por ahora,
  más README.md, .gitignore y .env.example en la raíz).
- infra/compose.yml (Docker Compose) con PostgreSQL 16 y Valkey 8 (volúmenes con nombre,
  puertos publicados solo en 127.0.0.1, healthchecks). La API corre fuera del contenedor por ahora con uvicorn.
- backend/pyproject.toml con dependencias y extras [dev] (pytest, httpx, ruff).
- .github/workflows/ci.yml: ruff + pytest del backend (con un servicio PostgreSQL)
  y lint + typecheck de la app.

2) MODELO DE DATOS (SQLAlchemy 2 + migración inicial de Alembic)
- clientes: id, firebase_uid (único, nullable), email (único), nombre, telefono_whatsapp, creado_en
- productos: id, nombre, categoria (hamburguesa | combo | acompañamiento | bebida | postre), precio, activo
- pedidos: id, codigo (BY-000123, único), cliente_id, estado (en_preparacion | en_camino | entregado | cancelado),
  total, direccion_entrega, local, creado_en, entregado_en (nullable)
- pedido_items: id, pedido_id, producto_id, cantidad, precio_unitario
- reclamos: id, codigo (RC-2026-000001, único), pedido_id, cliente_id, tipo (enum del CLAUDE.md),
  estado (enum del CLAUDE.md), descripcion, foto_ruta (nullable), creado_en, actualizado_en
- reclamo_items: id, reclamo_id, pedido_item_id, cantidad_afectada
- reclamo_eventos: id, reclamo_id, estado, mensaje, actor (cliente | sistema | bot | ia | agente), creado_en
Usa Enum de Python para tipos y estados. Fechas en UTC con zona horaria.

3) DATOS DE PRUEBA (python -m app.seed, idempotente)
- Menú de BurgerYa: unos 12 productos realistas con precios en soles.
- 2 clientes demo: cliente1@burgerya.pe y cliente2@burgerya.pe.
- Unos 8 pedidos entre ambos clientes, con estados y fechas variados. Incluye al menos uno
  entregado hace 30 minutos, otro entregado hace 3 días (fuera de plazo) y uno en camino.

4) API (prefijo /api/v1)
- GET /health
- Autenticación según AUTH_MODE (dev con X-Dev-User | firebase con firebase-admin),
  como dependencia reutilizable que devuelve el cliente actual. En modo firebase, si el
  cliente no existe se crea con los datos del token.
- GET /me
- GET /pedidos → pedidos del cliente actual, del más reciente al más antiguo
- GET /pedidos/{codigo} → detalle con sus ítems (404 si no es del cliente)
- POST /reclamos (multipart/form-data): pedido_codigo, tipo, descripcion, items
  (lista JSON de {pedido_item_id, cantidad_afectada}), foto (opcional, jpg/png/webp, máx. 5 MB).
  Validaciones de negocio en app/services/reclamos.py:
    · el pedido existe y pertenece al cliente
    · el pedido está entregado (o en camino si el tipo es "demora")
    · está dentro del plazo de reclamo: RECLAMO_PLAZO_HORAS desde la entrega (configurable, 24 por defecto)
    · los ítems pertenecen al pedido y las cantidades no superan las pedidas
    · no hay otro reclamo abierto del mismo tipo para ese pedido
    · tipos producto_equivocado y mal_estado: la foto es obligatoria
  Si todo está bien: crea el reclamo en estado "recibido", genera el código y registra el
  evento inicial ("Recibimos tu reclamo"). Deja una función encolar_reclamo() que por ahora
  solo escribe en el log: en la fase 3 enviará el reclamo a Celery.
  Errores con mensajes claros en español y códigos HTTP correctos (400, 404, 409, 422).
- GET /reclamos → reclamos del cliente
- GET /reclamos/{codigo} → detalle con ítems y eventos en orden cronológico
- GET /archivos/{nombre} → sirve la foto solo al dueño del reclamo
Fotos: guárdalas en disco (UPLOAD_DIR) mediante una interfaz AlmacenamientoArchivos con
implementación local, para cambiarla a Firebase Storage más adelante sin tocar el resto.
CORS habilitado para desarrollo.

5) PRUEBAS (pytest, base de datos de prueba aislada)
Cubre como mínimo: listar pedidos solo del cliente, detalle ajeno → 404, reclamo válido,
fuera de plazo, ítem ajeno, cantidad excedida, reclamo duplicado, foto obligatoria faltante
y foto con formato inválido.

6) APP MÓVIL (Expo + TypeScript + Expo Router)
- Configuración: EXPO_PUBLIC_API_URL y EXPO_PUBLIC_AUTH_MODE (dev | firebase).
  En modo dev, la pantalla de login muestra los dos clientes demo para elegir uno.
  En modo firebase, login con correo y contraseña (deja la integración lista pero opcional).
- Cliente HTTP tipado + TanStack Query. Sesión en Zustand, persistida con expo-secure-store.
- Pantallas:
  · Login
  · Mis pedidos (lista con código, fecha, total y estado con un color)
  · Detalle del pedido (ítems, total y botón "Tengo un problema con mi pedido" si aplica)
  · Nuevo reclamo: tipo (4 opciones con ícono y texto breve), selección de productos
    afectados con cantidad, descripción, foto con cámara o galería (expo-image-picker).
    Validación con React Hook Form + Zod y mensajes del backend mostrados de forma amigable.
  · Mis reclamos (lista con código, tipo y estado)
  · Detalle del reclamo: datos, foto y línea de tiempo vertical con los eventos
    (en la fase 4 se actualizará en vivo).
- Navegación con pestañas: Pedidos | Reclamos | Perfil (perfil con datos y cerrar sesión).
- Estilo con NativeWind: limpio y moderno, color principal naranja/rojo de hamburguesería,
  estados con colores consistentes, estados de carga, vacío y error en cada pantalla.
- ESLint + Prettier + script typecheck. Al menos un test con Jest (por ejemplo, el esquema Zod).

7) CIERRE
- README con los pasos exactos para levantar todo en Fedora y abrir la app en el celular.
- Corre ruff, pytest, lint y typecheck. Todo debe quedar en verde.
- Dame un resumen de lo hecho, las decisiones técnicas importantes explicadas en simple,
  y la lista de lo que debo probar yo manualmente en el celular.

Antes de escribir código, muéstrame un plan corto por bloques (1 a 7) y espera mi confirmación.
Después implementa bloque por bloque y haz un commit al terminar cada uno.
```

### Qué verificar tú al terminar la fase 1
- [ ] `docker compose -f infra/compose.yml up -d` levanta PostgreSQL y Valkey sin errores.
- [ ] `http://localhost:8000/docs` muestra la API en Swagger.
- [ ] La app abre en Expo Go escaneando el QR.
- [ ] Inicias sesión como cliente1, ves los pedidos y registras un reclamo con foto tomada desde el celular.
- [ ] Intentar reclamar el pedido de hace 3 días muestra un mensaje claro de "fuera de plazo".
- [ ] El reclamo aparece en "Mis reclamos" con su evento "Recibimos tu reclamo".
- [ ] GitHub Actions pasa en verde después del `git push`.

---

## FASE 2: sistema de caja antiguo + bot RPA

```text
Vamos a trabajar la FASE 2. Lee el CLAUDE.md.
1) sistema-caja/: aplicación Flask + Jinja2 + SQLite que simule un sistema de caja antiguo
   (estilo visual sobrio y algo anticuado) SIN API: login de operador, búsqueda de pedido por
   código, detalle del pedido, formulario para registrar una compensación (reenvío, reembolso
   parcial, reembolso total o cupón, con monto y motivo) e historial de compensaciones.
   Script para sincronizar sus pedidos desde PostgreSQL (simula que ambos sistemas comparten
   los datos de ventas). Usa atributos id estables en el HTML para que el bot pueda ubicarlos.
2) bot-rpa/: Robot Framework + Browser Library. Flujo resolver_reclamo.robot que recibe el
   código de pedido, el tipo de reclamo y la solución; inicia sesión, busca el pedido, verifica
   ítems y montos, registra la compensación y devuelve un resultado estructurado (JSON).
   Capturas de pantalla en cada paso. Debe poder ejecutarse con el navegador visible (demo)
   o en modo headless (worker).
3) Si Playwright falla en Fedora, crea un Dockerfile basado en mcr.microsoft.com/playwright.
4) Pruebas: el flujo feliz y al menos dos de error (pedido inexistente, monto excedido).
Primero el plan, después implementa con un commit por bloque.
```

## FASE 3: automatización de punta a punta

```text
Vamos a trabajar la FASE 3. Lee el CLAUDE.md.
Conecta todo: encolar_reclamo() envía el reclamo a Celery (broker Valkey). El worker cambia
los estados (en_validacion → validado → en_resolucion → resuelto, o escalado), registra cada
evento, aplica las reglas de negocio (qué solución corresponde a cada tipo) y los controles
antifraude (monto máximo de compensación automática, máximo de reclamos por cliente en 30
días, foto obligatoria), ejecuta el bot de la fase 2 y guarda su resultado y capturas.
Reglas y límites configurables en una tabla o archivo, no fijos en el código.
Agrega el worker al compose.yml. Pruebas de las reglas y del flujo con el bot simulado.
Primero el plan.
```

## FASE 4: tiempo real y notificaciones

```text
Vamos a trabajar la FASE 4. Lee el CLAUDE.md.
1) WebSocket en FastAPI: el detalle del reclamo en la app se actualiza en vivo
   (el worker publica los eventos por Valkey pub/sub).
2) Notificaciones push con expo-notifications y Expo Push Service: registro del token del
   dispositivo y envío en cada cambio de estado. Recuerda que en Android se necesita una
   development build (no Expo Go).
3) WhatsApp Cloud API: envío de plantillas en los hitos (recibido, resuelto, escalado) y
   webhook para recibir respuestas, expuesto con Cloudflare Tunnel o ngrok.
   Interfaz NotificadorWhatsApp con implementación falsa para pruebas.
Primero el plan.
```

## FASE 5: inteligencia artificial con Gemini

```text
Vamos a trabajar la FASE 5. Lee el CLAUDE.md.
Integra Gemini (SDK google-genai) en el worker, detrás de una interfaz ProveedorIA para poder
cambiar a OpenAI:
1) Clasificación del texto libre con salida estructurada (tipo, productos mencionados,
   confianza).
2) Análisis de la foto: ¿es coherente con lo reclamado?
3) Redacción de los mensajes al cliente (cordiales, breves, en español de Perú).
4) Llamada a funciones controladas (consultar_pedido, consultar_estado_reclamo) para un
   asistente de consultas por WhatsApp.
Si la confianza es baja o la foto no coincide → escalado. La IA nunca decide montos.
Registra cada llamada (latencia y costo aproximado). Pruebas con el proveedor simulado.
Primero el plan.
```

## FASE 6: panel web de supervisión

```text
Vamos a trabajar la FASE 6. Lee el CLAUDE.md.
panel-web/ con React + Vite + TypeScript, Tailwind + shadcn/ui, TanStack Query y Recharts.
Roles agente y administrador. Pantallas: bandeja de reclamos con filtros, detalle con línea
de tiempo, capturas del bot y análisis de la IA; resolución manual de casos escalados;
configuración de reglas y límites antifraude; dashboard de indicadores (tiempo promedio de
resolución, % resuelto sin intervención humana, reclamos por tipo, tasa de escalamiento).
Endpoints de backend protegidos por rol. Primero el plan.
```

## FASE 7: DevOps completo y cierre

```text
Vamos a trabajar la FASE 7. Lee el CLAUDE.md.
1) Dockerfile para backend, worker, bot y sistema de caja; compose.yml completo.
2) Despliegue en Fedora Server con Docker Compose (restart: unless-stopped, servicio docker
   habilitado al arranque) y un runner propio de
   GitHub Actions que despliegue al hacer merge en main.
3) Monitoreo: métricas de FastAPI y Celery en Prometheus, dashboard de Grafana con métricas
   técnicas y de negocio, y Sentry en backend y app.
4) Build de la app con EAS (APK).
5) Script de evaluación que simule N reclamos y mida los indicadores del objetivo específico 7.
6) Documentación final de arquitectura y despliegue.
Primero el plan.
```
