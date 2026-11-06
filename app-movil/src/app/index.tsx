import { Redirect } from 'expo-router';

// Ruta raíz ("/"): Expo Router vuelve aquí al cambiar la sesión. Sin ella, iniciar sesión
// terminaba en "Unmatched Route". Con sesión lleva a la lista de pedidos.
export default function Inicio() {
  return <Redirect href="/pedidos" />;
}
