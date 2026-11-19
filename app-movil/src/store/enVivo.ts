import { create } from 'zustand';

import type { EstadoConexion } from '@/lib/tiempoReal';

/** Estado de la conexión en vivo (lo actualiza useEventosEnVivo y lo leen las pantallas). */
export const useEstadoEnVivo = create<{ estado: EstadoConexion }>(() => ({
  estado: 'desconectado',
}));
