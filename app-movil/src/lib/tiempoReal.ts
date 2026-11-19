/**
 * Conexión WebSocket con la API para recibir en vivo los cambios de estado de los reclamos.
 *
 * Protocolo (ver backend/app/api/tiempo_real.py):
 *   app → {"tipo": "autenticar", "encabezados": {...}}   (los mismos encabezados de la API)
 *   api → {"tipo": "conectado"}                           (la app recarga sus datos)
 *   api → {"tipo": "reclamo_actualizado", "codigo", "estado", ...}
 *   app → {"tipo": "ping"}  /  api → {"tipo": "pong"}     (comprueba que la conexión vive)
 *
 * Si la conexión se corta, vuelve a intentar con espera creciente (1 s, 2 s, 4 s… hasta 30 s).
 * No depende de React: el hook useEventosEnVivo la conecta con TanStack Query.
 */

import type { EstadoReclamo } from '@/api/tipos';

export type EstadoConexion = 'conectando' | 'en_vivo' | 'desconectado';

export interface ReclamoActualizado {
  tipo: 'reclamo_actualizado';
  codigo: string;
  estado: EstadoReclamo;
  evento_id: number;
  momento: string;
}

/** Lo mínimo de un WebSocket que se usa (el de React Native, o uno falso en las pruebas). */
export interface SocketMinimo {
  onopen: (() => void) | null;
  onmessage: ((evento: { data: unknown }) => void) | null;
  onclose: ((evento: { code: number }) => void) | null;
  onerror: (() => void) | null;
  send(datos: string): void;
  close(): void;
}

export interface OpcionesConexion {
  url: string;
  obtenerEncabezados: () => Promise<Record<string, string>>;
  alConectar: () => void;
  alActualizar: (evento: ReclamoActualizado) => void;
  alCambiarEstado: (estado: EstadoConexion) => void;
  crearSocket?: (url: string) => SocketMinimo;
}

export const ESPERA_INICIAL_MS = 1_000;
export const ESPERA_MAXIMA_MS = 30_000;
export const INTERVALO_PING_MS = 25_000;
export const ESPERA_PONG_MS = 10_000;

/** URL del WebSocket a partir de la URL de la API: http → ws, https → wss. */
export function urlWebSocket(apiUrl: string): string {
  return `${apiUrl.replace(/^http/, 'ws')}/api/v1/ws`;
}

export function esperaReconexion(intentos: number): number {
  return Math.min(ESPERA_INICIAL_MS * 2 ** intentos, ESPERA_MAXIMA_MS);
}

function leerMensaje(datos: unknown): { tipo?: unknown } | null {
  if (typeof datos !== 'string') return null;
  try {
    const valor: unknown = JSON.parse(datos);
    return typeof valor === 'object' && valor !== null ? (valor as { tipo?: unknown }) : null;
  } catch {
    return null;
  }
}

export class ConexionEventos {
  private socket: SocketMinimo | null = null;
  private activa = false;
  private intentos = 0;
  private reconexion: ReturnType<typeof setTimeout> | null = null;
  private ping: ReturnType<typeof setInterval> | null = null;
  private esperaPong: ReturnType<typeof setTimeout> | null = null;
  private readonly crearSocket: (url: string) => SocketMinimo;

  constructor(private readonly opciones: OpcionesConexion) {
    this.crearSocket = opciones.crearSocket ?? ((url) => new WebSocket(url) as SocketMinimo);
  }

  iniciar(): void {
    if (this.activa) return;
    this.activa = true;
    this.intentos = 0;
    this.conectar();
  }

  detener(): void {
    this.activa = false;
    this.limpiarTemporizadores();
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.opciones.alCambiarEstado('desconectado');
  }

  private conectar(): void {
    this.opciones.alCambiarEstado('conectando');
    const socket = this.crearSocket(this.opciones.url);
    this.socket = socket;

    socket.onopen = () => {
      void this.opciones.obtenerEncabezados().then((encabezados) => {
        if (this.socket === socket) {
          socket.send(JSON.stringify({ tipo: 'autenticar', encabezados }));
        }
      });
    };
    socket.onmessage = ({ data }) => {
      if (this.socket === socket) this.recibir(data);
    };
    socket.onclose = () => {
      if (this.socket === socket) this.alCerrarse();
    };
    // Después de un error siempre llega onclose: ahí se decide la reconexión.
    socket.onerror = () => undefined;
  }

  private recibir(datos: unknown): void {
    const mensaje = leerMensaje(datos);
    switch (mensaje?.tipo) {
      case 'conectado':
        this.intentos = 0;
        this.opciones.alCambiarEstado('en_vivo');
        this.opciones.alConectar();
        this.programarPing();
        break;
      case 'reclamo_actualizado':
        this.opciones.alActualizar(mensaje as ReclamoActualizado);
        break;
      case 'pong':
        if (this.esperaPong) clearTimeout(this.esperaPong);
        this.esperaPong = null;
        break;
    }
  }

  private programarPing(): void {
    if (this.ping) clearInterval(this.ping);
    this.ping = setInterval(() => {
      this.socket?.send(JSON.stringify({ tipo: 'ping' }));
      if (this.esperaPong) return;
      // Sin respuesta: la conexión murió sin avisar (por ejemplo, cambio de red). Se rehace.
      this.esperaPong = setTimeout(() => this.reconectarAhora(), ESPERA_PONG_MS);
    }, INTERVALO_PING_MS);
  }

  private reconectarAhora(): void {
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.alCerrarse();
  }

  private alCerrarse(): void {
    this.limpiarTemporizadores();
    this.socket = null;
    if (!this.activa) return;
    this.opciones.alCambiarEstado('desconectado');
    const espera = esperaReconexion(this.intentos);
    this.intentos += 1;
    this.reconexion = setTimeout(() => {
      this.reconexion = null;
      if (this.activa) this.conectar();
    }, espera);
  }

  private limpiarTemporizadores(): void {
    if (this.reconexion) clearTimeout(this.reconexion);
    if (this.ping) clearInterval(this.ping);
    if (this.esperaPong) clearTimeout(this.esperaPong);
    this.reconexion = this.ping = this.esperaPong = null;
  }
}
