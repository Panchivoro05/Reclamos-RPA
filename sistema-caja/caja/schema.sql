-- Esquema de SISCAJA. Se aplica con `flask --app caja init-db` y se puede repetir.
-- Montos en céntimos (INTEGER) para no perder precisión; fechas en UTC como texto ISO 8601.

CREATE TABLE IF NOT EXISTS operadores (
    id          INTEGER PRIMARY KEY,
    usuario     TEXT    NOT NULL UNIQUE,
    nombre      TEXT    NOT NULL,
    clave_hash  TEXT    NOT NULL,
    activo      INTEGER NOT NULL DEFAULT 1,
    creado_en   TEXT    NOT NULL
);

-- Copia de los pedidos del sistema de ventas (se llena con `flask --app caja sincronizar`).
CREATE TABLE IF NOT EXISTS pedidos (
    id                  INTEGER PRIMARY KEY,
    codigo              TEXT    NOT NULL UNIQUE,
    cliente_nombre      TEXT    NOT NULL,
    cliente_email       TEXT    NOT NULL,
    estado              TEXT    NOT NULL,
    total_centimos      INTEGER NOT NULL,
    local               TEXT    NOT NULL,
    direccion_entrega   TEXT    NOT NULL,
    creado_en           TEXT    NOT NULL,
    entregado_en        TEXT,
    sincronizado_en     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pedido_items (
    id                       INTEGER PRIMARY KEY,
    pedido_id                INTEGER NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    producto                 TEXT    NOT NULL,
    cantidad                 INTEGER NOT NULL,
    precio_unitario_centimos INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pedido_items_pedido ON pedido_items (pedido_id);

CREATE TABLE IF NOT EXISTS compensaciones (
    id              INTEGER PRIMARY KEY,
    numero          TEXT    NOT NULL UNIQUE,
    pedido_id       INTEGER NOT NULL REFERENCES pedidos (id),
    tipo            TEXT    NOT NULL,
    monto_centimos  INTEGER NOT NULL,
    motivo          TEXT    NOT NULL,
    operador_id     INTEGER NOT NULL REFERENCES operadores (id),
    creado_en       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_compensaciones_pedido ON compensaciones (pedido_id);
