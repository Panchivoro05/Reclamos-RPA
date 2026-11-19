import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { urlApi } from '@/api/cliente';
import { ESTADOS_EN_PROCESO, useReclamo } from '@/api/consultas';
import type { ReclamoDetalle, ReclamoEvento, Resolucion } from '@/api/tipos';
import { Boton } from '@/components/Boton';
import { Cargando, ErrorPantalla } from '@/components/EstadosPantalla';
import { Insignia } from '@/components/Insignia';
import { Tarjeta } from '@/components/Tarjeta';
import { ESTADOS_RECLAMO, TIPOS_RECLAMO_INFO } from '@/lib/catalogos';
import { formatoFechaHora } from '@/lib/formato';
import { useEncabezadosAuth } from '@/lib/useEncabezadosAuth';
import { useEstadoEnVivo } from '@/store/enVivo';

export default function DetalleReclamo() {
  const { codigo } = useLocalSearchParams<{ codigo: string }>();
  const enVivo = useEstadoEnVivo((estado) => estado.estado === 'en_vivo');
  const { data: reclamo, isPending, error, refetch, isRefetching } = useReclamo(codigo, enVivo);

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
          <Datos reclamo={reclamo} enVivo={enVivo} />
          {reclamo.resolucion && (
            <TarjetaResolucion
              resolucion={reclamo.resolucion}
              registrada={reclamo.estado === 'resuelto' || reclamo.estado === 'cerrado'}
            />
          )}
          {reclamo.foto_url && <Foto ruta={reclamo.foto_url} />}
          <LineaDeTiempo eventos={reclamo.eventos} />
        </ScrollView>
      )}
    </>
  );
}

/** Mientras el reclamo se procesa: si los cambios llegan al instante o cada pocos segundos. */
function IndicadorEnVivo({ enVivo }: { enVivo: boolean }) {
  return (
    <View
      className="flex-row items-center gap-1.5"
      accessibilityLabel={enVivo ? 'Actualización en vivo' : 'Actualización periódica'}
    >
      <View className={`h-2 w-2 rounded-full ${enVivo ? 'bg-green-600' : 'bg-neutral-400'}`} />
      <Text className="text-xs text-neutral-500">{enVivo ? 'En vivo' : 'Actualizando…'}</Text>
    </View>
  );
}

function Datos({ reclamo, enVivo }: { reclamo: ReclamoDetalle; enVivo: boolean }) {
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
      <View className="flex-row items-center justify-between">
        <Insignia estado={ESTADOS_RECLAMO[reclamo.estado]} />
        {ESTADOS_EN_PROCESO.has(reclamo.estado) && <IndicadorEnVivo enVivo={enVivo} />}
      </View>
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

/** Primera letra en mayúscula: "un reembolso de S/ 8.90" → "Un reembolso de S/ 8.90". */
function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function TarjetaResolucion({
  resolucion,
  registrada,
}: {
  resolucion: Resolucion;
  registrada: boolean;
}) {
  const [verVideo, setVerVideo] = useState(false);
  return (
    <Tarjeta className="gap-3 border-emerald-200 bg-emerald-50">
      <View className="flex-row items-center gap-3">
        <Ionicons
          name={registrada ? 'checkmark-circle' : 'hourglass-outline'}
          size={26}
          color="#047857"
        />
        <Text className="flex-1 text-base font-bold text-emerald-900">
          {registrada ? 'Así resolvimos tu reclamo' : 'Te corresponde'}
        </Text>
      </View>
      <Text className="text-lg font-semibold text-neutral-900">
        {capitalizar(resolucion.descripcion)}
      </Text>
      {resolucion.numero_operacion ? (
        <Text className="text-neutral-700">
          Operación en caja: <Text className="font-semibold">{resolucion.numero_operacion}</Text>
        </Text>
      ) : (
        <Text className="text-neutral-700">Lo estamos registrando en nuestro sistema de caja…</Text>
      )}
      {resolucion.video_url &&
        (verVideo ? (
          <VideoResolucion ruta={resolucion.video_url} />
        ) : (
          <Boton
            titulo="Ver cómo lo resolvimos"
            icono="play-circle-outline"
            variante="secundario"
            onPress={() => setVerVideo(true)}
          />
        ))}
    </Tarjeta>
  );
}

function VideoResolucion({ ruta }: { ruta: string }) {
  // El video es privado: se pide con la misma sesión que el resto de la API.
  const encabezados = useEncabezadosAuth();
  return (
    <View className="gap-2">
      <Text className="text-sm text-neutral-600">
        Nuestro asistente automático (bot RPA) registró tu compensación en el sistema de caja, como
        lo haría un cajero. Así se vio:
      </Text>
      {encabezados && <Reproductor uri={urlApi(ruta)} encabezados={encabezados} />}
    </View>
  );
}

function Reproductor({ uri, encabezados }: { uri: string; encabezados: Record<string, string> }) {
  const player = useVideoPlayer({ uri, headers: encabezados }, (reproductor) => {
    reproductor.play();
  });
  return (
    <VideoView
      player={player}
      nativeControls
      contentFit="contain"
      fullscreenOptions={{ enable: true }}
      accessibilityLabel="Video del bot registrando la compensación"
      style={{ width: '100%', aspectRatio: 1280 / 800, borderRadius: 12, backgroundColor: '#000' }}
    />
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
