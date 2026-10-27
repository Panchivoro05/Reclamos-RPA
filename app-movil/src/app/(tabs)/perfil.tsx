import Ionicons from '@expo/vector-icons/Ionicons';
import { ScrollView, Text, View } from 'react-native';

import { useMe } from '@/api/consultas';
import { Boton } from '@/components/Boton';
import { Cargando, ErrorPantalla } from '@/components/EstadosPantalla';
import { Tarjeta } from '@/components/Tarjeta';
import { config } from '@/config';
import type { NombreIcono } from '@/lib/catalogos';
import { cerrarSesionFirebase } from '@/lib/firebase';
import { queryClient } from '@/lib/queryClient';
import { useSesion } from '@/store/sesion';

async function cerrarSesion() {
  if (config.modoAuth === 'firebase') await cerrarSesionFirebase().catch(() => undefined);
  useSesion.getState().cerrar();
  queryClient.clear();
}

function Dato({ icono, etiqueta, valor }: { icono: NombreIcono; etiqueta: string; valor: string }) {
  return (
    <View className="flex-row items-center gap-3">
      <Ionicons name={icono} size={20} color="#B7330F" />
      <View className="flex-1">
        <Text className="text-xs text-neutral-500">{etiqueta}</Text>
        <Text className="text-base text-neutral-900">{valor}</Text>
      </View>
    </View>
  );
}

export default function Perfil() {
  const { data: cliente, isPending, error, refetch } = useMe();

  if (isPending) return <Cargando />;
  if (error) return <ErrorPantalla error={error} reintentar={() => void refetch()} />;

  return (
    <ScrollView contentContainerClassName="gap-4 p-4">
      <View className="items-center gap-2 py-4">
        <View className="h-20 w-20 items-center justify-center rounded-full bg-marca-100">
          <Text className="text-3xl font-bold text-marca-700">
            {cliente.nombre.charAt(0).toUpperCase()}
          </Text>
        </View>
        <Text className="text-xl font-bold text-neutral-900">{cliente.nombre}</Text>
      </View>
      <Tarjeta className="gap-4">
        <Dato icono="mail-outline" etiqueta="Correo" valor={cliente.email} />
        <Dato
          icono="logo-whatsapp"
          etiqueta="WhatsApp"
          valor={cliente.telefono_whatsapp ?? 'Sin registrar'}
        />
      </Tarjeta>
      <Boton
        titulo="Cerrar sesión"
        icono="log-out-outline"
        variante="peligro"
        onPress={() => void cerrarSesion()}
      />
      <Text className="text-center text-xs text-neutral-400">
        Modo {config.modoAuth} · {config.apiUrl}
      </Text>
    </ScrollView>
  );
}
