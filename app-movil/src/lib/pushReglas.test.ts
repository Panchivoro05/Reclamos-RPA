import { codigoDeNotificacion, type Entorno, motivoSinPush } from './pushReglas';

const android: Entorno = {
  os: 'android',
  enExpoGo: false,
  esDispositivo: true,
  projectId: 'abc-123',
};

test('en una development build de Android se usan push (también en el emulador)', () => {
  expect(motivoSinPush(android)).toBeNull();
  expect(motivoSinPush({ ...android, esDispositivo: false })).toBeNull();
});

test('casos sin push', () => {
  expect(motivoSinPush({ ...android, enExpoGo: true })).toMatch(/Expo Go/);
  expect(motivoSinPush({ ...android, projectId: null })).toMatch(/eas init/);
  expect(motivoSinPush({ ...android, os: 'web' })).toMatch(/Android e iOS/);
  expect(motivoSinPush({ ...android, os: 'ios', esDispositivo: false })).toMatch(/simulador/);
});

test('solo se abre un reclamo con un código válido', () => {
  expect(codigoDeNotificacion({ codigo: 'RC-2026-000001', estado: 'resuelto' })).toBe(
    'RC-2026-000001',
  );
  expect(codigoDeNotificacion({ codigo: '../../login' })).toBeNull();
  expect(codigoDeNotificacion({})).toBeNull();
  expect(codigoDeNotificacion(null)).toBeNull();
});
