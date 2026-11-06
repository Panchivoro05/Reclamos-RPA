// Cursor y banner visibles del bot RPA.
//
// Playwright mueve un mouse "virtual" que no se dibuja en pantalla. Este script dibuja una
// flecha que sigue los eventos reales de ese mouse (mousemove/mousedown), resalta el elemento
// sobre el que está y muestra un banner con el paso actual. Así quien mire la pantalla (o el
// video) ve al bot operar SISCAJA como lo haría una persona.
//
// No modifica SISCAJA: se inyecta desde afuera en cada página. Es idempotente.
() => {
  if (window.__botCursor) return;

  const CLAVE = '__bot_rpa_estado';
  const estado = JSON.parse(sessionStorage.getItem(CLAVE) || '{"x":40,"y":40,"texto":""}');
  const guardar = () => sessionStorage.setItem(CLAVE, JSON.stringify(estado));

  const estilo = document.createElement('style');
  estilo.textContent = `
    #bot-cursor, #bot-onda, #bot-marco, #bot-banner { position: fixed; pointer-events: none; z-index: 2147483647; }
    #bot-cursor { width: 26px; height: 26px; margin: -2px 0 0 -3px; transition: transform .08s; }
    #bot-cursor.presionado { transform: scale(.82); }
    #bot-onda { width: 40px; height: 40px; margin: -20px 0 0 -20px; border-radius: 50%;
      border: 3px solid #f97316; opacity: 0; }
    #bot-onda.activa { animation: bot-onda .45s ease-out; }
    @keyframes bot-onda { from { transform: scale(.3); opacity: 1; } to { transform: scale(1.6); opacity: 0; } }
    #bot-marco { border: 2px solid #f97316; border-radius: 3px; box-shadow: 0 0 0 4px rgba(249,115,22,.25);
      transition: all .15s; display: none; }
    #bot-banner { bottom: 12px; right: 12px; max-width: 420px; padding: 8px 12px; border-radius: 8px;
      background: rgba(17,24,39,.92); color: #fff; font: 600 13px/1.35 system-ui, sans-serif;
      box-shadow: 0 4px 14px rgba(0,0,0,.3); display: none; }
    #bot-banner b { color: #fdba74; }
  `;
  document.head.appendChild(estilo);

  const cursor = document.createElement('div');
  cursor.id = 'bot-cursor';
  cursor.innerHTML =
    '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7.5 19 2.6-7.6L21 10.8z" ' +
    'fill="#f97316" stroke="#7c2d12" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const onda = document.createElement('div');
  onda.id = 'bot-onda';
  const marco = document.createElement('div');
  marco.id = 'bot-marco';
  const banner = document.createElement('div');
  banner.id = 'bot-banner';
  document.body.append(marco, onda, cursor, banner);

  const ubicar = (x, y) => {
    estado.x = x;
    estado.y = y;
    cursor.style.left = onda.style.left = `${x}px`;
    cursor.style.top = onda.style.top = `${y}px`;
  };

  const resaltar = (elemento) => {
    const interactivo = elemento && elemento.closest('input, select, textarea, button, a');
    if (!interactivo) {
      marco.style.display = 'none';
      return;
    }
    const caja = interactivo.getBoundingClientRect();
    Object.assign(marco.style, {
      display: 'block',
      left: `${caja.left - 4}px`,
      top: `${caja.top - 4}px`,
      width: `${caja.width + 8}px`,
      height: `${caja.height + 8}px`,
    });
  };

  const anunciar = (texto) => {
    estado.texto = texto;
    guardar();
    banner.innerHTML = texto ? `🤖 <b>Bot RPA</b> · ${texto}` : '';
    banner.style.display = texto ? 'block' : 'none';
  };

  document.addEventListener('mousemove', (e) => {
    ubicar(e.clientX, e.clientY);
    resaltar(document.elementFromPoint(e.clientX, e.clientY));
  }, true);
  document.addEventListener('mousedown', () => {
    cursor.classList.add('presionado');
    onda.classList.remove('activa');
    void onda.offsetWidth; // reinicia la animación
    onda.classList.add('activa');
  }, true);
  document.addEventListener('mouseup', () => cursor.classList.remove('presionado'), true);
  window.addEventListener('pagehide', guardar);

  ubicar(estado.x, estado.y);
  anunciar(estado.texto);
  window.__botCursor = { anunciar };
}
