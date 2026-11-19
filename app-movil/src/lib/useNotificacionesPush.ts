import { router } from 'expo-router';
import { useEffect } from 'react';

import { useSesion } from '@/store/sesion';

import { alTocarAviso, registrarParaPush } from './push';

/** Registra el celular para push al iniciar sesión y abre el reclamo al tocar un aviso. */
export function useNotificacionesPush(): void {
  const email = useSesion((estado) => estado.sesion?.email ?? null);

  useEffect(() => {
    if (!email) return;
    void registrarParaPush();
    return alTocarAviso((codigo) => router.push(`/reclamos/${codigo}`));
  }, [email]);
}
