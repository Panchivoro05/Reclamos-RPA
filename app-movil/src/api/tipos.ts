/** Tipos de las respuestas de la API (reflejan app/schemas/ del backend). */

export const TIPOS_RECLAMO = [
  'producto_equivocado',
  'pedido_incompleto',
  'mal_estado',
  'demora',
] as const;
export type TipoReclamo = (typeof TIPOS_RECLAMO)[number];

export type EstadoPedido = 'en_preparacion' | 'en_camino' | 'entregado' | 'cancelado';

export type EstadoReclamo =
  'recibido' | 'en_validacion' | 'validado' | 'en_resolucion' | 'resuelto' | 'cerrado' | 'escalado';

export type ActorEvento = 'cliente' | 'sistema' | 'bot' | 'ia' | 'agente';

export type CategoriaProducto = 'hamburguesa' | 'combo' | 'acompañamiento' | 'bebida' | 'postre';

/** Los montos llegan como texto ("82.50") para no perder precisión. */
export type Monto = string;

export interface Cliente {
  id: number;
  email: string;
  nombre: string;
  telefono_whatsapp: string | null;
}

export interface PedidoResumen {
  codigo: string;
  estado: EstadoPedido;
  total: Monto;
  local: string;
  cantidad_productos: number;
  creado_en: string;
  entregado_en: string | null;
}

export interface PedidoItem {
  id: number;
  producto: string;
  categoria: CategoriaProducto;
  cantidad: number;
  precio_unitario: Monto;
  subtotal: Monto;
}

export interface PedidoDetalle extends PedidoResumen {
  direccion_entrega: string;
  items: PedidoItem[];
  tipos_reclamo_disponibles: TipoReclamo[];
}

export interface ReclamoResumen {
  codigo: string;
  pedido_codigo: string;
  tipo: TipoReclamo;
  estado: EstadoReclamo;
  creado_en: string;
  actualizado_en: string;
}

export interface ReclamoItem {
  pedido_item_id: number;
  producto: string;
  cantidad_afectada: number;
}

export interface ReclamoEvento {
  estado: EstadoReclamo;
  mensaje: string;
  actor: ActorEvento;
  creado_en: string;
}

export interface ReclamoDetalle extends ReclamoResumen {
  descripcion: string;
  foto_url: string | null;
  items: ReclamoItem[];
  eventos: ReclamoEvento[];
}

/** Cuerpo de los errores del backend: {"detail", "codigo", "errores"?}. */
export interface CuerpoError {
  detail: string;
  codigo: string;
  errores?: { campo: string; mensaje: string }[];
}
