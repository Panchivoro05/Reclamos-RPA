import { Stack } from 'expo-router';

// Al abrir un detalle desde otra pestaña, la lista queda debajo para poder volver.
export const unstable_settings = { initialRouteName: 'index' };

export default function Layout() {
  return (
    <Stack
      screenOptions={{
        headerTintColor: '#B7330F',
        headerTitleStyle: { color: '#171717' },
        contentStyle: { backgroundColor: '#FAFAFA' },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Mis pedidos' }} />
      <Stack.Screen name="[codigo]" options={{ title: 'Detalle' }} />
    </Stack>
  );
}
