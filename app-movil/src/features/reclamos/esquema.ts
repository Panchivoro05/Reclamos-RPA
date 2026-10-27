/**
 * Validación del formulario "Nuevo reclamo" (React Hook Form + Zod).
 * Repite en el celular las reglas del backend para avisar antes de enviar;
 * el backend igual las vuelve a validar.
 */
import { z } from 'zod';

import type { NuevoReclamo } from '@/api/consultas';
import { TIPOS_RECLAMO } from '@/api/tipos';
import { FOTO_MAX_BYTES } from '@/config';
import { TIPOS_RECLAMO_INFO } from '@/lib/catalogos';

export const esquemaReclamo = z
  .object({
    tipo: z.enum(TIPOS_RECLAMO, { error: 'Elige qué problema tuvo tu pedido.' }),
    descripcion: z
      .string()
      .trim()
      .min(10, 'Cuéntanos un poco más (al menos 10 caracteres).')
      .max(1000, 'La descripción puede tener hasta 1000 caracteres.'),
    // Un elemento por cada producto del pedido; cantidad 0 = no afectado.
    items: z.array(
      z.object({
        pedido_item_id: z.number().int(),
        cantidad_afectada: z.number().int().min(0),
        maximo: z.number().int(),
      }),
    ),
    foto: z
      .object({
        uri: z.string(),
        nombre: z.string(),
        tipoMime: z.string(),
        tamano: z.number().nullable(),
      })
      .nullable(),
  })
  .superRefine((valores, ctx) => {
    const seleccionados = valores.items.filter((item) => item.cantidad_afectada > 0);
    if (valores.tipo !== 'demora' && seleccionados.length === 0) {
      ctx.addIssue({
        code: 'custom',
        path: ['items'],
        message: 'Marca al menos un producto que tuvo el problema.',
      });
    }
    if (valores.items.some((item) => item.cantidad_afectada > item.maximo)) {
      ctx.addIssue({
        code: 'custom',
        path: ['items'],
        message: 'No puedes reclamar más unidades de las que pediste.',
      });
    }
    if (TIPOS_RECLAMO_INFO[valores.tipo].fotoObligatoria && !valores.foto) {
      ctx.addIssue({
        code: 'custom',
        path: ['foto'],
        message: 'Para este problema necesitamos una foto del producto.',
      });
    }
    if (valores.foto?.tamano && valores.foto.tamano > FOTO_MAX_BYTES) {
      ctx.addIssue({
        code: 'custom',
        path: ['foto'],
        message: 'La foto pesa más de 5 MB. Elige otra o tómala de nuevo.',
      });
    }
  });

export type ValoresReclamo = z.input<typeof esquemaReclamo>;

/** Convierte los valores del formulario en lo que se envía a la API. */
export function aNuevoReclamo(pedidoCodigo: string, valores: ValoresReclamo): NuevoReclamo {
  return {
    pedido_codigo: pedidoCodigo,
    tipo: valores.tipo,
    descripcion: valores.descripcion.trim(),
    // En una demora no se reclaman productos puntuales.
    items: (valores.tipo === 'demora' ? [] : valores.items)
      .filter((item) => item.cantidad_afectada > 0)
      .map(({ pedido_item_id, cantidad_afectada }) => ({ pedido_item_id, cantidad_afectada })),
    foto: valores.foto
      ? { uri: valores.foto.uri, nombre: valores.foto.nombre, tipoMime: valores.foto.tipoMime }
      : null,
  };
}
