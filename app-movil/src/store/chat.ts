import { create } from 'zustand';

import type { MensajeChat } from '@/api/tipos';

/**
 * Conversación con el asistente. Vive solo en memoria (el backend no guarda chats): se
 * conserva al cambiar de pestaña y se borra al cerrar sesión o al reiniciar la app.
 */
interface EstadoChat {
  mensajes: MensajeChat[];
  agregar: (mensaje: MensajeChat) => void;
  limpiar: () => void;
}

export const useChat = create<EstadoChat>((set) => ({
  mensajes: [],
  agregar: (mensaje) => set((estado) => ({ mensajes: [...estado.mensajes, mensaje] })),
  limpiar: () => set({ mensajes: [] }),
}));
