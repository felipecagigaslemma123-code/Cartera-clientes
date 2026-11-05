"""Actualización y presentación local del dashboard sin dependencias externas."""

SCRIPT = r"""
(() => {
  'use strict';
  const bloque = document.getElementById('datos-cartera');
  if (!bloque) return;
  const datos = JSON.parse(bloque.textContent);
  const habilitada = datos.actualizacion_habilitada === true;
  const finito = valor => typeof valor === 'number' && Number.isFinite(valor) ? valor : null;
  const positivo = valor => finito(valor) !== null && valor > 0 ? valor : null;
  const numero = new Intl.NumberFormat('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const cantidad = new Intl.NumberFormat('es-AR', {maximumSignificantDigits: 17});
  const momento = new Intl.DateTimeFormat('es-AR', {timeZone: 'America/Argentina/Buenos_Aires', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
  const formato = valor => finito(valor) === null ? 'sin dato' : numero.format(valor);
  const dinero = valor => finito(valor) === null ? 'sin dato' : '$ ' + numero.format(valor);
  const porcentaje = valor => finito(valor) === null ? 'sin dato' : numero.format(valor * 100) + '%';
  const seguro = valor => Number.isFinite(valor) ? valor : null;
  const origen = estado => ({extracto: 'extracto', estimado: 'estimado', mixto: 'incluye estimado', incompleto: 'falta estimar'}[estado] || 'falta estimar');
  const estado = valor => ({vivo: 'En vivo', cache: 'Último dato', sin_dato: 'Sin dato'}[valor] || 'Sin dato');
  const suma = valores => valores.length ? seguro(valores.reduce((total, valor) => total + valor, 0)) : null;
  const elemento = id => document.getElementById(id);
  const texto = (id, contenido) => { const nodo = elemento(id); if (nodo) nodo.textContent = contenido; };
  const aviso = (id, contenido) => { const nodo = elemento(id); if (nodo) { nodo.textContent = contenido; nodo.hidden = !contenido; } };
  const hora = valor => {
    if (typeof valor !== 'string' || !valor.trim()) return 'sin dato';
    const fecha = new Date(valor);
    return Number.isFinite(fecha.getTime()) ? momento.format(fecha).replace(', ', ' ') : 'sin dato';
  };
  const dia = valor => typeof valor === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(valor) ? valor.split('-').reverse().join('/') : 'sin dato';
  const plural = valor => valor === 1 ? '1 día' : valor + ' días';
  const fechaLocal = fecha => [fecha.getFullYear(), String(fecha.getMonth() + 1).padStart(2, '0'), String(fecha.getDate()).padStart(2, '0')].join('-');
  const diaFecha = textoFecha => {
    if (typeof textoFecha !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(textoFecha)) return null;
    const [ano, mes, dia] = textoFecha.split('-').map(Number);
    const fecha = new Date(Date.UTC(ano, mes - 1, dia));
    if (fecha.getUTCFullYear() !== ano || fecha.getUTCMonth() !== mes - 1 || fecha.getUTCDate() !== dia) return null;
    return fecha.getTime() / 86400000;
  };
  const diasRestantes = vencimiento => {
    const dia = diaFecha(vencimiento);
    return dia === null ? null : dia - diaFecha(fechaLocal(new Date()));
  };
  const posiciones = (datos.posiciones || []).map(posicion => ({...posicion}));
  let mep = datos.mep ? {...datos.mep} : null;
  const pendientes = new Set(['arg_cedears', 'arg_stocks', 'arg_bonds', 'arg_notes', 'arg_corp']);
  let ocupada = false;
  let rondaFallida = false;
  let ultimaConsulta = null;
  let ultimaExitosa = null;
  const boton = elemento('actualizar');
  for (const posicion of posiciones) {
    posicion.ultimo = posicion.estado === 'sin_dato' ? null : positivo(posicion.ultimo);
    posicion.estado = posicion.ultimo === null ? 'sin_dato' : 'cache';
    posicion.bid = positivo(posicion.bid);
    posicion.ask = positivo(posicion.ask);
    posicion.pct_dia = finito(posicion.pct_dia);
    const instante = Date.parse(posicion.consultado_en);
    if (posicion.ultimo !== null && Number.isFinite(instante)) ultimaExitosa = Math.max(ultimaExitosa || instante, instante);
  }
  if (mep) {
    mep.ultimo = positivo(mep.ultimo);
    mep.estado = mep.ultimo === null ? 'sin_dato' : 'cache';
  }


  const tituloOriginal = typeof document.title === 'string' ? document.title : 'Cartera';
  const estadoNiveles = new Map();
  const botonAvisos = elemento('activar-avisos');
  let cantidadAlertas = 0;
  let ultimoChequeo = null;
  let especiesChequeadas = 0;
  let especiesSinChequear = [];
  let contextoAudio = null;
  let falloPermiso = false;
  let falloNotificacion = false;
  const relojMercado = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Argentina/Buenos_Aires', weekday: 'short',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  });

  function enHorarioMercado() {
    const partes = Object.fromEntries(relojMercado.formatToParts(new Date()).map(parte => [parte.type, parte.value]));
    const minutos = Number(partes.hour) * 60 + Number(partes.minute);
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(partes.weekday) && minutos >= 11 * 60 && minutos < 17 * 60;
  }

  function conNiveles() {
    return posiciones.filter(posicion => positivo(posicion.take_profit) !== null || positivo(posicion.stop_loss) !== null);
  }

  function mostrarEstadoAlertas() {
    const configuradas = conNiveles().length;
    if (!configuradas) {
      texto('alertas-estado', 'Alertas sin niveles definidos. Leé los niveles al generar nuevamente el archivo.');
    } else if (!enHorarioMercado()) {
      texto('alertas-estado', 'Alertas fuera de horario: se chequean de lunes a viernes de 11:00 a 17:00, hora de Argentina.');
    } else if (ultimoChequeo === null) {
      texto('alertas-estado', 'Alertas sin chequear: esperando la primera ronda de precios en vivo.');
    } else {
      texto('alertas-estado', 'Chequeado ' + hora(ultimoChequeo) + ': ' + especiesChequeadas + ' de ' + configuradas +
        ' especies con niveles.' + (especiesSinChequear.length ? ' No se pudo chequear: ' + especiesSinChequear.join(', ') + '.' : ''));
    }
  }

  function mostrarEstadoAvisos(permiso) {
    try {
      if (falloPermiso || falloNotificacion || typeof globalThis.Notification !== 'function') {
        texto('avisos-estado', 'Notificaciones no disponibles. Los avisos quedan en pantalla.');
        return;
      }
      const estado = permiso || globalThis.Notification.permission;
      texto('avisos-estado', estado === 'granted' ?
        'Notificaciones activas. El sonido se habilita con el botón si el navegador lo permite.' :
        estado === 'denied' ? 'Notificaciones bloqueadas. Los avisos quedan en pantalla.' :
        'Notificaciones sin activar. Los avisos quedan en pantalla.');
    } catch (_) {
      texto('avisos-estado', 'Notificaciones no disponibles. Los avisos quedan en pantalla.');
    }
  }

  function obtenerAudio() {
    if (contextoAudio) return contextoAudio;
    const Constructor = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (typeof Constructor !== 'function') return null;
    contextoAudio = new Constructor();
    return contextoAudio;
  }

  async function habilitarSonido() {
    try {
      const contexto = obtenerAudio();
      if (contexto && typeof contexto.resume === 'function') await contexto.resume();
    } catch (_) {
      // El navegador puede impedir sonido: el cartel siempre queda disponible.
    }
  }

  function sonar() {
    try {
      const contexto = obtenerAudio();
      if (!contexto || contexto.state === 'suspended' || contexto.state === 'closed') return;
      const tono = contexto.createOscillator();
      const volumen = contexto.createGain();
      tono.type = 'sine';
      tono.frequency.value = 880;
      volumen.gain.value = 0.12;
      tono.connect(volumen);
      volumen.connect(contexto.destination);
      tono.start(contexto.currentTime);
      tono.stop(contexto.currentTime + 0.18);
    } catch (_) {
      // Ninguna falla de audio puede interrumpir las consultas o los avisos visuales.
    }
  }

  async function activarAvisos() {
    // Comenzar dentro del gesto del usuario, antes de esperar el permiso.
    const sonido = habilitarSonido();
    falloPermiso = false;
    try {
      if (typeof globalThis.Notification !== 'function') {
        mostrarEstadoAvisos();
        return;
      }
      let permiso = globalThis.Notification.permission;
      if (permiso !== 'granted') {
        if (typeof globalThis.Notification.requestPermission !== 'function') throw new Error('Sin soporte');
        permiso = await globalThis.Notification.requestPermission();
        if (!['granted', 'denied', 'default'].includes(permiso)) throw new Error('Permiso no disponible');
      }
      mostrarEstadoAvisos(permiso);
    } catch (_) {
      falloPermiso = true;
      mostrarEstadoAvisos();
    } finally {
      await sonido;
      sonar();
    }
  }

  function notificarRonda(lineas) {
    sonar();
    try {
      if (typeof globalThis.Notification === 'function' && globalThis.Notification.permission === 'granted') {
        const slug = datos.cliente && typeof datos.cliente.slug === 'string' ? datos.cliente.slug : '';
        new globalThis.Notification('Alertas · ' + slug, {body: lineas.join('\n')});
        falloNotificacion = false;
        mostrarEstadoAvisos();
      }
    } catch (_) {
      falloNotificacion = true;
      mostrarEstadoAvisos();
    }
  }

  function volvioDentroDelNivel(referencia, nivel, campo) {
    // Comparar las expresiones decimales evita que 0,27 × 0,99 redondee
    // por encima de 0,2673 y convierta el límite exacto en un rearme.
    const decimal = valor => {
      const [mantisa, potencia = '0'] = valor.toString().split('e');
      const fraccion = mantisa.split('.')[1] || '';
      return {coeficiente: BigInt(mantisa.replace('.', '')), exponente: Number(potencia) - fraccion.length};
    };
    const precio = decimal(referencia);
    const limite = decimal(nivel);
    const exponente = Math.min(precio.exponente, limite.exponente);
    const izquierda = precio.coeficiente * 100n * 10n ** BigInt(precio.exponente - exponente);
    const factor = campo === 'take_profit' ? 99n : 101n;
    const derecha = limite.coeficiente * factor * 10n ** BigInt(limite.exponente - exponente);
    return campo === 'take_profit' ? izquierda < derecha : izquierda > derecha;
  }

  function evaluarAlertas() {
    if (!elemento('alertas-lista')) return;
    const configuradas = conNiveles();
    if (!configuradas.length || !enHorarioMercado()) {
      mostrarEstadoAlertas();
      return;
    }
    const nuevas = [];
    especiesChequeadas = 0;
    especiesSinChequear = [];
    ultimoChequeo = new Date().toISOString();
    for (const posicion of configuradas) {
      const referencia = positivo(posicion.bid) || positivo(posicion.ultimo);
      if (posicion.estado !== 'vivo' || referencia === null) {
        especiesSinChequear.push(String(posicion.ticker));
        continue;
      }
      especiesChequeadas += 1;
      for (const campo of ['take_profit', 'stop_loss']) {
        const nivel = positivo(posicion[campo]);
        const clave = JSON.stringify([posicion.ticker, campo]);
        if (nivel === null) {
          estadoNiveles.delete(clave);
          continue;
        }
        let registro = estadoNiveles.get(clave);
        if (!registro || registro.nivel !== nivel) registro = {nivel, disparada: false};
        if (registro.disparada && volvioDentroDelNivel(referencia, nivel, campo)) {
          registro.disparada = false;
        }
        const alcanzado = campo === 'take_profit' ? referencia >= nivel : referencia <= nivel;
        if (!registro.disparada && alcanzado) {
          registro.disparada = true;
          nuevas.push(String(posicion.ticker) + (campo === 'take_profit' ? ' take profit' : ' stop loss') +
            ': precio ' + formato(referencia) + ', nivel ' + formato(nivel));
        }
        estadoNiveles.set(clave, registro);
      }
    }
    if (nuevas.length) {
      const lista = elemento('alertas-lista');
      for (const linea of nuevas) {
        const nodo = document.createElement('li');
        nodo.textContent = hora(ultimoChequeo) + ' · ' + linea;
        lista.appendChild(nodo);
      }
      cantidadAlertas += nuevas.length;
      document.title = '(' + cantidadAlertas + ') ' + tituloOriginal;
      notificarRonda(nuevas);
    }
    mostrarEstadoAlertas();
  }

  function calcular(posicion) {
    const ultimo = positivo(posicion.ultimo);
    const unidades = positivo(posicion.cotiza_cada);
    const q = positivo(posicion.cantidad);
    const valor = ultimo !== null && q !== null && (unidades === 1 || unidades === 100) ? seguro(q / unidades * ultimo) : null;
    const completo = ['extracto', 'estimado', 'mixto'].includes(posicion.estado_costo) && positivo(posicion.costo) !== null;
    const costo = completo ? posicion.costo : null;
    const compra = valor !== null && costo !== null ? seguro(valor - costo) : null;
    const base = positivo(posicion.precio_dia_cero) !== null && q !== null && (unidades === 1 || unidades === 100) ? seguro(q / unidades * posicion.precio_dia_cero) : null;
    const diferencia = valor !== null && base !== null ? seguro(valor - base) : null;
    return {...posicion, valor, costo, compra, base, diferencia};
  }

  function celda(fila, contenido, clase = '') {
    const nodo = document.createElement('td');
    nodo.textContent = contenido;
    if (clase) nodo.className = clase;
    fila.appendChild(nodo);
  }

  function renderizarPosiciones(calculadas, total) {
    const cuerpo = elemento('posiciones-body');
    if (!cuerpo) return;
    cuerpo.replaceChildren();
    for (const posicion of calculadas) {
      const fila = document.createElement('tr');
      fila.dataset.ticker = posicion.ticker;
      celda(fila, posicion.ticker);
      celda(fila, posicion.especie || 'sin dato');
      celda(fila, posicion.tipo || 'sin dato');
      celda(fila, positivo(posicion.cantidad) === null ? 'sin dato' : cantidad.format(posicion.cantidad), 'numero');
      celda(fila, formato(posicion.ultimo), 'numero');
      celda(fila, dinero(posicion.valor), 'numero');
      celda(fila, posicion.valor !== null && positivo(total) !== null ? porcentaje(posicion.valor / total) : 'sin dato', 'numero');
      celda(fila, finito(posicion.pct_dia) === null ? 'sin dato' : formato(posicion.pct_dia) + '%', 'numero');
      celda(fila, posicion.costo === null ? 'falta estimar' : dinero(posicion.costo), 'numero');
      celda(fila, origen(posicion.estado_costo), posicion.estado_costo === 'extracto' ? '' : 'estimado');
      const compra = posicion.costo === null ? 'falta estimar' : posicion.compra === null ? 'sin dato' : dinero(posicion.compra) + ' (' + porcentaje(posicion.compra / posicion.costo) + ')';
      celda(fila, compra, 'numero');
      celda(fila, posicion.diferencia === null ? 'sin dato' : dinero(posicion.diferencia) + ' (' + porcentaje(posicion.diferencia / posicion.base) + ')', 'numero');
      const referencia = positivo(posicion.bid) || positivo(posicion.ultimo);
      for (const campo of ['take_profit', 'stop_loss']) {
        const nivel = positivo(posicion[campo]);
        celda(fila, nivel !== null && referencia !== null ? porcentaje(nivel / referencia - 1) : 'sin dato', 'numero');
      }
      let detalle = estado(posicion.estado) + ' · consulta ' + hora(posicion.consultado_en);
      const dias = diasRestantes(posicion.vencimiento);
      if (dias !== null && dias < 0 && posicion.estado !== 'vivo') detalle += ' · Especie vencida: la fuente puede haber dejado de cotizarla.';
      celda(fila, detalle, 'estado');
      cuerpo.appendChild(fila);
    }
  }

  function renderizarTotales(calculadas) {
    const conocidas = calculadas.filter(posicion => posicion.valor !== null);
    const total = suma(conocidas.map(posicion => posicion.valor));
    const dolar = mep ? positivo(mep.ultimo) : null;
    const cuerpo = elemento('totales-body');
    if (cuerpo) {
      cuerpo.replaceChildren();
      const tipos = [...new Set(calculadas.map(posicion => posicion.tipo))];
      for (const tipo of [...tipos, null]) {
        const grupo = tipo === null ? calculadas : calculadas.filter(posicion => posicion.tipo === tipo);
        const valores = grupo.filter(posicion => posicion.valor !== null);
        const valor = suma(valores.map(posicion => posicion.valor));
        const fila = document.createElement('tr');
        celda(fila, tipo === null ? 'Total de posiciones conocidas' : tipo);
        celda(fila, dinero(valor), 'numero');
        celda(fila, valor !== null && dolar !== null ? 'USD ' + formato(seguro(valor / dolar)) : 'sin dato', 'numero');
        celda(fila, (grupo.length - valores.length) + ' sin precio');
        cuerpo.appendChild(fila);
      }
    }
    const comparables = conocidas.filter(posicion => posicion.costo !== null && posicion.compra !== null);
    const costo = suma(comparables.map(posicion => posicion.costo));
    const valorComparable = suma(comparables.map(posicion => posicion.valor));
    const resultado = valorComparable !== null && costo !== null ? seguro(valorComparable - costo) : null;
    texto('resultado-compra', 'Desde la compra, solo la parte con costo completo y precio: ' + dinero(resultado) +
      (resultado !== null && positivo(costo) !== null ? ' (' + porcentaje(resultado / costo) + ')' : '') +
      ' · ' + comparables.length + ' de ' + calculadas.length + ' posiciones · valuación comparable ' + dinero(valorComparable) +
      '. Los costos mixtos o estimados incluyen estimaciones.');
    const conBase = conocidas.filter(posicion => posicion.base !== null && posicion.diferencia !== null);
    const valorConBase = suma(conBase.map(posicion => posicion.valor));
    const base = suma(conBase.map(posicion => posicion.base));
    const diferencia = valorConBase !== null && base !== null ? seguro(valorConBase - base) : null;
    const mepCero = datos.dia_cero ? positivo(datos.dia_cero.mep) : null;
    const diferenciaUsd = diferencia !== null && dolar !== null && mepCero !== null ? seguro(valorConBase / dolar - base / mepCero) : null;
    texto('variacion-precios', 'Variación de precios desde el día cero, con la misma cantidad: ' + dinero(diferencia) +
      ' · USD ' + formato(diferenciaUsd) + ' · ' + conBase.length + ' de ' + calculadas.length + ' posiciones comparables.');
    texto('mep-dato', 'Dólar MEP: ' + formato(dolar) + (mep && dolar !== null ? ' · ' + estado(mep.estado) + ' · consulta ' + hora(mep.consultado_en) : ''));
    renderizarPosiciones(calculadas, total);
    renderizarIntegral(calculadas);
  }

  function renderizarIntegral(calculadas) {
    const integral = datos.integral;
    if (!integral) return;
    const faltantes = [...(integral.faltantes_fijos || [])];
    const agregarFaltante = etiqueta => { if (!faltantes.includes(etiqueta)) faltantes.push(etiqueta); };
    const inicial = finito(integral.patrimonio_inicial);
    if (inicial === null && !faltantes.length) agregarFaltante('patrimonio inicial');
    const caja = integral.efectivo || {};
    const ars = finito(caja.ARS);
    const usd = finito(caja.USD);
    if (ars === null) agregarFaltante('efectivo ARS calculado');
    if (usd === null) agregarFaltante('efectivo USD calculado');
    for (const posicion of calculadas) {
      if (posicion.valor === null) agregarFaltante('precio actual de ' + posicion.ticker);
    }
    // Una cartera vendida por completo tiene valuación cero; no necesita sus precios anteriores.
    const valuacion = calculadas.some(posicion => posicion.valor === null) ? null :
      seguro(calculadas.reduce((total, posicion) => total + posicion.valor, 0));
    if (valuacion === null && calculadas.every(posicion => posicion.valor !== null)) agregarFaltante('valuación actual fuera de rango');
    const dolar = mep ? positivo(mep.ultimo) : null;
    if (usd !== null && usd !== 0 && dolar === null) agregarFaltante('dólar MEP actual');
    const conversion = usd === 0 ? 0 : usd !== null && dolar !== null ? seguro(usd * dolar) : null;
    if (usd !== null && usd !== 0 && dolar !== null && conversion === null) agregarFaltante('conversión de efectivo USD fuera de rango');
    const patrimonio = valuacion !== null && ars !== null && conversion !== null ? seguro(valuacion + ars + conversion) : null;
    if (valuacion !== null && ars !== null && conversion !== null && patrimonio === null) agregarFaltante('patrimonio final fuera de rango');
    const aportes = finito(integral.aportes);
    const retiros = finito(integral.retiros);
    if (aportes === null) agregarFaltante('aportes');
    if (retiros === null) agregarFaltante('retiros');
    let total = faltantes.length === 0 && patrimonio !== null && inicial !== null ? seguro(patrimonio - inicial - aportes + retiros) : null;
    if (!faltantes.length && total === null) agregarFaltante('resultado completo fuera de rango');
    texto('integral-inicial', formato(inicial));
    texto('integral-valuacion', formato(valuacion));
    texto('integral-final', formato(patrimonio));
    texto('integral-total', formato(total));
    for (const campo of ['aportes', 'retiros', 'rentas', 'dividendos', 'gastos']) texto('integral-' + campo, formato(integral[campo]));
    aviso('integral-faltantes', faltantes.length ? 'Sin dato; faltan: ' + faltantes.join(', ') + '.' : '');
    const precioAnterior = calculadas.some(posicion => posicion.valor !== null && posicion.estado !== 'vivo');
    const dolarAnterior = usd !== null && usd !== 0 && dolar !== null && mep.estado !== 'vivo';
    texto('integral-estado', total === null ? 'Resultado sin dato: revisá los faltantes indicados.' : precioAnterior || dolarAnterior ?
      'Usa un último dato guardado de precios o dólar MEP; consultá su estado y hora.' :
      calculadas.length || (usd !== null && usd !== 0) ? 'Recalculado con los precios y el dólar MEP disponibles en esta consulta.' :
      'Cartera sin posiciones y sin efectivo USD: el cálculo no necesita precios actuales.');
  }

  function renderizarVencimientos() {
    const lista = elemento('vencimientos-lista');
    if (!lista) return;
    const vencimientos = posiciones.map(posicion => ({...posicion, dias: diasRestantes(posicion.vencimiento)}))
      .filter(posicion => posicion.dias !== null && posicion.dias <= 60)
      .sort((a, b) => a.vencimiento.localeCompare(b.vencimiento) || String(a.ticker).localeCompare(String(b.ticker)));
    lista.replaceChildren();
    if (!vencimientos.length) {
      const nodo = document.createElement('li');
      nodo.textContent = 'Sin vencimientos informados dentro de los próximos 60 días ni especies vencidas.';
      lista.appendChild(nodo);
    }
    for (const posicion of vencimientos) {
      const nodo = document.createElement('li');
      nodo.className = posicion.dias < 0 ? 'vencida' : 'proximo';
      nodo.textContent = posicion.ticker + ' · ' + dia(posicion.vencimiento) + ' · ' +
        (posicion.dias < 0 ? 'vencida hace ' + plural(Math.abs(posicion.dias)) : posicion.dias === 0 ? 'vence hoy' : (posicion.dias === 1 ? 'falta ' : 'faltan ') + plural(posicion.dias));
      if (posicion.dias < 0 && posicion.estado !== 'vivo') nodo.textContent += '. La fuente puede dejar de cotizar una especie vencida.';
      lista.appendChild(nodo);
    }
  }

  function renderizarAvisos() {
    texto('ultima-consulta', ultimaConsulta === null ? 'Consulta al generar el archivo: ' + hora(datos.generado_en) : 'Última consulta: ' + hora(ultimaConsulta));
    const desactualizada = ultimaExitosa === null || Date.now() - ultimaExitosa > 11 * 60 * 1000;
    const detalle = !habilitada ? 'Vista estática: faltan cantidades o unidades para recalcular. Los precios son los embebidos al generar el archivo.' :
      rondaFallida ? 'No se pudo actualizar ninguna posición en la última ronda. Se muestran los últimos datos disponibles.' :
      desactualizada ? 'Sin una consulta exitosa reciente de posiciones: los datos pueden estar desactualizados.' :
      ultimaConsulta === null ? 'Precios embebidos al generar el archivo: se confirman mediante una nueva consulta.' : '';
    aviso('aviso-datos', detalle);
    const generada = new Date(datos.generado_en);
    aviso('aviso-dia-distinto', !Number.isFinite(generada.getTime()) || fechaLocal(generada) !== fechaLocal(new Date()) ?
      'Este archivo se generó otro día; las posiciones pueden haber cambiado. Generá nuevamente el dashboard.' : '');
    const noVivas = posiciones.filter(posicion => posicion.estado !== 'vivo');
    let parcial = noVivas.length ? noVivas.length + ' de ' + posiciones.length + ' posiciones sin confirmar en vivo. Consultá el estado y la hora de cada fila.' : '';
    if (!mep || positivo(mep.ultimo) === null || mep.estado !== 'vivo') parcial += (parcial ? ' ' : '') + 'Dólar MEP sin confirmar en vivo.';
    aviso('aviso-parcial', parcial);
  }

  function renderizar() {
    if (habilitada) renderizarTotales(posiciones.map(calcular));
    renderizarVencimientos();
    renderizarAvisos();
    mostrarEstadoAlertas();
    mostrarEstadoAvisos();
  }

  async function panel(endpoint) {
    const controlador = new AbortController();
    const temporizador = setTimeout(() => controlador.abort(), 15000);
    try {
      const url = endpoint === 'mep' ? 'https://data912.com/live/mep' : 'https://data912.com/live/' + endpoint;
      const respuesta = await fetch(url, {
        signal: controlador.signal, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer'
      });
      if (!respuesta.ok) return null;
      const filas = await respuesta.json();
      return Array.isArray(filas) ? filas : null;
    } catch (_) {
      return null;
    } finally {
      clearTimeout(temporizador);
    }
  }

  function indexar(filas) {
    const mapa = new Map();
    const repetidos = new Set();
    for (const fila of filas || []) {
      if (!fila || typeof fila !== 'object' || typeof fila.symbol !== 'string') continue;
      if (mapa.has(fila.symbol)) repetidos.add(fila.symbol);
      mapa.set(fila.symbol, fila);
    }
    for (const ticker of repetidos) mapa.delete(ticker);
    return mapa;
  }

  async function actualizar() {
    if (!habilitada || ocupada) return;
    ocupada = true;
    if (boton) boton.disabled = true;
    try {
      const endpoints = [...new Set(posiciones.map(posicion => posicion.endpoint).filter(endpoint => pendientes.has(endpoint)))];
      const respuestas = await Promise.all([...endpoints, 'mep'].map(async endpoint => [endpoint, await panel(endpoint)]));
      const porEndpoint = new Map(respuestas);
      const tablas = new Map(endpoints.map(endpoint => [endpoint, indexar(porEndpoint.get(endpoint))]));
      const ahora = new Date().toISOString();
      let exitos = 0;
      for (const posicion of posiciones) {
        const tabla = tablas.get(posicion.endpoint);
        const fila = tabla ? tabla.get(posicion.ticker) : null;
        const ultimo = fila ? positivo(fila.c) : null;
        if (ultimo !== null) {
          Object.assign(posicion, {ultimo, bid: positivo(fila.px_bid), ask: positivo(fila.px_ask), pct_dia: finito(fila.pct_change), estado: 'vivo', consultado_en: ahora});
          exitos += 1;
        } else {
          posicion.estado = positivo(posicion.ultimo) === null ? 'sin_dato' : 'cache';
          if (posicion.estado === 'sin_dato') posicion.consultado_en = ahora;
        }
      }
      const referencias = (porEndpoint.get('mep') || []).filter(fila => fila && typeof fila === 'object' && fila.ticker === 'AL30');
      const marca = referencias.length === 1 ? positivo(referencias[0].mark) : null;
      if (marca !== null) mep = {ultimo: marca, estado: 'vivo', consultado_en: ahora};
      else if (mep && positivo(mep.ultimo) !== null) mep.estado = 'cache';
      else mep = null;
      ultimaConsulta = ahora;
      rondaFallida = posiciones.length ? exitos === 0 : marca === null;
      if (exitos || (!posiciones.length && marca !== null)) ultimaExitosa = Date.now();
    } catch (_) {
      rondaFallida = true;
      ultimaConsulta = new Date().toISOString();
      for (const posicion of posiciones) posicion.estado = positivo(posicion.ultimo) === null ? 'sin_dato' : 'cache';
      if (mep) mep.estado = 'cache';
    } finally {
      ocupada = false;
      if (boton) boton.disabled = !habilitada;
      renderizar();
      evaluarAlertas();
    }
  }

  if (boton) {
    boton.disabled = !habilitada;
    boton.addEventListener('click', actualizar);
  }
  if (botonAvisos) botonAvisos.addEventListener('click', activarAvisos);
  mostrarEstadoAvisos();
  renderizar();
  if (habilitada) {
    actualizar();
    setInterval(() => { renderizar(); actualizar(); }, 300000);
  }
})();
"""
