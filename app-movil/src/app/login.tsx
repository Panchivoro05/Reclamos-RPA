import Ionicons from '@expo/vector-icons/Ionicons';
import { zodResolver } from '@hookform/resolvers/zod';
import { useState, type ReactNode } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { z } from 'zod';

import { api } from '@/api/cliente';
import type { Cliente } from '@/api/tipos';
import { Boton } from '@/components/Boton';
import { AvisoError, mensajeDeError } from '@/components/EstadosPantalla';
import { Tarjeta } from '@/components/Tarjeta';
import { CLIENTES_DEMO, config } from '@/config';
import { cerrarSesionFirebase, iniciarSesionFirebase } from '@/lib/firebase';
import { queryClient } from '@/lib/queryClient';
import { useSesion, type Sesion } from '@/store/sesion';

/** Activa la sesión y la confirma con GET /me; si el backend la rechaza, la deshace. */
async function confirmarSesion(sesion: Sesion): Promise<void> {
  const { iniciar, cerrar } = useSesion.getState();
  iniciar(sesion);
  try {
    const cliente = await api<Cliente>('/me');
    queryClient.setQueryData(['me'], cliente);
  } catch (error) {
    cerrar();
    throw error;
  }
}

export default function Login() {
  return (
    <SafeAreaView className="flex-1 bg-neutral-50">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        className="flex-1"
      >
        <ScrollView contentContainerClassName="flex-grow justify-center gap-8 p-6">
          <View className="items-center gap-3">
            <View className="rounded-3xl bg-marca-500 p-5">
              <Ionicons name="fast-food" size={48} color="#FFFFFF" />
            </View>
            <Text className="text-3xl font-bold text-neutral-900">BurgerYa</Text>
            <Text className="text-center text-neutral-500">
              ¿Algo salió mal con tu pedido? Cuéntanos y lo resolvemos.
            </Text>
          </View>

          {config.modoAuth === 'dev' ? <LoginDev /> : <LoginFirebase />}

          <Text className="text-center text-xs text-neutral-400">Servidor: {config.apiUrl}</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function LoginDev() {
  const [cargando, setCargando] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function entrar(email: string) {
    setCargando(email);
    setError(null);
    try {
      await confirmarSesion({ modo: 'dev', email });
    } catch (e) {
      setError(mensajeDeError(e));
    } finally {
      setCargando(null);
    }
  }

  return (
    <View className="gap-3">
      <Text className="font-semibold text-neutral-700">Modo desarrollo: elige un cliente demo</Text>
      {CLIENTES_DEMO.map((cliente) => (
        <Tarjeta key={cliente.email} onPress={() => void entrar(cliente.email)}>
          <View className="flex-row items-center gap-3">
            <View className="rounded-full bg-marca-100 p-3">
              <Ionicons name="person" size={22} color="#B7330F" />
            </View>
            <View className="flex-1">
              <Text className="text-base font-semibold text-neutral-900">{cliente.nombre}</Text>
              <Text className="text-neutral-500">{cliente.email}</Text>
            </View>
            <Ionicons
              name={cargando === cliente.email ? 'hourglass-outline' : 'chevron-forward'}
              size={20}
              color="#A3A3A3"
            />
          </View>
        </Tarjeta>
      ))}
      {error && <AvisoError mensaje={error} />}
    </View>
  );
}

const esquemaLogin = z.object({
  email: z.email('Ingresa un correo válido.'),
  contrasena: z.string().min(6, 'La contraseña tiene al menos 6 caracteres.'),
});
type ValoresLogin = z.infer<typeof esquemaLogin>;

function LoginFirebase() {
  const [error, setError] = useState<string | null>(null);
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ValoresLogin>({
    resolver: zodResolver(esquemaLogin),
    defaultValues: { email: '', contrasena: '' },
  });

  const entrar = handleSubmit(async ({ email, contrasena }) => {
    setError(null);
    try {
      const emailFirebase = await iniciarSesionFirebase(email.trim(), contrasena);
      await confirmarSesion({ modo: 'firebase', email: emailFirebase });
    } catch (e) {
      await cerrarSesionFirebase().catch(() => undefined);
      setError(
        e instanceof Error && e.name === 'FirebaseError'
          ? 'Correo o contraseña incorrectos.'
          : mensajeDeError(e),
      );
    }
  });

  return (
    <View className="gap-4">
      <Campo etiqueta="Correo" error={errors.email?.message}>
        <Controller
          control={control}
          name="email"
          render={({ field }) => (
            <TextInput
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              placeholder="tucorreo@ejemplo.com"
              className="rounded-xl border border-neutral-300 bg-white px-4 py-3 text-base"
            />
          )}
        />
      </Campo>
      <Campo etiqueta="Contraseña" error={errors.contrasena?.message}>
        <Controller
          control={control}
          name="contrasena"
          render={({ field }) => (
            <TextInput
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              secureTextEntry
              autoComplete="password"
              className="rounded-xl border border-neutral-300 bg-white px-4 py-3 text-base"
            />
          )}
        />
      </Campo>
      {error && <AvisoError mensaje={error} />}
      <Boton titulo="Ingresar" onPress={() => void entrar()} cargando={isSubmitting} />
    </View>
  );
}

function Campo({
  etiqueta,
  error,
  children,
}: {
  etiqueta: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <View className="gap-1">
      <Text className="font-medium text-neutral-700">{etiqueta}</Text>
      {children}
      {error && <Text className="text-sm text-rose-700">{error}</Text>}
    </View>
  );
}
