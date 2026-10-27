/** Formatos visibles para el cliente (español de Perú). */

// Perú no usa horario de verano: America/Lima es siempre UTC-5. Calcularlo así evita
// depender del soporte de zonas horarias de Intl en cada dispositivo.
const DESFASE_LIMA_MS = -5 * 60 * 60 * 1000;

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

function dos(n: number): string {
  return n.toString().padStart(2, '0');
}

/** "82.5" → "S/ 82.50" */
export function formatoSoles(monto: string | number): string {
  return `S/ ${Number(monto).toFixed(2)}`;
}

/** ISO en UTC → "26 oct 2026, 18:04" (hora de Lima). */
export function formatoFechaHora(iso: string): string {
  const lima = new Date(new Date(iso).getTime() + DESFASE_LIMA_MS);
  const mes = MESES[lima.getUTCMonth()] ?? '';
  return `${lima.getUTCDate()} ${mes} ${lima.getUTCFullYear()}, ${dos(lima.getUTCHours())}:${dos(lima.getUTCMinutes())}`;
}
