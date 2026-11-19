import {
  ConexionEventos,
  ESPERA_PONG_MS,
  type EstadoConexion,
  esperaReconexion,
  INTERVALO_PING_MS,
  type ReclamoActualizado,
  type SocketMinimo,
  urlWebSocket,
} from './tiempoReal';

class SocketFalso implements SocketMinimo {
  onopen: (() => void) | null = null;
  onmessage: ((evento: { data: unknown }) => void) | null = null;
  onclose: ((evento: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  enviados: unknown[] = [];
  cerrado = false;

  send(datos: string): void {
    this.enviados.push(JSON.parse(datos));
  }
  close(): void {
    this.cerrado = true;
  }
  // Lo que haría el servidor:
  abrir(): void {
    this.onopen?.();
  }
  responder(mensaje: object): void {
    this.onmessage?.({ data: JSON.stringify(mensaje) });
  }
  cortar(code = 1006): void {
    this.onclose?.({ code });
  }
}

const EVENTO: ReclamoActualizado = {
  tipo: 'reclamo_actualizado',
  codigo: 'RC-2026-000001',
  estado: 'resuelto',
  evento_id: 5,
  momento: '2026-11-19T04:00:00+00:00',
};

function preparar() {
  const sockets: SocketFalso[] = [];
  const estados: EstadoConexion[] = [];
  const eventos: ReclamoActualizado[] = [];
  const alConectar = jest.fn();
  const conexion = new ConexionEventos({
    url: 'ws://api/api/v1/ws',
    obtenerEncabezados: () => Promise.resolve({ 'X-Dev-User': 'cliente1@burgerya.pe' }),
    alConectar,
    alActualizar: (evento) => eventos.push(evento),
    alCambiarEstado: (estado) => estados.push(estado),
    crearSocket: () => {
      const socket = new SocketFalso();
      sockets.push(socket);
      return socket;
    },
  });
  const ultimo = (): SocketFalso => {
    const socket = sockets.at(-1);
    if (!socket) throw new Error('Todavía no se creó ningún socket');
    return socket;
  };
  return { conexion, sockets, ultimo, estados, eventos, alConectar };
}

/** Abre el socket, deja que se envíe la autenticación y responde "conectado". */
async function conectar(socket: SocketFalso): Promise<void> {
  socket.abrir();
  await Promise.resolve();
  socket.responder({ tipo: 'conectado' });
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test('url del WebSocket a partir de la API', () => {
  expect(urlWebSocket('http://192.168.1.20:8000')).toBe('ws://192.168.1.20:8000/api/v1/ws');
  expect(urlWebSocket('https://api.burgerya.pe')).toBe('wss://api.burgerya.pe/api/v1/ws');
});

test('se autentica con los encabezados de la sesión y recarga al conectarse', async () => {
  const { conexion, ultimo, estados, alConectar } = preparar();
  conexion.iniciar();
  await conectar(ultimo());

  expect(ultimo().enviados[0]).toEqual({
    tipo: 'autenticar',
    encabezados: { 'X-Dev-User': 'cliente1@burgerya.pe' },
  });
  expect(estados).toEqual(['conectando', 'en_vivo']);
  expect(alConectar).toHaveBeenCalledTimes(1);
});

test('entrega los cambios de estado e ignora mensajes desconocidos', async () => {
  const { conexion, ultimo, eventos } = preparar();
  conexion.iniciar();
  await conectar(ultimo());

  ultimo().responder(EVENTO);
  ultimo().onmessage?.({ data: 'no es json' });
  ultimo().responder({ tipo: 'otra_cosa' });

  expect(eventos).toEqual([EVENTO]);
});

test('si se corta, reconecta con espera creciente', async () => {
  const { conexion, sockets, ultimo, estados } = preparar();
  conexion.iniciar();
  ultimo().cortar();
  expect(estados.at(-1)).toBe('desconectado');

  jest.advanceTimersByTime(esperaReconexion(0) - 1);
  expect(sockets).toHaveLength(1);
  jest.advanceTimersByTime(1);
  expect(sockets).toHaveLength(2);

  ultimo().cortar();
  jest.advanceTimersByTime(esperaReconexion(1));
  expect(sockets).toHaveLength(3);

  // Al conectarse bien, la espera vuelve a empezar desde 1 s.
  await conectar(ultimo());
  ultimo().cortar();
  jest.advanceTimersByTime(esperaReconexion(0));
  expect(sockets).toHaveLength(4);
});

test('la espera crece hasta un máximo de 30 s', () => {
  expect([0, 1, 2, 3, 4, 5, 10].map(esperaReconexion)).toEqual([
    1000, 2000, 4000, 8000, 16000, 30000, 30000,
  ]);
});

test('sin pong, da la conexión por muerta y reconecta', async () => {
  const { conexion, sockets, ultimo } = preparar();
  conexion.iniciar();
  await conectar(ultimo());
  const primero = ultimo();

  jest.advanceTimersByTime(INTERVALO_PING_MS);
  expect(primero.enviados.at(-1)).toEqual({ tipo: 'ping' });
  primero.responder({ tipo: 'pong' });
  jest.advanceTimersByTime(ESPERA_PONG_MS);
  expect(primero.cerrado).toBe(false);

  jest.advanceTimersByTime(INTERVALO_PING_MS - ESPERA_PONG_MS); // segundo ping, sin respuesta
  expect(primero.cerrado).toBe(false);
  jest.advanceTimersByTime(ESPERA_PONG_MS);
  expect(primero.cerrado).toBe(true);
  jest.advanceTimersByTime(esperaReconexion(0));
  expect(sockets).toHaveLength(2);
});

test('al detenerla cierra el socket y no reconecta', async () => {
  const { conexion, sockets, ultimo, estados } = preparar();
  conexion.iniciar();
  await conectar(ultimo());

  conexion.detener();
  ultimo().cortar();
  jest.advanceTimersByTime(60_000);

  expect(ultimo().cerrado).toBe(true);
  expect(sockets).toHaveLength(1);
  expect(estados.at(-1)).toBe('desconectado');
});

test('no envía la autenticación si se detuvo antes de abrir', async () => {
  const { conexion, ultimo } = preparar();
  conexion.iniciar();
  const socket = ultimo();
  conexion.detener();
  socket.abrir();
  await Promise.resolve();
  expect(socket.enviados).toEqual([]);
});
