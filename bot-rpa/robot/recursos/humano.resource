*** Settings ***
Documentation    Acciones "humanas": el bot mueve el mouse hasta cada elemento, lo resalta,
...              hace clic y escribe tecla por tecla, con un cursor visible dibujado en la
...              página. Así se ve (en vivo o en el video) cómo opera SISCAJA.

Library          Browser
Library          bot_rpa.BotRPA


*** Variables ***
# Pasos del movimiento del mouse y pausa entre teclas. `python -m bot_rpa` los sube en modo
# visible (30 pasos, 70 ms) para que la demo se vea natural; oculto usa estos valores.
${PASOS_MOUSE}    5
${PAUSA_TECLA}    10 ms


*** Keywords ***
Instalar Cursor
    [Documentation]    Dibuja el cursor y el banner del bot en la página actual (idempotente).
    ${script}    Script Del Cursor
    Evaluate JavaScript    ${None}    ${script}

Anunciar
    [Documentation]    Muestra en el banner de la página qué está haciendo el bot.
    [Arguments]    ${texto}
    Instalar Cursor
    Evaluate JavaScript    ${None}    (texto) => window.__botCursor.anunciar(texto)    arg=${texto}

Mover Mouse A
    [Documentation]    Desliza el mouse hasta el centro del elemento, en varios pasos.
    [Arguments]    ${selector}
    Instalar Cursor
    Scroll To Element    ${selector}
    ${caja}    Get BoundingBox    ${selector}
    ${x}    Evaluate    ${caja}[x] + ${caja}[width] / 2
    ${y}    Evaluate    ${caja}[y] + ${caja}[height] / 2
    Mouse Move    ${x}    ${y}    steps=${PASOS_MOUSE}
    RETURN    ${x}    ${y}

Clic Humano
    [Documentation]    Lleva el mouse al elemento y hace clic donde se ve el cursor.
    [Arguments]    ${selector}
    ${x}    ${y}    Mover Mouse A    ${selector}
    Mouse Button    click    ${x}    ${y}

Escribir Humano
    [Documentation]    Hace clic en el campo y escribe el texto tecla por tecla.
    [Arguments]    ${selector}    ${texto}
    Clic Humano    ${selector}
    Type Text    ${selector}    ${texto}    delay=${PAUSA_TECLA}

Escribir Secreto Humano
    [Documentation]    Igual que Escribir Humano, pero el texto no queda en los logs.
    [Arguments]    ${selector}    ${variable_de_entorno}
    Clic Humano    ${selector}
    Type Secret    ${selector}    %${variable_de_entorno}    delay=${PAUSA_TECLA}

Elegir Opcion Humano
    [Documentation]    Abre la lista desplegable y elige la opcion por su valor.
    [Arguments]    ${selector}    ${valor}
    Clic Humano    ${selector}
    Select Options By    ${selector}    value    ${valor}
    # Cierra la lista desplegada si quedó abierta.
    Keyboard Key    press    Escape

Capturar Paso
    [Documentation]    Toma una captura de la página (con cursor y banner) y registra el paso.
    [Arguments]    ${paso}    ${descripcion}
    ${ruta}    Ruta De Captura    ${paso}
    Take Screenshot    filename=${ruta}    log_screenshot=False
    Registrar Paso    ${paso}    ${descripcion}    ${ruta}
