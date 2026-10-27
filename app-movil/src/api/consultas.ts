/** Hooks de TanStack Query: cada pantalla pide sus datos por aquí. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './cliente';
import type {
  Cliente,
  PedidoDetalle,
  PedidoResumen,
  ReclamoDetalle,
  ReclamoResumen,
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

export function useReclamo(codigo: string) {
  return useQuery({
    queryKey: claves.reclamo(codigo),
    queryFn: () => api<ReclamoDetalle>(`/reclamos/${encodeURIComponent(codigo)}`),
  });
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
        // En React Native, FormData acepta un archivo local como {uri, name, type}.
        const archivo = {
          uri: reclamo.foto.uri,
          name: reclamo.foto.nombre,
          type: reclamo.foto.tipoMime,
        };
        formulario.append('foto', archivo as unknown as Blob);
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
