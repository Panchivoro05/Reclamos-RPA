import { aNuevoReclamo, esquemaReclamo, type ValoresReclamo } from './esquema';

const base: ValoresReclamo = {
  tipo: 'pedido_incompleto',
  descripcion: 'Faltaron las papas fritas del combo.',
  items: [
    { pedido_item_id: 1, cantidad_afectada: 1, maximo: 2 },
    { pedido_item_id: 2, cantidad_afectada: 0, maximo: 1 },
  ],
  foto: null,
};

const foto = { uri: 'file:///foto.jpg', nombre: 'foto.jpg', tipoMime: 'image/jpeg', tamano: 1000 };

function mensajes(valores: ValoresReclamo): Record<string, string> {
  const resultado = esquemaReclamo.safeParse(valores);
  if (resultado.success) return {};
  return Object.fromEntries(resultado.error.issues.map((i) => [i.path.join('.'), i.message]));
}

describe('esquemaReclamo', () => {
  it('acepta un reclamo válido', () => {
    expect(esquemaReclamo.safeParse(base).success).toBe(true);
  });

  it('exige una descripción de al menos 10 caracteres (sin contar espacios)', () => {
    expect(mensajes({ ...base, descripcion: '   corta   ' })).toHaveProperty('descripcion');
  });

  it('exige al menos un producto afectado, salvo en demoras', () => {
    const sinItems = base.items.map((i) => ({ ...i, cantidad_afectada: 0 }));
    expect(mensajes({ ...base, items: sinItems })).toHaveProperty('items');
    expect(mensajes({ ...base, tipo: 'demora', items: sinItems })).toEqual({});
  });

  it('no permite reclamar más unidades de las pedidas', () => {
    const excedido = [{ pedido_item_id: 1, cantidad_afectada: 3, maximo: 2 }];
    expect(mensajes({ ...base, items: excedido }).items).toMatch(/más unidades/);
  });

  it.each(['producto_equivocado', 'mal_estado'] as const)('exige foto en %s', (tipo) => {
    expect(mensajes({ ...base, tipo })).toHaveProperty('foto');
    expect(mensajes({ ...base, tipo, foto })).toEqual({});
  });

  it('rechaza fotos de más de 5 MB', () => {
    const grande = { ...foto, tamano: 6 * 1024 * 1024 };
    expect(mensajes({ ...base, tipo: 'mal_estado', foto: grande }).foto).toMatch(/5 MB/);
  });
});

describe('aNuevoReclamo', () => {
  it('envía solo los productos marcados y sin el máximo', () => {
    expect(aNuevoReclamo('BY-000101', { ...base, descripcion: '  Faltaron las papas.  ' })).toEqual(
      {
        pedido_codigo: 'BY-000101',
        tipo: 'pedido_incompleto',
        descripcion: 'Faltaron las papas.',
        items: [{ pedido_item_id: 1, cantidad_afectada: 1 }],
        foto: null,
      },
    );
  });

  it('no envía productos en una demora', () => {
    expect(aNuevoReclamo('BY-000102', { ...base, tipo: 'demora' }).items).toEqual([]);
  });
});
