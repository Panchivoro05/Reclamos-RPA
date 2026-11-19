/**
 * Notificaciones push (expo-notifications + Expo Push Service).
 *
 * Al iniciar sesión se pide permiso, se obtiene el token de Expo del celular y se registra en
 * la API (POST /dispositivos). Al cerrar sesión se da de baja. El backend envía un aviso por
 * cada cambio de estado del reclamo; al tocarlo se abre su detalle.
 *
 * Solo funciona en una development build (o en la app final): desde el SDK 53, Expo Go en
 * Android no recibe push. Por eso expo-notifications se carga solo cuando se puede usar: en
 * Expo Go la app funciona igual, sin push y sin advertencias.
 */

import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { isRunningInExpoGo } from 'expo';
import { Platform } from 'react-native';

import { api } from '@/api/cliente';

import { CANAL_ANDROID, codigoDeNotificacion, type Entorno, motivoSinPush } from './pushReglas';

type ModuloNotificaciones = typeof import('expo-notifications');
type NotificationResponse = import('expo-notifications').NotificationResponse;

function entornoActual(): Entorno {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return {
    os: Platform.OS,
    enExpoGo: isRunningInExpoGo(),
    esDispositivo: Device.isDevice,
    projectId: Constants.easConfig?.projectId ?? extra?.eas?.projectId ?? null,
  };
}

let modulo: Promise<ModuloNotificaciones> | null = null;

/** Carga expo-notifications (solo si aquí hay push) y configura cómo se muestran los avisos. */
function notificaciones(): Promise<ModuloNotificaciones> | null {
  const motivo = motivoSinPush(entornoActual());
  if (motivo) {
    if (__DEV__) console.info(`Push desactivado: ${motivo}`);
    return null;
  }
  modulo ??= import('expo-notifications').then((Notifications) => {
    // Los avisos se muestran aunque la app esté abierta.
    Notifications.setNotificationHandler({
      handleNotification: () =>
        Promise.resolve({
          shouldShowBanner: true,
          shouldShowList: true,
          shouldPlaySound: true,
          shouldSetBadge: false,
        }),
    });
    return Notifications;
  });
  return modulo;
}

let tokenRegistrado: string | null = null;

/** Pide permiso, obtiene el token y lo registra en la API. No lanza: sin push la app sigue. */
export async function registrarParaPush(): Promise<void> {
  const cargando = notificaciones();
  if (!cargando) return;
  try {
    const Notifications = await cargando;
    if (Platform.OS === 'android') {
      // El backend envía con channelId "reclamos". Android 13+ pide el permiso recién
      // cuando existe un canal, por eso se crea antes.
      await Notifications.setNotificationChannelAsync(CANAL_ANDROID, {
        name: 'Estado de tus reclamos',
        importance: Notifications.AndroidImportance.HIGH,
        lightColor: '#DC4316',
      });
    }
    let permiso = await Notifications.getPermissionsAsync();
    if (!permiso.granted && permiso.canAskAgain) {
      permiso = await Notifications.requestPermissionsAsync();
    }
    if (!permiso.granted) return;

    const { data: token } = await Notifications.getExpoPushTokenAsync({
      projectId: entornoActual().projectId ?? undefined,
    });
    await api<void>('/dispositivos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, plataforma: Platform.OS }),
    });
    tokenRegistrado = token;
  } catch (error) {
    if (__DEV__) console.warn('No se pudo registrar el celular para push:', error);
  }
}

/** Al cerrar sesión (con la sesión todavía activa, para autenticar la baja). */
export async function darDeBajaPush(): Promise<void> {
  const token = tokenRegistrado;
  if (!token) return;
  tokenRegistrado = null;
  await api<void>(`/dispositivos/${encodeURIComponent(token)}`, { method: 'DELETE' }).catch(
    () => undefined,
  );
}

/**
 * Llama a `abrir(codigo)` cuando el cliente toca un aviso, incluido el que abrió la app
 * estando cerrada. Devuelve la función para dejar de escuchar.
 */
export function alTocarAviso(abrir: (codigo: string) => void): () => void {
  const cargando = notificaciones();
  if (!cargando) return () => undefined;
  let activo = true;
  let quitar: (() => void) | null = null;

  void cargando.then((Notifications) => {
    if (!activo) return;
    const atender = (respuesta: NotificationResponse) => {
      const codigo = codigoDeNotificacion(respuesta.notification.request.content.data);
      if (codigo) abrir(codigo);
    };
    const ultima = Notifications.getLastNotificationResponse();
    if (ultima) {
      // Se limpia para no volver a abrirlo cada vez que se monta la pantalla.
      Notifications.clearLastNotificationResponse();
      atender(ultima);
    }
    const suscripcion = Notifications.addNotificationResponseReceivedListener(atender);
    quitar = () => suscripcion.remove();
  });

  return () => {
    activo = false;
    quitar?.();
  };
}
