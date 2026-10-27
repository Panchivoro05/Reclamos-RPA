import '../../global.css';

import { QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { Cargando } from '@/components/EstadosPantalla';
import { queryClient } from '@/lib/queryClient';
import { useSesion, useSesionHidratada } from '@/store/sesion';

export default function RootLayout() {
  const hidratada = useSesionHidratada();
  const conSesion = useSesion((estado) => estado.sesion !== null);

  // Hasta leer la sesión guardada no se sabe si mostrar el login o la app.
  if (!hidratada) return <Cargando />;

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerTintColor: '#B7330F',
          headerTitleStyle: { color: '#171717' },
          contentStyle: { backgroundColor: '#FAFAFA' },
        }}
      >
        {/* Las rutas protegidas solo existen con sesión; al cerrarla se vuelve al login. */}
        <Stack.Protected guard={conSesion}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen
            name="nuevo-reclamo"
            options={{ presentation: 'modal', title: 'Nuevo reclamo' }}
          />
        </Stack.Protected>
        <Stack.Protected guard={!conSesion}>
          <Stack.Screen name="login" options={{ headerShown: false }} />
        </Stack.Protected>
      </Stack>
    </QueryClientProvider>
  );
}
