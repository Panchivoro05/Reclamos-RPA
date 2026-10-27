import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { Stack, useLocalSearchParams } from 'expo-router';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { urlApi } from '@/api/cliente';
import { useReclamo } from '@/api/consultas';
import type { ReclamoDetalle, ReclamoEvento } from '@/api/tipos';
import { Cargando, ErrorPantalla } from '@/components/EstadosPantalla';
import { Insignia } from '@/components/Insignia';
import { Tarjeta } from '@/components/Tarjeta';
import { ESTADOS_RECLAMO, TIPOS_RECLAMO_INFO } from '@/lib/catalogos';
import { formatoFechaHora } from '@/lib/formato';
import { useEncabezadosAuth } from '@/lib/useEncabezadosAuth';

export default function DetalleReclamo() {
  const { codigo } = useLocalSearchParams<{ codigo: string }>();
  const { data: reclamo, isPending, error, refetch, isRefetching } = useReclamo(codigo);

  return (
    <>
      <Stack.Screen options={{ title: codigo }} />
      {isPending ? (
        <Cargando />
      ) : error ? (
        <ErrorPantalla error={error} reintentar={() => void refetch()} />
      ) : (
        <ScrollView
          contentContainerClassName="gap-4 p-4"
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />
          }
        >
          <Datos reclamo={reclamo} />
          {reclamo.foto_url && <Foto ruta={reclamo.foto_url} />}
          <LineaDeTiempo eventos={reclamo.eventos} />
        </ScrollView>
      )}
    </>
  );
}

function Datos({ reclamo }: { reclamo: ReclamoDetalle }) {
  const tipo = TIPOS_RECLAMO_INFO[reclamo.tipo];
  return (
    <Tarjeta className="gap-3">
      <View className="flex-row items-center gap-3">
        <View className="rounded-full bg-marca-50 p-3">
          <Ionicons name={tipo.icono} size={22} color="#DC4316" />
        </View>
        <View className="flex-1">
          <Text className="text-base font-bold text-neutral-900">{tipo.etiqueta}</Text>
          <Text className="text-neutral-500">Pedido {reclamo.pedido_codigo}</Text>
        </View>
      </View>
      <Insignia estado={ESTADOS_RECLAMO[reclamo.estado]} />
      <Text className="text-neutral-700">{reclamo.descripcion}</Text>
      {reclamo.items.length > 0 && (
        <View className="gap-1 border-t border-neutral-200 pt-3">
          <Text className="font-semibold text-neutral-900">Productos afectados</Text>
          {reclamo.items.map((item) => (
            <Text key={item.pedido_item_id} className="text-neutral-700">
              {item.cantidad_afectada}× {item.producto}
            </Text>
          ))}
        </View>
      )}
    </Tarjeta>
  );
}

function Foto({ ruta }: { ruta: string }) {
  // La foto es privada: se pide con la misma sesión que el resto de la API.
  const encabezados = useEncabezadosAuth();
  return (
    <Tarjeta className="gap-3">
      <Text className="font-semibold text-neutral-900">Foto adjunta</Text>
      {encabezados && (
        <Image
          source={{ uri: urlApi(ruta), headers: encabezados }}
          contentFit="cover"
          transition={200}
          accessibilityLabel="Foto adjunta al reclamo"
          style={{ width: '100%', aspectRatio: 4 / 3, borderRadius: 12 }}
        />
      )}
    </Tarjeta>
  );
}

function LineaDeTiempo({ eventos }: { eventos: ReclamoEvento[] }) {
  return (
    <Tarjeta className="gap-1">
      <Text className="mb-3 text-base font-semibold text-neutral-900">Seguimiento</Text>
      {eventos.map((evento, indice) => {
        const estado = ESTADOS_RECLAMO[evento.estado];
        const ultimo = indice === eventos.length - 1;
        return (
          <View key={`${evento.creado_en}-${indice}`} className="flex-row gap-3">
            <View className="items-center">
              <View
                className="h-4 w-4 rounded-full border-2 border-white"
                style={{ backgroundColor: estado.color }}
              />
              {!ultimo && <View className="w-0.5 flex-1 bg-neutral-200" />}
            </View>
            <View className={`flex-1 gap-1 ${ultimo ? '' : 'pb-5'}`}>
              <Text className="font-semibold text-neutral-900">{estado.etiqueta}</Text>
              <Text className="text-neutral-700">{evento.mensaje}</Text>
              <Text className="text-xs text-neutral-500">{formatoFechaHora(evento.creado_en)}</Text>
            </View>
          </View>
        );
      })}
    </Tarjeta>
  );
}
