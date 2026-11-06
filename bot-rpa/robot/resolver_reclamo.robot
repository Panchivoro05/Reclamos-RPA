*** Settings ***
Documentation    Resuelve un reclamo en SISCAJA operando su interfaz web, como un cajero:
...              inicia sesion, busca el pedido, verifica items y montos, registra la
...              compensacion y lee el numero de operacion.
...
...              Deja en ${SALIDA}: resultado.json, capturas/ y video/ (si se graba).
...              Normalmente se ejecuta con `python -m bot_rpa`, que arma las variables.

Library          Collections
Library          Browser
Library          bot_rpa.BotRPA
Resource         recursos/humano.resource
Resource         recursos/siscaja.resource

Task Setup       Abrir SISCAJA
Task Teardown    Cerrar Y Guardar Resultado


*** Variables ***
${CAJA_URL}            http://127.0.0.1:5050
${OPERADOR_USUARIO}    cajero01
${PEDIDO}              ${EMPTY}
${TIPO_RECLAMO}        ${EMPTY}
${SOLUCION}            ${EMPTY}
${MONTO}               ${EMPTY}
${MOTIVO}              ${EMPTY}
# JSON: [{"producto": "Hamburguesa Clasica", "cantidad": 1}, ...]. Vacío: no se compara.
${ITEMS_ESPERADOS}     ${EMPTY}
# Total esperado del pedido ("82.50"). Vacío: no se compara.
${TOTAL_ESPERADO}      ${EMPTY}
${SALIDA}              ${OUTPUT DIR}
${VISIBLE}             ${False}
${VELOCIDAD_MS}        250
${GRABAR_VIDEO}        ${True}


*** Tasks ***
Resolver Reclamo
    [Documentation]    Flujo completo de un cajero: login, busqueda, verificacion, compensacion
    ...    y lectura del comprobante.
    Iniciar Sesion En SISCAJA    ${CAJA_URL}    ${OPERADOR_USUARIO}
    Buscar Pedido    ${PEDIDO}
    Verificar Pedido    ${ITEMS_ESPERADOS}    ${TOTAL_ESPERADO}
    Registrar Compensacion    ${SOLUCION}    ${MONTO}    ${MOTIVO}
    Leer Comprobante


*** Keywords ***
Abrir SISCAJA
    [Documentation]    Abre el navegador (visible u oculto) y empieza a grabar la ejecucion.
    # Desde la línea de comandos llegan como texto ("True"/"False").
    ${visible}    Evaluate    str($VISIBLE).strip().lower() == 'true'
    ${grabar}    Evaluate    str($GRABAR_VIDEO).strip().lower() == 'true'
    Set Browser Timeout    15s
    # Las capturas de error las toma el propio bot (Capturar Paso), no Browser.
    Register Keyword To Run On Failure    ${None}
    Iniciar Resultado    ${SALIDA}
    ...    pedido=${PEDIDO}
    ...    tipo_reclamo=${TIPO_RECLAMO}
    ...    solucion=${SOLUCION}
    ...    monto_solicitado=${MONTO}
    IF    $visible
        # Demo: ventana real y más lenta (python -m bot_rpa también suaviza mouse y tipeo).
        New Browser    chromium    headless=False    slowMo=${VELOCIDAD_MS} ms
    ELSE
        New Browser    chromium    headless=True
    END
    VAR    &{tamano}    width=${1280}    height=${800}
    IF    $grabar
        VAR    &{video}    dir=${SALIDA}/video    size=${tamano}
        New Context    viewport=${tamano}    recordVideo=${video}    locale=es-PE
    ELSE
        New Context    viewport=${tamano}    locale=es-PE
    END
    New Page    about:blank

Cerrar Y Guardar Resultado
    [Documentation]    Cierra el navegador (lo que guarda el video) y escribe resultado.json.
    # Si falló y SISCAJA no mostró un error (ya capturado), deja una captura del momento.
    ${ultimo}    Ultimo Paso
    IF    $TEST_STATUS == 'FAIL' and $ultimo != 'error'
        Run Keyword And Ignore Error    Anunciar    Error · ${TEST MESSAGE}
        Run Keyword And Ignore Error    Capturar Paso    fallo    ${TEST MESSAGE}
    END
    # Cerrar el contexto escribe el video en disco.
    Run Keyword And Ignore Error    Close Context
    Run Keyword And Ignore Error    Close Browser
    ${ruta}    Finalizar Resultado    ${TEST STATUS}    ${TEST MESSAGE}
    Log    Resultado: ${ruta}
