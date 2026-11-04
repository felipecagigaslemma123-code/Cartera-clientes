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
    const desactualizada = ultimaExitosa === null || Date.now() - ultimaExitosa > 5 * 60 * 1000;
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
      rondaFallida = exitos === 0;
      if (exitos) ultimaExitosa = Date.now();
    } catch (_) {
      rondaFallida = true;
      ultimaConsulta = new Date().toISOString();
      for (const posicion of posiciones) posicion.estado = positivo(posicion.ultimo) === null ? 'sin_dato' : 'cache';
      if (mep) mep.estado = 'cache';
    } finally {
      ocupada = false;
      if (boton) boton.disabled = !habilitada;
      renderizar();
    }
  }

  if (boton) {
    boton.disabled = !habilitada;
    boton.addEventListener('click', actualizar);
  }
  renderizar();
  if (habilitada) {
    actualizar();
    setInterval(() => { renderizar(); actualizar(); }, 60000);
  }
})();
"""
