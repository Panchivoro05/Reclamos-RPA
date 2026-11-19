*** Settings ***
Documentation    Pasos del bot sobre SISCAJA. Solo usa la interfaz web (ids estables del HTML):
...              SISCAJA no tiene API.

Library          Collections
Library          Browser
Library          bot_rpa.BotRPA
Resource         humano.resource


*** Keywords ***
Iniciar Sesion En SISCAJA
    [Documentation]    Ingresa con el operador de caja; la clave se escribe sin quedar en logs.
    [Arguments]    ${url}    ${usuario}
    Go To    ${url}/login
    Anunciar    Paso 1 de 5 · Iniciando sesion en SISCAJA
    Escribir Humano    id=usuario    ${usuario}
    Escribir Secreto Humano    id=clave    CAJA_OPERADOR_CLAVE
    Clic Humano    id=btn-ingresar
    Esperar Respuesta De SISCAJA    operador-actual    credenciales_invalidas
    Get Text    id=operador-actual    ==    ${usuario}
    Anunciar    Paso 1 de 5 · Sesion iniciada como ${usuario}
    Capturar Paso    login    Inicio de sesion como ${usuario}

Buscar Pedido
    [Documentation]    Busca el pedido por su codigo y espera su detalle.
    [Arguments]    ${codigo}
    Anunciar    Paso 2 de 5 · Buscando el pedido ${codigo}
    Escribir Humano    id=buscar-codigo    ${codigo}
    Clic Humano    id=btn-buscar
    Esperar Respuesta De SISCAJA    pedido-codigo    pedido_inexistente
    Get Text    id=pedido-codigo    ==    ${codigo}
    Anunciar    Paso 2 de 5 · Pedido ${codigo} encontrado
    Capturar Paso    pedido    Pedido ${codigo} encontrado

Verificar Pedido
    [Documentation]    Lee el estado, los ítems y el total, y los compara con lo esperado.
    [Arguments]    ${items_esperados}    ${total_esperado}
    Anunciar    Paso 3 de 5 · Verificando items y montos
    ${estado}    Get Text    id=pedido-estado
    IF    '${estado}' == 'CANCELADO'
        Fallar Con Codigo    pedido_no_compensable    El pedido esta cancelado en caja.
    END
    ${items}    Leer Items Del Pedido
    Verificar Items    ${items}    ${items_esperados}
    Mover Mouse A    id=pedido-total
    ${total}    Get Text    id=pedido-total
    Verificar Total    ${total}    ${total_esperado}
    Guardar Dato    total_en_caja    ${total}
    Anunciar    Paso 3 de 5 · Datos verificados (total ${total})
    Capturar Paso    verificacion    Items y total verificados (${total})

Leer Items Del Pedido
    [Documentation]    Recorre la grilla con el mouse, fila por fila, como quien lee.
    ${cantidad}    Get Element Count    css=#tabla-items tr.item
    VAR    @{items}    @{EMPTY}
    FOR    ${n}    IN RANGE    1    ${cantidad + 1}
        Mover Mouse A    id=item-${n}
        ${producto}    Get Text    css=#item-${n} .item-producto
        ${unidades}    Get Text    css=#item-${n} .item-cantidad
        VAR    &{item}    producto=${producto}    cantidad=${unidades}
        Append To List    ${items}    ${item}
    END
    RETURN    ${items}

Registrar Compensacion
    [Documentation]    Llena y envia el formulario de compensacion de SISCAJA.
    [Arguments]    ${solucion}    ${monto}    ${motivo}
    Anunciar    Paso 4 de 5 · Registrando la compensacion
    ${hay_boton}    Get Element Count    id=btn-compensar
    IF    ${hay_boton} == 0
        Fallar Con Codigo    pedido_no_compensable    El pedido no admite compensaciones en caja.
    END
    Clic Humano    id=btn-compensar
    Esperar Respuesta De SISCAJA    form-compensacion    pedido_no_compensable
    Elegir Opcion Humano    id=comp-tipo    ${solucion}
    IF    $monto    Escribir Humano    id=comp-monto    ${monto}
    Escribir Humano    id=comp-motivo    ${motivo}
    Capturar Paso    formulario    Formulario de compensacion completo
    Clic Humano    id=btn-registrar
    Esperar Respuesta De SISCAJA    numero-operacion    compensacion_rechazada

Leer Comprobante
    [Documentation]    Lee el numero de operacion, el monto y el tipo del comprobante.
    Anunciar    Paso 5 de 5 · Leyendo el numero de operacion
    Mover Mouse A    id=numero-operacion
    ${numero}    Get Text    id=numero-operacion    matches    ^CMP-\\d{6}$
    ${monto}    Get Text    id=op-monto
    ${tipo}    Get Attribute    id=op-tipo    data-tipo
    Guardar Dato    numero_operacion    ${numero}
    Guardar Dato    monto_registrado    ${monto}
    Guardar Dato    tipo_registrado    ${tipo}
    Anunciar    Listo · Operacion ${numero} registrada (${monto})
    Capturar Paso    comprobante    Operacion ${numero} registrada por ${monto}

Buscar Compensacion Previa
    [Documentation]    Revisa el historial del pedido: si ya hay una compensacion de este
    ...    reclamo (su codigo va al inicio del motivo), devuelve su numero. Asi un reintento
    ...    del worker nunca compensa dos veces. Sin codigo de reclamo devuelve vacio.
    [Arguments]    ${reclamo}
    IF    not $reclamo    RETURN    ${EMPTY}
    ${fila}    Xpath Compensacion De Reclamo    ${reclamo}
    ${cantidad}    Get Element Count    ${fila}
    IF    ${cantidad} == 0    RETURN    ${EMPTY}
    ${numero}    Get Text    ${fila}/td[1]
    RETURN    ${numero}

Usar Compensacion Previa
    [Documentation]    El reclamo ya estaba compensado: lee esa operacion en vez de registrar otra.
    [Arguments]    ${numero}
    Anunciar    Paso 4 de 5 · Este reclamo ya tenia la operacion ${numero}
    Mover Mouse A    id=comp-${numero}
    ${monto}    Get Text    css=tr[id="comp-${numero}"] td.num
    Guardar Dato    numero_operacion    ${numero}
    Guardar Dato    monto_registrado    ${monto}
    Guardar Dato    reutilizada    si
    Anunciar    Listo · Se reutilizo la operacion ${numero} (${monto})
    Capturar Paso    ya_registrada    El reclamo ya tenia la operacion ${numero} por ${monto}

Esperar Respuesta De SISCAJA
    [Documentation]    Después de un clic que cambia de página, espera lo que muestre SISCAJA:
    ...    el elemento de éxito de la página siguiente o un mensaje de error. Si es un
    ...    error, lo lee, lo captura y termina con ese código.
    [Arguments]    ${id_exito}    ${codigo_si_falla}
    Wait For Elements State    css=\#mensaje-error, \#${id_exito}    visible
    Instalar Cursor
    ${hay_error}    Get Element Count    id=mensaje-error
    IF    ${hay_error} > 0
        Mover Mouse A    id=mensaje-error
        ${mensaje}    Get Text    id=mensaje-error
        Anunciar    Error · ${mensaje}
        Capturar Paso    error    SISCAJA rechazo la operacion: ${mensaje}
        Fallar Con Codigo    ${codigo_si_falla}    ${mensaje}
    END
