import { formatoFechaHora, formatoSoles } from './formato';

describe('formato', () => {
  it('muestra montos en soles con dos decimales', () => {
    expect(formatoSoles('82.5')).toBe('S/ 82.50');
    expect(formatoSoles(25.9)).toBe('S/ 25.90');
  });

  it('convierte la fecha UTC a la hora de Lima (UTC-5)', () => {
    expect(formatoFechaHora('2026-10-27T04:23:00Z')).toBe('26 oct 2026, 23:23');
    expect(formatoFechaHora('2026-01-05T15:07:00+00:00')).toBe('5 ene 2026, 10:07');
  });
});
