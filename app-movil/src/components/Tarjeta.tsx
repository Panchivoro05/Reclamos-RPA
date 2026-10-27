import type { ReactNode } from 'react';
import { Pressable, View } from 'react-native';

interface Props {
  children: ReactNode;
  onPress?: () => void;
  className?: string;
}

export function Tarjeta({ children, onPress, className = '' }: Props) {
  const clases = `rounded-2xl border border-neutral-200 bg-white p-4 ${className}`;
  if (!onPress) return <View className={clases}>{children}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      className={`${clases} active:bg-neutral-50`}
    >
      {children}
    </Pressable>
  );
}
