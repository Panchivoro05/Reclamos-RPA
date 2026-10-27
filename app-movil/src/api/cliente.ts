/** Cliente HTTP de la API: agrega la sesión, traduce errores y tipa las respuestas. */

import { config } from '@/config';
import { obtenerTokenFirebase } from '@/lib/firebase';
import { useSesion } from '@/store/sesion';

import type { CuerpoError } from './tipos';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly codigo: string,
    mensaje: string,
    readonly errores: { campo: string; mensaje: string }[] = [],
  ) {
    super(mensaje);
    this.name = 'ApiError';
  }
}

export async function encabezadosAuth(): Promise<Record<string, string>> {
  const sesion = useSesion.getState().sesion;
  if (!sesion) return {};
  if (sesion.modo === 'dev') return { 'X-Dev-User': sesion.email };
  const token = await obtenerTokenFirebase();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function esCuerpoError(valor: unknown): valor is CuerpoError {
  return (
    typeof valor === 'object' && valor !== null && typeof (valor as CuerpoError).detail === 'string'
  );
}

export async function api<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${config.apiUrl}/api/v1${ruta}`, {
      ...init,
      headers: { Accept: 'application/json', ...(await encabezadosAuth()), ...init.headers },
    });
  } catch {
    throw new ApiError(
      0,
      'sin_conexion',
      'No pudimos conectarnos con BurgerYa. Revisa tu conexión a internet e inténtalo otra vez.',
    );
  }

  const cuerpo: unknown = await respuesta.json().catch(() => null);
  if (respuesta.ok) return cuerpo as T;

  if (respuesta.status === 401) {
    // La sesión ya no es válida: se cierra y la navegación vuelve al login.
    useSesion.getState().cerrar();
  }
  if (esCuerpoError(cuerpo)) {
    throw new ApiError(respuesta.status, cuerpo.codigo, cuerpo.detail, cuerpo.errores);
  }
  throw new ApiError(
    respuesta.status,
    'error_servidor',
    'Tuvimos un problema de nuestro lado. Inténtalo de nuevo en unos minutos.',
  );
}

/** URL absoluta de un recurso de la API (por ejemplo, la foto de un reclamo). */
export function urlApi(rutaRelativa: string): string {
  return `${config.apiUrl}${rutaRelativa}`;
}
