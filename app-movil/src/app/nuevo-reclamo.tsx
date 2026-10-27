import Ionicons from '@expo/vector-icons/Ionicons';
import { zodResolver } from '@hookform/resolvers/zod';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Controller, useForm, useWatch, type UseFormSetError } from 'react-hook-form';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { z } from 'zod';

import { ApiError } from '@/api/cliente';
import { useCrearReclamo, usePedido } from '@/api/consultas';
import type { PedidoDetalle, TipoReclamo } from '@/api/tipos';
import { Boton } from '@/components/Boton';
import { AvisoError, Cargando, ErrorPantalla, mensajeDeError } from '@/components/EstadosPantalla';
import { aNuevoReclamo, esquemaReclamo, type ValoresReclamo } from '@/features/reclamos/esquema';
import { TIPOS_RECLAMO_INFO } from '@/lib/catalogos';

type SalidaReclamo = z.output<typeof esquemaReclamo>;

export default function NuevoReclamo() {
  const { pedido: codigo } = useLocalSearchParams<{ pedido: string }>();
  const { data: pedido, isPending, error, refetch } = usePedido(codigo);

  if (isPending) return <Cargando />;
  if (error) return <ErrorPantalla error={error} reintentar={() => void refetch()} />;
  return <Formulario pedido={pedido} />;
}

/** Campo del formulario al que corresponde cada error de negocio del backend. */
const CAMPO_POR_CODIGO: Record<string, 'foto' | 'items' | 'descripcion'> = {
  foto_requerida: 'foto',
  foto_formato_invalido: 'foto',
  foto_muy_grande: 'foto',
  items_requeridos: 'items',
  items_invalidos: 'items',
  item_no_pertenece: 'items',
  item_repetido: 'items',
  cantidad_excedida: 'items',
};

function mostrarErrorDelServidor(
  error: unknown,
  setError: UseFormSetError<ValoresReclamo>,
): string | null {
  if (!(error instanceof ApiError)) return mensajeDeError(error);
  const campo = CAMPO_POR_CODIGO[error.codigo];
  if (campo) {
    setError(campo, { message: error.message });
    return null;
  }
  if (error.errores.length > 0) {
    for (const { campo: nombre, mensaje } of error.errores) {
      if (nombre === 'descripcion' || nombre === 'tipo' || nombre === 'foto') {
        setError(nombre, { message: mensaje });
      }
    }
  }
  return error.message;
}

function Formulario({ pedido }: { pedido: PedidoDetalle }) {
  const crear = useCrearReclamo();
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null);
  const disponibles = pedido.tipos_reclamo_disponibles;

  const {
    control,
    handleSubmit,
    setValue,
    setError,
    formState: { errors },
  } = useForm<ValoresReclamo, unknown, SalidaReclamo>({
    resolver: zodResolver(esquemaReclamo),
    defaultValues: {
      tipo: disponibles.length === 1 ? disponibles[0] : undefined,
      descripcion: '',
      items: pedido.items.map((item) => ({
        pedido_item_id: item.id,
        cantidad_afectada: 0,
        maximo: item.cantidad,
      })),
      foto: null,
    },
  });

  const tipo = useWatch({ control, name: 'tipo' });
  const foto = useWatch({ control, name: 'foto' });
  const fotoObligatoria = tipo ? TIPOS_RECLAMO_INFO[tipo].fotoObligatoria : false;

  const enviar = handleSubmit((valores) => {
    setErrorGeneral(null);
    crear.mutate(aNuevoReclamo(pedido.codigo, valores), {
      onSuccess: (reclamo) => {
        router.dismiss();
        router.navigate(`/reclamos/${reclamo.codigo}`);
      },
      onError: (error) => setErrorGeneral(mostrarErrorDelServidor(error, setError)),
    });
  });

  async function elegirFoto(origen: 'camara' | 'galeria') {
    if (origen === 'camara') {
      const permiso = await ImagePicker.requestCameraPermissionsAsync();
      if (!permiso.granted) {
        Alert.alert(
          'Necesitamos tu cámara',
          'Activa el permiso de cámara en los ajustes del celular para tomar la foto.',
        );
        return;
      }
    }
    const opciones: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.6 };
    const resultado =
      origen === 'camara'
        ? await ImagePicker.launchCameraAsync(opciones)
        : await ImagePicker.launchImageLibraryAsync(opciones);
    const imagen = resultado.canceled ? undefined : resultado.assets[0];
    if (!imagen) return;

    const tipoMime = imagen.mimeType ?? 'image/jpeg';
    setValue(
      'foto',
      {
        uri: imagen.uri,
        nombre: imagen.fileName ?? `foto.${tipoMime.split('/')[1] ?? 'jpg'}`,
        tipoMime,
        tamano: imagen.fileSize ?? null,
      },
      { shouldValidate: true },
    );
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      className="flex-1 bg-neutral-50"
      keyboardVerticalOffset={80}
    >
      <ScrollView contentContainerClassName="gap-6 p-4 pb-10" keyboardShouldPersistTaps="handled">
        <Text className="text-neutral-500">Pedido {pedido.codigo}</Text>

        <Seccion titulo="¿Qué pasó con tu pedido?" error={errors.tipo?.message}>
          <Controller
            control={control}
            name="tipo"
            render={({ field }) => (
              <View className="gap-2">
                {disponibles.map((opcion) => (
                  <OpcionTipo
                    key={opcion}
                    tipo={opcion}
                    seleccionado={field.value === opcion}
                    onPress={() => field.onChange(opcion)}
                  />
                ))}
              </View>
            )}
          />
        </Seccion>

        {tipo && tipo !== 'demora' && (
          <Seccion
            titulo="¿Qué productos tuvieron el problema?"
            error={errors.items?.message ?? errors.items?.root?.message}
          >
            <View className="gap-2">
              {pedido.items.map((item, indice) => (
                <Controller
                  key={item.id}
                  control={control}
                  name={`items.${indice}.cantidad_afectada`}
                  render={({ field }) => (
                    <SelectorCantidad
                      producto={item.producto}
                      maximo={item.cantidad}
                      valor={field.value}
                      onChange={field.onChange}
                    />
                  )}
                />
              ))}
            </View>
          </Seccion>
        )}

        <Seccion titulo="Cuéntanos qué pasó" error={errors.descripcion?.message}>
          <Controller
            control={control}
            name="descripcion"
            render={({ field }) => (
              <TextInput
                value={field.value}
                onChangeText={field.onChange}
                onBlur={field.onBlur}
                multiline
                maxLength={1000}
                placeholder="Por ejemplo: pedí una Doble Queso y me llegó una Clásica."
                textAlignVertical="top"
                className="min-h-28 rounded-xl border border-neutral-300 bg-white p-3 text-base"
              />
            )}
          />
        </Seccion>

        <Seccion
          titulo={fotoObligatoria ? 'Foto del producto (obligatoria)' : 'Foto (opcional)'}
          error={errors.foto?.message}
        >
          {foto ? (
            <View>
              <Image
                source={{ uri: foto.uri }}
                contentFit="cover"
                accessibilityLabel="Foto seleccionada"
                style={{ width: '100%', aspectRatio: 4 / 3, borderRadius: 12 }}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Quitar foto"
                onPress={() => setValue('foto', null, { shouldValidate: true })}
                className="absolute right-2 top-2 rounded-full bg-black/60 p-2"
              >
                <Ionicons name="close" size={20} color="#FFFFFF" />
              </Pressable>
            </View>
          ) : (
            <View className="flex-row gap-3">
              <View className="flex-1">
                <Boton
                  titulo="Cámara"
                  icono="camera-outline"
                  variante="secundario"
                  onPress={() => void elegirFoto('camara')}
                />
              </View>
              <View className="flex-1">
                <Boton
                  titulo="Galería"
                  icono="images-outline"
                  variante="secundario"
                  onPress={() => void elegirFoto('galeria')}
                />
              </View>
            </View>
          )}
        </Seccion>

        {errorGeneral && <AvisoError mensaje={errorGeneral} />}
        <Boton
          titulo="Enviar reclamo"
          icono="send"
          onPress={() => void enviar()}
          cargando={crear.isPending}
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Seccion({
  titulo,
  error,
  children,
}: {
  titulo: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <View className="gap-3">
      <Text className="text-base font-semibold text-neutral-900">{titulo}</Text>
      {children}
      {error && <Text className="text-sm text-rose-700">{error}</Text>}
    </View>
  );
}

function OpcionTipo({
  tipo,
  seleccionado,
  onPress,
}: {
  tipo: TipoReclamo;
  seleccionado: boolean;
  onPress: () => void;
}) {
  const info = TIPOS_RECLAMO_INFO[tipo];
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected: seleccionado }}
      onPress={onPress}
      className={`flex-row items-center gap-3 rounded-2xl border-2 p-4 ${
        seleccionado ? 'border-marca-500 bg-marca-50' : 'border-neutral-200 bg-white'
      }`}
    >
      <View className={`rounded-full p-2 ${seleccionado ? 'bg-marca-500' : 'bg-neutral-100'}`}>
        <Ionicons name={info.icono} size={22} color={seleccionado ? '#FFFFFF' : '#525252'} />
      </View>
      <View className="flex-1">
        <Text className="text-base font-semibold text-neutral-900">{info.etiqueta}</Text>
        <Text className="text-neutral-500">{info.descripcion}</Text>
      </View>
      {seleccionado && <Ionicons name="checkmark-circle" size={22} color="#F05A28" />}
    </Pressable>
  );
}

function SelectorCantidad({
  producto,
  maximo,
  valor,
  onChange,
}: {
  producto: string;
  maximo: number;
  valor: number;
  onChange: (valor: number) => void;
}) {
  const activo = valor > 0;
  return (
    <View
      className={`flex-row items-center gap-3 rounded-2xl border p-3 ${
        activo ? 'border-marca-500 bg-marca-50' : 'border-neutral-200 bg-white'
      }`}
    >
      <View className="flex-1">
        <Text className="font-medium text-neutral-900">{producto}</Text>
        <Text className="text-xs text-neutral-500">Pediste {maximo}</Text>
      </View>
      <BotonCantidad
        icono="remove"
        etiqueta={`Quitar una unidad de ${producto}`}
        deshabilitado={valor <= 0}
        onPress={() => onChange(valor - 1)}
      />
      <Text className="w-6 text-center text-base font-bold text-neutral-900">{valor}</Text>
      <BotonCantidad
        icono="add"
        etiqueta={`Agregar una unidad de ${producto}`}
        deshabilitado={valor >= maximo}
        onPress={() => onChange(valor + 1)}
      />
    </View>
  );
}

function BotonCantidad({
  icono,
  etiqueta,
  deshabilitado,
  onPress,
}: {
  icono: 'add' | 'remove';
  etiqueta: string;
  deshabilitado: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={etiqueta}
      disabled={deshabilitado}
      onPress={onPress}
      className={`h-9 w-9 items-center justify-center rounded-full ${
        deshabilitado ? 'bg-neutral-100' : 'bg-marca-500 active:bg-marca-600'
      }`}
    >
      <Ionicons name={icono} size={20} color={deshabilitado ? '#A3A3A3' : '#FFFFFF'} />
    </Pressable>
  );
}
