import * as SecureStore from 'expo-secure-store';
import { useSyncExternalStore } from 'react';
import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';

import type { ModoAuth } from '@/config';

export interface Sesion {
  modo: ModoAuth;
  email: string;
}

interface EstadoSesion {
  sesion: Sesion | null;
  iniciar: (sesion: Sesion) => void;
  cerrar: () => void;
}

// SecureStore guarda en el llavero del sistema (Keychain en iOS, Keystore en Android).
const almacenamientoSeguro: StateStorage = {
  getItem: (clave) => SecureStore.getItemAsync(clave),
  setItem: (clave, valor) => SecureStore.setItemAsync(clave, valor),
  removeItem: (clave) => SecureStore.deleteItemAsync(clave),
};

export const useSesion = create<EstadoSesion>()(
  persist(
    (set) => ({
      sesion: null,
      iniciar: (sesion) => set({ sesion }),
      cerrar: () => set({ sesion: null }),
    }),
    {
      name: 'burgerya.sesion',
      storage: createJSONStorage(() => almacenamientoSeguro),
      partialize: (estado) => ({ sesion: estado.sesion }),
    },
  ),
);

/** true cuando ya se leyó la sesión guardada (antes no se sabe si mostrar login). */
export function useSesionHidratada(): boolean {
  return useSyncExternalStore(
    (avisar) => useSesion.persist.onFinishHydration(avisar),
    () => useSesion.persist.hasHydrated(),
  );
}
