/** Estados de carga, vacío y error que comparten todas las pantallas. */

import Ionicons from '@expo/vector-icons/Ionicons';
import { ActivityIndicator, Text, View } from 'react-native';

import { ApiError } from '@/api/cliente';
import type { NombreIcono } from '@/lib/catalogos';

import { Boton } from './Boton';

export function Cargando({ mensaje = 'Cargando…' }: { mensaje?: string }) {
  return (
    <View className="flex-1 items-center justify-center gap-3 bg-neutral-50 p-6">
      <ActivityIndicator size="large" color="#F05A28" />
      <Text className="text-neutral-500">{mensaje}</Text>
    </View>
  );
}

interface PropsVacio {
  icono: NombreIcono;
  titulo: string;
  mensaje: string;
}

export function Vacio({ icono, titulo, mensaje }: PropsVacio) {
  return (
    <View className="flex-1 items-center justify-center gap-3 p-8">
      <View className="rounded-full bg-marca-50 p-5">
        <Ionicons name={icono} size={40} color="#F05A28" />
      </View>
      <Text className="text-center text-lg font-semibold text-neutral-900">{titulo}</Text>
      <Text className="text-center text-neutral-500">{mensaje}</Text>
    </View>
  );
}

export function mensajeDeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Ocurrió un error inesperado. Inténtalo otra vez.';
}

interface PropsError {
  error: unknown;
  reintentar?: () => void;
}

export function ErrorPantalla({ error, reintentar }: PropsError) {
  const sinConexion = error instanceof ApiError && error.codigo === 'sin_conexion';
  return (
    <View className="flex-1 items-center justify-center gap-4 bg-neutral-50 p-8">
      <View className="rounded-full bg-rose-50 p-5">
        <Ionicons
          name={sinConexion ? 'cloud-offline-outline' : 'alert-circle-outline'}
          size={40}
          color="#E11D48"
        />
      </View>
      <Text className="text-center text-lg font-semibold text-neutral-900">
        {sinConexion ? 'Sin conexión' : 'Algo salió mal'}
      </Text>
      <Text className="text-center text-neutral-500">{mensajeDeError(error)}</Text>
      {reintentar && (
        <Boton titulo="Reintentar" icono="refresh" variante="secundario" onPress={reintentar} />
      )}
    </View>
  );
}

/** Mensaje de error dentro de un formulario. */
export function AvisoError({ mensaje }: { mensaje: string }) {
  return (
    <View className="flex-row items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3">
      <Ionicons name="alert-circle" size={20} color="#E11D48" />
      <Text className="flex-1 text-rose-800">{mensaje}</Text>
    </View>
  );
}
