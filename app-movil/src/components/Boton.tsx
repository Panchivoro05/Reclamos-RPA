import Ionicons from '@expo/vector-icons/Ionicons';
import { ActivityIndicator, Pressable, Text } from 'react-native';

import type { NombreIcono } from '@/lib/catalogos';

interface Props {
  titulo: string;
  onPress: () => void;
  variante?: 'primario' | 'secundario' | 'peligro';
  icono?: NombreIcono;
  cargando?: boolean;
  deshabilitado?: boolean;
}

const ESTILOS = {
  primario: { caja: 'bg-marca-500 active:bg-marca-600', texto: 'text-white', icono: '#FFFFFF' },
  secundario: {
    caja: 'border border-marca-200 bg-white active:bg-marca-50',
    texto: 'text-marca-700',
    icono: '#B7330F',
  },
  peligro: {
    caja: 'border border-rose-200 bg-white active:bg-rose-50',
    texto: 'text-rose-700',
    icono: '#BE123C',
  },
} as const;

export function Boton({
  titulo,
  onPress,
  variante = 'primario',
  icono,
  cargando = false,
  deshabilitado = false,
}: Props) {
  const estilo = ESTILOS[variante];
  const inactivo = deshabilitado || cargando;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactivo, busy: cargando }}
      onPress={onPress}
      disabled={inactivo}
      className={`flex-row items-center justify-center gap-2 rounded-2xl px-5 py-4 ${estilo.caja} ${inactivo ? 'opacity-60' : ''}`}
    >
      {cargando ? (
        <ActivityIndicator color={estilo.icono} />
      ) : (
        icono && <Ionicons name={icono} size={20} color={estilo.icono} />
      )}
      <Text className={`text-base font-semibold ${estilo.texto}`}>{titulo}</Text>
    </Pressable>
  );
}
