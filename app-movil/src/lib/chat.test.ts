import type { MensajeChat } from '@/api/tipos';

import { historialParaEnviar, MAXIMO_CARACTERES, MAXIMO_MENSAJES, prepararPregunta } from './chat';

const cliente = (texto: string): MensajeChat => ({ rol: 'cliente', texto });
const asistente = (texto: string): MensajeChat => ({ rol: 'asistente', texto });

describe('prepararPregunta', () => {
  it('quita espacios de más', () => {
    expect(prepararPregunta('  ¿Cómo   va\n mi reclamo? ')).toBe('¿Cómo va mi reclamo?');
  });

  it('deja vacía una pregunta en blanco', () => {
    expect(prepararPregunta('   \n ')).toBe('');
  });

  it('respeta el máximo de caracteres', () => {
    expect(prepararPregunta('a'.repeat(MAXIMO_CARACTERES + 50))).toHaveLength(MAXIMO_CARACTERES);
  });
});

describe('historialParaEnviar', () => {
  it('envía la conversación completa si es corta', () => {
    const historial = [cliente('Hola'), asistente('¡Hola!'), cliente('¿Y mi reclamo?')];
    expect(historialParaEnviar(historial)).toEqual(historial);
  });

  it('se queda con los últimos mensajes y empieza por uno del cliente', () => {
    const historial = Array.from({ length: MAXIMO_MENSAJES + 5 }, (_, i) =>
      i % 2 === 0 ? cliente(`p${i}`) : asistente(`r${i}`),
    );
    const enviado = historialParaEnviar(historial);
    expect(enviado.length).toBeLessThanOrEqual(MAXIMO_MENSAJES);
    expect(enviado[0]?.rol).toBe('cliente');
    expect(enviado.at(-1)).toEqual(historial.at(-1));
  });

  it('sin preguntas del cliente no envía nada', () => {
    expect(historialParaEnviar([asistente('Hola')])).toEqual([]);
  });
});
