import { intervaloDeRespaldo } from './consultas';

test('sin conexión en vivo, consulta cada 3 s solo mientras se procesa', () => {
  expect(intervaloDeRespaldo('en_resolucion', false)).toBe(3000);
  expect(intervaloDeRespaldo('recibido', false)).toBe(3000);
  expect(intervaloDeRespaldo('resuelto', false)).toBe(false);
  expect(intervaloDeRespaldo(undefined, false)).toBe(false);
});

test('con conexión en vivo no consulta: espera los avisos', () => {
  expect(intervaloDeRespaldo('en_resolucion', true)).toBe(false);
});
