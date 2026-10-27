import Ionicons from '@expo/vector-icons/Ionicons';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { usePedido } from '@/api/consultas';
import type { PedidoDetalle } from '@/api/tipos';
import { Boton } from '@/components/Boton';
import { Cargando, ErrorPantalla } from '@/components/EstadosPantalla';
import { Insignia } from '@/components/Insignia';
import { Tarjeta } from '@/components/Tarjeta';
import { ESTADOS_PEDIDO } from '@/lib/catalogos';
import { formatoFechaHora, formatoSoles } from '@/lib/formato';

export default function DetallePedido() {
  const { codigo } = useLocalSearchParams<{ codigo: string }>();
  const { data: pedido, isPending, error, refetch, isRefetching } = usePedido(codigo);

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
          <Resumen pedido={pedido} />
          <Productos pedido={pedido} />
          <AccionReclamo pedido={pedido} />
        </ScrollView>
      )}
    </>
  );
}

function Fila({
  icono,
  texto,
}: {
  icono: 'time-outline' | 'storefront-outline' | 'location-outline';
  texto: string;
}) {
  return (
    <View className="flex-row items-center gap-2">
      <Ionicons name={icono} size={16} color="#737373" />
      <Text className="flex-1 text-neutral-600">{texto}</Text>
    </View>
  );
}

function Resumen({ pedido }: { pedido: PedidoDetalle }) {
  return (
    <Tarjeta className="gap-3">
      <Insignia estado={ESTADOS_PEDIDO[pedido.estado]} />
      <Fila icono="time-outline" texto={`Pedido el ${formatoFechaHora(pedido.creado_en)}`} />
      {pedido.entregado_en && (
        <Fila
          icono="time-outline"
          texto={`Entregado el ${formatoFechaHora(pedido.entregado_en)}`}
        />
      )}
      <Fila icono="storefront-outline" texto={pedido.local} />
      <Fila icono="location-outline" texto={pedido.direccion_entrega} />
    </Tarjeta>
  );
}

function Productos({ pedido }: { pedido: PedidoDetalle }) {
  return (
    <Tarjeta className="gap-3">
      <Text className="text-base font-semibold text-neutral-900">Productos</Text>
      {pedido.items.map((item) => (
        <View key={item.id} className="flex-row justify-between gap-3">
          <Text className="flex-1 text-neutral-700">
            <Text className="font-semibold">{item.cantidad}×</Text> {item.producto}
          </Text>
          <Text className="text-neutral-700">{formatoSoles(item.subtotal)}</Text>
        </View>
      ))}
      <View className="flex-row justify-between border-t border-neutral-200 pt-3">
        <Text className="text-base font-bold text-neutral-900">Total</Text>
        <Text className="text-base font-bold text-neutral-900">{formatoSoles(pedido.total)}</Text>
      </View>
    </Tarjeta>
  );
}

function AccionReclamo({ pedido }: { pedido: PedidoDetalle }) {
  if (pedido.tipos_reclamo_disponibles.length > 0) {
    return (
      <Boton
        titulo="Tengo un problema con mi pedido"
        icono="chatbubble-ellipses-outline"
        onPress={() =>
          router.push({ pathname: '/nuevo-reclamo', params: { pedido: pedido.codigo } })
        }
      />
    );
  }
  // Explica por qué no aparece el botón.
  const motivo =
    pedido.estado === 'cancelado'
      ? 'Este pedido fue cancelado.'
      : pedido.estado === 'en_preparacion'
        ? 'Tu pedido se está preparando. Si demora, podrás avisarnos cuando esté en camino.'
        : 'El plazo para reclamar este pedido ya venció o ya tienes reclamos abiertos para él.';
  return <Text className="px-2 text-center text-sm text-neutral-500">{motivo}</Text>;
}
