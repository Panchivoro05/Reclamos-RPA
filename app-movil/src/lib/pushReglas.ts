/** Reglas de las notificaciones push sin código nativo (se prueban con Jest). */

export const CANAL_ANDROID = 'reclamos';
const PATRON_CODIGO = /^RC-\d{4}-\d{6}$/;

export interface Entorno {
  os: string;
  enExpoGo: boolean;
  esDispositivo: boolean;
  projectId: string | null;
}

/** Por qué no se pueden usar push aquí (null si sí se puede). */
export function motivoSinPush(entorno: Entorno): string | null {
  if (entorno.os !== 'android' && entorno.os !== 'ios') return 'Push solo en Android e iOS.';
  if (entorno.enExpoGo) return 'Expo Go no recibe push: usa la development build.';
  // El emulador de Android con Google Play sí recibe push (FCM); el simulador de iOS no.
  if (entorno.os === 'ios' && !entorno.esDispositivo) return 'El simulador de iOS no recibe push.';
  if (!entorno.projectId) return 'Falta el projectId de EAS (ejecuta "eas init").';
  return null;
}

/** Código del reclamo que trae una notificación (si viene de nuestro backend). */
export function codigoDeNotificacion(datos: unknown): string | null {
  if (typeof datos !== 'object' || datos === null) return null;
  const codigo = (datos as { codigo?: unknown }).codigo;
  return typeof codigo === 'string' && PATRON_CODIGO.test(codigo) ? codigo : null;
}
