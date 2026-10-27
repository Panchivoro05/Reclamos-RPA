import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { FlatList, RefreshControl, Text, View } from 'react-native';

import { useReclamos } from '@/api/consultas';
import { Cargando, ErrorPantalla, Vacio } from '@/components/EstadosPantalla';
import { Insignia } from '@/components/Insignia';
import { Tarjeta } from '@/components/Tarjeta';
import { ESTADOS_RECLAMO, TIPOS_RECLAMO_INFO } from '@/lib/catalogos';
import { formatoFechaHora } from '@/lib/formato';

export default function MisReclamos() {
  const { data, isPending, error, refetch, isRefetching } = useReclamos();

  if (isPending) return <Cargando mensaje="Buscando tus reclamos…" />;
  if (error) return <ErrorPantalla error={error} reintentar={() => void refetch()} />;

  return (
    <FlatList
      data={data}
      keyExtractor={(reclamo) => reclamo.codigo}
      contentContainerClassName="flex-grow gap-3 p-4"
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
      ListEmptyComponent={
        <Vacio
          icono="happy-outline"
          titulo="No tienes reclamos"
          mensaje="Si algo sale mal con un pedido, regístralo desde la pestaña Pedidos."
        />
      }
      renderItem={({ item: reclamo }) => {
        const tipo = TIPOS_RECLAMO_INFO[reclamo.tipo];
        return (
          <Tarjeta onPress={() => router.push(`/reclamos/${reclamo.codigo}`)}>
            <View className="flex-row items-center gap-3">
              <View className="rounded-full bg-marca-50 p-3">
                <Ionicons name={tipo.icono} size={22} color="#DC4316" />
              </View>
              <View className="flex-1 gap-1">
                <Text className="text-base font-bold text-neutral-900">{reclamo.codigo}</Text>
                <Text className="text-neutral-700">{tipo.etiqueta}</Text>
                <Text className="text-xs text-neutral-500">
                  Pedido {reclamo.pedido_codigo} · {formatoFechaHora(reclamo.creado_en)}
                </Text>
                <Insignia estado={ESTADOS_RECLAMO[reclamo.estado]} />
              </View>
              <Ionicons name="chevron-forward" size={18} color="#A3A3A3" />
            </View>
          </Tarjeta>
        );
      }}
    />
  );
}
