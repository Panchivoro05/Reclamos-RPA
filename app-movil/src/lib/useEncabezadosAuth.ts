import { useEffect, useState } from 'react';

import { encabezadosAuth } from '@/api/cliente';

/** Encabezados de sesión para recursos que se cargan fuera de fetch (por ejemplo, imágenes). */
export function useEncabezadosAuth(): Record<string, string> | null {
  const [encabezados, setEncabezados] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    let activo = true;
    void encabezadosAuth().then((valor) => {
      if (activo) setEncabezados(valor);
    });
    return () => {
      activo = false;
    };
  }, []);
  return encabezados;
}
