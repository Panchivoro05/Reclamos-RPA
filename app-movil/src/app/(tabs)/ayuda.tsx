import Ionicons from '@expo/vector-icons/Ionicons';
import { useHeaderHeight } from 'expo-router/react-navigation';
import { useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
  type ScrollViewInstance,
} from 'react-native';

import { ApiError } from '@/api/cliente';
import { useConsultarAsistente } from '@/api/consultas';
import type { MensajeChat } from '@/api/tipos';
import {
  BIENVENIDA,
  historialParaEnviar,
  MAXIMO_CARACTERES,
  prepararPregunta,
  SUGERENCIAS,
} from '@/lib/chat';
import { useChat } from '@/store/chat';

function Burbuja({ mensaje }: { mensaje: MensajeChat }) {
  const delCliente = mensaje.rol === 'cliente';
  return (
    <View
      className={`max-w-[85%] rounded-2xl px-4 py-3 ${
        delCliente ? 'self-end rounded-br-sm bg-marca-500' : 'self-start rounded-bl-sm bg-white'
      }`}
    >
      <Text className={`text-base ${delCliente ? 'text-white' : 'text-neutral-900'}`}>
        {mensaje.texto}
      </Text>
    </View>
  );
}

export default function Asistente() {
  const { mensajes, agregar } = useChat();
  const [texto, setTexto] = useState('');
  const [error, setError] = useState<string | null>(null);
  const consulta = useConsultarAsistente();
  const lista = useRef<ScrollViewInstance>(null);
  const alturaEncabezado = useHeaderHeight();

  function enviar(entrada: string) {
    const pregunta = prepararPregunta(entrada);
    if (!pregunta || consulta.isPending) return;
    const mensaje: MensajeChat = { rol: 'cliente', texto: pregunta };
    agregar(mensaje);
    setTexto('');
    setError(null);
    consulta.mutate(historialParaEnviar([...mensajes, mensaje]), {
      onSuccess: ({ respuesta }) => agregar({ rol: 'asistente', texto: respuesta }),
      // El error no entra a la conversación: el cliente puede volver a preguntar.
      onError: (e) =>
        setError(e instanceof ApiError ? e.message : 'No pudimos responder. Inténtalo otra vez.'),
    });
  }

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-neutral-50"
      // "padding" también en Android (va de borde a borde) y el alto real del encabezado.
      behavior="padding"
      keyboardVerticalOffset={alturaEncabezado}
    >
      <ScrollView
        ref={lista}
        contentContainerClassName="gap-3 p-4"
        onContentSizeChange={() => lista.current?.scrollToEnd({ animated: true })}
        keyboardShouldPersistTaps="handled"
      >
        <Burbuja mensaje={{ rol: 'asistente', texto: BIENVENIDA }} />
        {mensajes.length === 0 && (
          <View className="flex-row flex-wrap gap-2">
            {SUGERENCIAS.map((sugerencia) => (
              <Pressable
                key={sugerencia}
                accessibilityRole="button"
                onPress={() => enviar(sugerencia)}
                className="rounded-full border border-marca-200 bg-white px-3 py-2 active:bg-marca-50"
              >
                <Text className="text-sm text-marca-700">{sugerencia}</Text>
              </Pressable>
            ))}
          </View>
        )}
        {mensajes.map((mensaje, indice) => (
          <Burbuja key={indice} mensaje={mensaje} />
        ))}
        {consulta.isPending && (
          <View className="flex-row items-center gap-2 self-start rounded-2xl bg-white px-4 py-3">
            <ActivityIndicator size="small" color="#DC4316" />
            <Text className="text-neutral-500">Buscando tu información…</Text>
          </View>
        )}
        {error && (
          <View className="flex-row items-center gap-2 self-stretch rounded-xl bg-rose-50 p-3">
            <Ionicons name="alert-circle-outline" size={18} color="#BE123C" />
            <Text className="flex-1 text-sm text-rose-700">{error}</Text>
          </View>
        )}
      </ScrollView>
      <View className="flex-row items-end gap-2 border-t border-neutral-200 bg-white p-3">
        <TextInput
          value={texto}
          onChangeText={setTexto}
          placeholder="Escribe tu consulta…"
          placeholderTextColor="#A3A3A3"
          multiline
          maxLength={MAXIMO_CARACTERES}
          className="max-h-28 flex-1 rounded-2xl border border-neutral-200 px-4 py-3 text-base text-neutral-900"
          accessibilityLabel="Consulta para el asistente"
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Enviar"
          onPress={() => enviar(texto)}
          disabled={!prepararPregunta(texto) || consulta.isPending}
          className="h-12 w-12 items-center justify-center rounded-full bg-marca-500 active:bg-marca-600 disabled:opacity-50"
        >
          <Ionicons name="send" size={20} color="#FFFFFF" />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}
