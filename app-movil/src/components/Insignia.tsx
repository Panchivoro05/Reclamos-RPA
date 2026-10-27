import { Text, View } from 'react-native';

import type { EstiloEstado } from '@/lib/catalogos';

export function Insignia({ estado }: { estado: EstiloEstado }) {
  return (
    <View className={`self-start rounded-full px-3 py-1 ${estado.fondo}`}>
      <Text className={`text-xs font-semibold ${estado.texto}`}>{estado.etiqueta}</Text>
    </View>
  );
}
