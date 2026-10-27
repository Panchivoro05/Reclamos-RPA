/**
 * Configuración leída de variables EXPO_PUBLIC_* (ver .env.example).
 * Expo las reemplaza al compilar, por eso se leen con su nombre completo.
 */

export type ModoAuth = 'dev' | 'firebase';

function leerModoAuth(valor: string | undefined): ModoAuth {
  return valor === 'firebase' ? 'firebase' : 'dev';
}

export const config = {
  apiUrl: (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, ''),
  modoAuth: leerModoAuth(process.env.EXPO_PUBLIC_AUTH_MODE),
  firebase: {
    apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY ?? '',
    authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN ?? '',
    projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID ?? '',
    appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID ?? '',
  },
} as const;

/** Clientes de la semilla del backend (python -m app.seed), para el login en modo dev. */
export const CLIENTES_DEMO = [
  { email: 'cliente1@burgerya.pe', nombre: 'María Quispe' },
  { email: 'cliente2@burgerya.pe', nombre: 'Jorge Ramírez' },
] as const;

/** Debe coincidir con FOTO_MAX_BYTES del backend. */
export const FOTO_MAX_BYTES = 5 * 1024 * 1024;
