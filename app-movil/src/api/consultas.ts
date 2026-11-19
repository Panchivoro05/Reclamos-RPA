/** Hooks de TanStack Query: cada pantalla pide sus datos por aquí. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { File } from 'expo-file-system';

import { api } from './cliente';
import type {
  Cliente,
  EstadoReclamo,
  MensajeChat,
  PedidoDetalle,
  PedidoResumen,
  ReclamoDetalle,
  ReclamoResumen,
  RespuestaAsistente,
  TipoReclamo,
} from './tipos';

export const claves = {
  me: ['me'] as const,
  pedidos: ['pedidos'] as const,
  pedido: (codigo: string) => ['pedidos', codigo] as const,
  reclamos: ['reclamos'] as const,
  reclamo: (codigo: string) => ['reclamos', codigo] as const,
};

export function useMe() {
  return useQuery({ queryKey: claves.me, queryFn: () => api<Cliente>('/me') });
}

export function usePedidos() {
  return useQuery({ queryKey: claves.pedidos, queryFn: () => api<PedidoResumen[]>('/pedidos') });
}

export function usePedido(codigo: string) {
  return useQuery({
    queryKey: claves.pedido(codigo),
    queryFn: () => api<PedidoDetalle>(`/pedidos/${encodeURIComponent(codigo)}`),
  });
}

export function useReclamos() {
  return useQuery({
    queryKey: claves.reclamos,
    queryFn: () => api<ReclamoResumen[]>('/reclamos'),
  });
}

/** Estados en los que el worker todavía está trabajando el reclamo. */
export const ESTADOS_EN_PROCESO = new Set<EstadoReclamo>([
  'recibido',
  'en_validacion',
  'validado',
  'en_resolucion',
]);

/**
 * Detalle de un reclamo. Con la conexión en vivo, se recarga cuando llega un aviso
 * (useEventosEnVivo). Sin ella, mientras el reclamo se procesa se consulta cada 3 s.
 */
export function useReclamo(codigo: string, enVivo: boolean) {
  return useQuery({
    queryKey: claves.reclamo(codigo),
    queryFn: () => api<ReclamoDetalle>(`/reclamos/${encodeURIComponent(codigo)}`),
    refetchInterval: (consulta) => intervaloDeRespaldo(consulta.state.data?.estado, enVivo),
  });
}

export function intervaloDeRespaldo(
  estado: EstadoReclamo | undefined,
  enVivo: boolean,
): number | false {
  return !enVivo && estado !== undefined && ESTADOS_EN_PROCESO.has(estado) ? 3000 : false;
}

export interface FotoAdjunta {
  uri: string;
  nombre: string;
  tipoMime: string;
}

export interface NuevoReclamo {
  pedido_codigo: string;
  tipo: TipoReclamo;
  descripcion: string;
  items: { pedido_item_id: number; cantidad_afectada: number }[];
  foto: FotoAdjunta | null;
}

export function useCrearReclamo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reclamo: NuevoReclamo) => {
      const formulario = new FormData();
      formulario.append('pedido_codigo', reclamo.pedido_codigo);
      formulario.append('tipo', reclamo.tipo);
      formulario.append('descripcion', reclamo.descripcion);
      formulario.append('items', JSON.stringify(reclamo.items));
      if (reclamo.foto) {
        // Desde el SDK 58 el fetch global es expo/fetch, que no acepta el antiguo objeto
        // {uri, name, type} de React Native. File de expo-file-system es un Blob real.
        formulario.append('foto', new File(reclamo.foto.uri), reclamo.foto.nombre);
      }
      return api<ReclamoDetalle>('/reclamos', { method: 'POST', body: formulario });
    },
    onSuccess: (reclamo) => {
      queryClient.setQueryData(claves.reclamo(reclamo.codigo), reclamo);
      void queryClient.invalidateQueries({ queryKey: claves.reclamos });
      void queryClient.invalidateQueries({ queryKey: claves.pedido(reclamo.pedido_codigo) });
    },
  });
}

/** Pregunta al asistente; se envía la conversación completa (el backend no guarda chats). */
export function useConsultarAsistente() {
  return useMutation({
    mutationFn: (mensajes: MensajeChat[]) =>
      api<RespuestaAsistente>('/asistente', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensajes }),
      }),
  });
}
