/** Textos, íconos y colores de estados y tipos: un solo lugar para que la app sea consistente.
 *  Las clases se escriben completas para que Tailwind las detecte al compilar. */

import type Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps } from 'react';

import type { EstadoPedido, EstadoReclamo, TipoReclamo } from '@/api/tipos';

export type NombreIcono = ComponentProps<typeof Ionicons>['name'];

export interface EstiloEstado {
  etiqueta: string;
  /** Clases de la insignia. */
  fondo: string;
  texto: string;
  /** Color sólido (puntos de la línea de tiempo). */
  color: string;
}

export const ESTADOS_PEDIDO: Record<EstadoPedido, EstiloEstado> = {
  en_preparacion: {
    etiqueta: 'En preparación',
    fondo: 'bg-amber-100',
    texto: 'text-amber-800',
    color: '#D97706',
  },
  en_camino: {
    etiqueta: 'En camino',
    fondo: 'bg-sky-100',
    texto: 'text-sky-800',
    color: '#0284C7',
  },
  entregado: {
    etiqueta: 'Entregado',
    fondo: 'bg-emerald-100',
    texto: 'text-emerald-800',
    color: '#059669',
  },
  cancelado: {
    etiqueta: 'Cancelado',
    fondo: 'bg-neutral-200',
    texto: 'text-neutral-700',
    color: '#737373',
  },
};

export const ESTADOS_RECLAMO: Record<EstadoReclamo, EstiloEstado> = {
  recibido: { etiqueta: 'Recibido', fondo: 'bg-sky-100', texto: 'text-sky-800', color: '#0284C7' },
  en_validacion: {
    etiqueta: 'En validación',
    fondo: 'bg-amber-100',
    texto: 'text-amber-800',
    color: '#D97706',
  },
  validado: {
    etiqueta: 'Validado',
    fondo: 'bg-indigo-100',
    texto: 'text-indigo-800',
    color: '#4F46E5',
  },
  en_resolucion: {
    etiqueta: 'En resolución',
    fondo: 'bg-violet-100',
    texto: 'text-violet-800',
    color: '#7C3AED',
  },
  resuelto: {
    etiqueta: 'Resuelto',
    fondo: 'bg-emerald-100',
    texto: 'text-emerald-800',
    color: '#059669',
  },
  cerrado: {
    etiqueta: 'Cerrado',
    fondo: 'bg-neutral-200',
    texto: 'text-neutral-700',
    color: '#737373',
  },
  escalado: {
    etiqueta: 'En revisión por un agente',
    fondo: 'bg-rose-100',
    texto: 'text-rose-800',
    color: '#E11D48',
  },
};

export interface InfoTipoReclamo {
  etiqueta: string;
  descripcion: string;
  icono: NombreIcono;
  fotoObligatoria: boolean;
}

export const TIPOS_RECLAMO_INFO: Record<TipoReclamo, InfoTipoReclamo> = {
  producto_equivocado: {
    etiqueta: 'Producto equivocado',
    descripcion: 'Me llegó algo distinto a lo que pedí.',
    icono: 'swap-horizontal',
    fotoObligatoria: true,
  },
  pedido_incompleto: {
    etiqueta: 'Pedido incompleto',
    descripcion: 'Faltó uno o más productos.',
    icono: 'bag-remove-outline',
    fotoObligatoria: false,
  },
  mal_estado: {
    etiqueta: 'Producto en mal estado',
    descripcion: 'Llegó frío, aplastado o derramado.',
    icono: 'warning-outline',
    fotoObligatoria: true,
  },
  demora: {
    etiqueta: 'Demora en la entrega',
    descripcion: 'Mi pedido tardó demasiado o no llega.',
    icono: 'time-outline',
    fotoObligatoria: false,
  },
};
