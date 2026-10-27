import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import type { ColorValue } from 'react-native';

import type { NombreIcono } from '@/lib/catalogos';

function icono(nombre: NombreIcono) {
  // Los colores de las pestañas se definen abajo como texto (#RRGGBB).
  function IconoPestana({ color, size }: { color: ColorValue; size: number }) {
    return (
      <Ionicons name={nombre} size={size} color={typeof color === 'string' ? color : undefined} />
    );
  }
  return IconoPestana;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#DC4316',
        tabBarInactiveTintColor: '#737373',
        headerTitleStyle: { color: '#171717' },
      }}
    >
      <Tabs.Screen
        name="pedidos"
        options={{ title: 'Pedidos', headerShown: false, tabBarIcon: icono('receipt-outline') }}
      />
      <Tabs.Screen
        name="reclamos"
        options={{
          title: 'Reclamos',
          headerShown: false,
          tabBarIcon: icono('chatbubbles-outline'),
        }}
      />
      <Tabs.Screen
        name="perfil"
        options={{ title: 'Perfil', tabBarIcon: icono('person-outline') }}
      />
    </Tabs>
  );
}
