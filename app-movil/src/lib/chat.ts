/** Reglas del chat con el asistente (sin React: se prueban con Jest). */

import type { MensajeChat } from '@/api/tipos';

/** Lo que acepta la API: hasta 30 mensajes de hasta 1000 caracteres. */
export const MAXIMO_MENSAJES = 30;
export const MAXIMO_CARACTERES = 1000;

export const SUGERENCIAS = [
  '¿Cómo van mis reclamos?',
  '¿Qué tenía mi último pedido?',
  '¿Cómo hago un reclamo?',
] as const;

export const BIENVENIDA =
  '¡Hola! Soy el asistente de BurgerYa. Puedo contarte cómo va tu reclamo o qué tenía tu ' +
  'pedido. ¿En qué te ayudo?';

/** Limpia la pregunta: sin espacios de más y dentro del máximo. Vacía si no hay nada. */
export function prepararPregunta(texto: string): string {
  return texto.trim().replace(/\s+/g, ' ').slice(0, MAXIMO_CARACTERES);
}

/** La conversación que se envía: los últimos mensajes, empezando por uno del cliente. */
export function historialParaEnviar(historial: MensajeChat[]): MensajeChat[] {
  const recientes = historial.slice(-MAXIMO_MENSAJES);
  const inicio = recientes.findIndex((m) => m.rol === 'cliente');
  return inicio === -1 ? [] : recientes.slice(inicio);
}
