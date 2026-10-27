/**
 * Integración con Firebase Authentication (solo EXPO_PUBLIC_AUTH_MODE=firebase).
 *
 * La sesión de Firebase se mantiene en memoria: si se cierra la app, el backend
 * responde 401 al primer pedido y la app vuelve al login. Para recordarla entre
 * aperturas se puede agregar persistencia más adelante.
 */
import { getApps, initializeApp } from 'firebase/app';
import { getAuth, signInWithEmailAndPassword, signOut, type Auth } from 'firebase/auth';

import { config } from '@/config';

function auth(): Auth {
  const app = getApps()[0] ?? initializeApp(config.firebase);
  return getAuth(app);
}

export async function iniciarSesionFirebase(email: string, contrasena: string): Promise<string> {
  const credencial = await signInWithEmailAndPassword(auth(), email, contrasena);
  return credencial.user.email ?? email;
}

/** ID token vigente (Firebase lo renueva solo cuando está por vencer). */
export async function obtenerTokenFirebase(): Promise<string | null> {
  return (await auth().currentUser?.getIdToken()) ?? null;
}

export async function cerrarSesionFirebase(): Promise<void> {
  await signOut(auth());
}
