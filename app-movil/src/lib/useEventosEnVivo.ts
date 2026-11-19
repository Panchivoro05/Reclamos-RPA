/**
 * Mantiene abierta la conexión en vivo mientras haya sesión y la app esté en primer plano.
 *
 * Cada aviso solo dice "este reclamo cambió": se invalidan sus consultas y TanStack Query vuelve
 * a pedirlas a la API, que sigue siendo la fuente de verdad. Al (re)conectarse se recarga todo
 * lo de reclamos, por si algo cambió mientras la app estaba desconectada.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import { encabezadosAuth } from '@/api/cliente';
import { claves } from '@/api/consultas';
import { config } from '@/config';
import { useEstadoEnVivo } from '@/store/enVivo';
import { useSesion } from '@/store/sesion';

import { ConexionEventos, urlWebSocket } from './tiempoReal';

export function useEventosEnVivo(): void {
  const queryClient = useQueryClient();
  const email = useSesion((estado) => estado.sesion?.email ?? null);

  useEffect(() => {
    if (!email) return;
    const conexion = new ConexionEventos({
      url: urlWebSocket(config.apiUrl),
      obtenerEncabezados: encabezadosAuth,
      alCambiarEstado: (estado) => useEstadoEnVivo.setState({ estado }),
      alConectar: () => {
        void queryClient.invalidateQueries({ queryKey: claves.reclamos });
        void queryClient.invalidateQueries({ queryKey: claves.pedidos });
      },
      alActualizar: ({ codigo }) => {
        void queryClient.invalidateQueries({ queryKey: claves.reclamo(codigo) });
        void queryClient.invalidateQueries({ queryKey: claves.reclamos, exact: true });
        void queryClient.invalidateQueries({ queryKey: claves.pedidos });
      },
    });

    // En segundo plano se cierra (ahorra batería); al volver se reconecta y recarga.
    if (AppState.currentState !== 'background') conexion.iniciar();
    const suscripcion = AppState.addEventListener('change', (estado) => {
      if (estado === 'active') conexion.iniciar();
      else if (estado === 'background') conexion.detener();
    });
    return () => {
      suscripcion.remove();
      conexion.detener();
    };
  }, [email, queryClient]);
}
