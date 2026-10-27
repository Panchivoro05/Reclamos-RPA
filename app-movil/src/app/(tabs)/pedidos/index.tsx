import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { FlatList, RefreshControl, Text, View } from 'react-native';

import { usePedidos } from '@/api/consultas';
import { Cargando, ErrorPantalla, Vacio } from '@/components/EstadosPantalla';
import { Insignia } from '@/components/Insignia';
import { Tarjeta } from '@/components/Tarjeta';
import { ESTADOS_PEDIDO } from '@/lib/catalogos';
import { formatoFechaHora, formatoSoles } from '@/lib/formato';

export default function MisPedidos() {
  const { data, isPending, error, refetch, isRefetching } = usePedidos();

  if (isPending) return <Cargando mensaje="Buscando tus pedidos…" />;
  if (error) return <ErrorPantalla error={error} reintentar={() => void refetch()} />;

  return (
    <FlatList
      data={data}
      keyExtractor={(pedido) => pedido.codigo}
      contentContainerClassName="flex-grow gap-3 p-4"
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
      ListEmptyComponent={
        <Vacio
          icono="fast-food-outline"
          titulo="Aún no tienes pedidos"
          mensaje="Cuando hagas tu primer pedido en BurgerYa, lo verás aquí."
        />
      }
      renderItem={({ item: pedido }) => (
        <Tarjeta onPress={() => router.push(`/pedidos/${pedido.codigo}`)}>
          <View className="flex-row items-start justify-between gap-3">
            <View className="flex-1 gap-1">
              <Text className="text-base font-bold text-neutral-900">{pedido.codigo}</Text>
              <Text className="text-neutral-500">{formatoFechaHora(pedido.creado_en)}</Text>
              <Text className="text-neutral-500">
                {pedido.local} · {pedido.cantidad_productos}{' '}
                {pedido.cantidad_productos === 1 ? 'producto' : 'productos'}
              </Text>
            </View>
            <View className="items-end gap-2">
              <Text className="text-base font-bold text-neutral-900">
                {formatoSoles(pedido.total)}
              </Text>
              <Insignia estado={ESTADOS_PEDIDO[pedido.estado]} />
            </View>
            <Ionicons name="chevron-forward" size={18} color="#A3A3A3" />
          </View>
        </Tarjeta>
      )}
    />
  );
}
