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

  // XLSX local: las cifras salen del estado que ya usa la pantalla. Los textos
  // son inlineStr, por lo que ningún contenido se convierte en una fórmula.
  function xmlExcel(valor) {
    return String(valor).replace(/[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/gu, '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&apos;').replace(/\r/g, '&#13;');
  }

  function fechaDescargaExcel(fecha) {
    const partes = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
      timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(fecha).map(parte => [parte.type, parte.value]));
    return {texto: partes.day + '/' + partes.month + '/' + partes.year + ' ' + partes.hour + ':' + partes.minute,
      nombre: partes.year + '-' + partes.month + '-' + partes.day + '-' + partes.hour + partes.minute};
  }

  const textoExcel = valor => ({tipo: 'texto', valor: valor === null || valor === undefined ? 'sin dato' : String(valor)});
  const numeroExcel = (valor, estilo = 2, faltante = 'sin dato') => finito(valor) === null ? textoExcel(faltante) : {tipo: 'numero', valor, estilo};
  function fechaExcel(valor, opcional = false) {
    if (opcional && (valor === null || valor === undefined || valor === '')) return null;
    const dias = diaFecha(valor);
    if (dias === null) return textoExcel('sin dato');
    // Excel conserva el día ficticio 29/02/1900 en su calendario de números de serie.
    return {tipo: 'numero', valor: dias + 25569 - (valor < '1900-03-01' ? 1 : 0), estilo: 5};
  }

  function posicionesExcel() {
    return posiciones.map(posicion => {
      const calculada = calcular(posicion);
      if (!habilitada) {
        // Una vista estática también puede carecer de cantidades o unidades; no
        // se pierden por eso los valores ya calculados y embebidos en el HTML.
        if (Object.prototype.hasOwnProperty.call(posicion, 'valuacion')) calculada.valor = finito(posicion.valuacion);
        if (Object.prototype.hasOwnProperty.call(posicion, 'resultado')) calculada.compra = finito(posicion.resultado);
      }
      return calculada;
    });
  }

  function hojasExcel(generado) {
    const calculadas = posicionesExcel();
    const conocidas = calculadas.filter(posicion => posicion.valor !== null);
    const total = suma(conocidas.map(posicion => posicion.valor));
    const dolar = mep ? positivo(mep.ultimo) : null;
    const comparables = conocidas.filter(posicion => posicion.costo !== null && posicion.compra !== null);
    const costo = suma(comparables.map(posicion => posicion.costo));
    const comparable = suma(comparables.map(posicion => posicion.valor));
    const resultado = comparable !== null && costo !== null ? seguro(comparable - costo) : null;
    const resumen = [
      ['Concepto', 'Valor'], ['Cliente', datos.cliente && typeof datos.cliente.slug === 'string' ? datos.cliente.slug : ''],
      ['Generado', generado.texto], ['Última consulta', ultimaConsulta === null ? 'sin dato' : hora(ultimaConsulta)],
      ['Dólar MEP', numeroExcel(dolar)], ['Valuación conocida ARS', numeroExcel(total)],
      ['Valuación conocida USD', numeroExcel(total !== null && dolar !== null ? seguro(total / dolar) : null)],
      ['Posiciones sin precio', numeroExcel(calculadas.length - conocidas.length, 3)],
      ['Posiciones sin confirmar en vivo', numeroExcel(calculadas.filter(posicion => posicion.estado !== 'vivo').length, 3)],
      ['Resultado desde la compra ARS', numeroExcel(resultado)]
    ];
    const filas = [[
      'Ticker', 'Especie', 'Tipo', 'Cantidad', 'Último', 'Valuación ARS', 'Peso', 'Variación del día', 'Costo ARS',
      'Origen del costo', 'Resultado ARS', 'Resultado %', 'Take profit', 'Stop loss', 'Vencimiento',
      'Estado del precio', 'Hora de consulta'
    ]];
    for (const posicion of calculadas) {
      let resultadoPct = posicion.compra !== null && posicion.costo !== null ? seguro(posicion.compra / posicion.costo) : null;
      if (!habilitada && Object.prototype.hasOwnProperty.call(posicion, 'resultado_pct')) resultadoPct = finito(posicion.resultado_pct);
      filas.push([
        textoExcel(posicion.ticker), textoExcel(posicion.especie || 'sin dato'), textoExcel(posicion.tipo || 'sin dato'),
        numeroExcel(posicion.cantidad, 3), numeroExcel(positivo(posicion.ultimo)), numeroExcel(posicion.valor),
        numeroExcel(posicion.valor !== null && positivo(total) !== null ? seguro(posicion.valor / total) : null, 4),
        numeroExcel(finito(posicion.pct_dia) === null ? null : seguro(posicion.pct_dia / 100), 4),
        numeroExcel(posicion.costo, 2, 'falta estimar'), textoExcel(origen(posicion.estado_costo)),
        numeroExcel(posicion.compra, 2, posicion.costo === null ? 'falta estimar' : 'sin dato'),
        numeroExcel(resultadoPct, 4, posicion.costo === null ? 'falta estimar' : 'sin dato'),
        positivo(posicion.take_profit) === null ? null : numeroExcel(posicion.take_profit),
        positivo(posicion.stop_loss) === null ? null : numeroExcel(posicion.stop_loss),
        fechaExcel(posicion.vencimiento, true), textoExcel(estado(posicion.estado)), textoExcel(hora(posicion.consultado_en))
      ]);
    }
    const hojas = [{nombre: 'Resumen', filas: resumen}, {nombre: 'Posiciones', filas}];
    if (datos.historial && typeof datos.historial === 'object') {
      const historial = datos.historial;
      resumen.push(['Total conocido realizado ARS', numeroExcel(historial.total_conocido)],
        ['Realizado de extracto ARS', numeroExcel(historial.realizado_extracto)],
        ['Realizado con estimaciones ARS', numeroExcel(historial.realizado_estimado)]);
      const ventas = [['Ticker', 'Fecha', 'Clase', 'Cantidad', 'Sin lote', 'Importe ARS', 'Costo ARS', 'Origen del costo', 'Resultado ARS']];
      for (const venta of historial.realizados || []) {
        ventas.push([textoExcel(venta.ticker), fechaExcel(venta.fecha), textoExcel(venta.clase), numeroExcel(venta.cantidad, 3),
          numeroExcel(venta.cantidad_sin_lote, 3), numeroExcel(venta.importe_ars), numeroExcel(venta.costo_ars),
          textoExcel(venta.origen_costo === 'incompleto' ? 'incompleto (sin dato)' : origen(venta.origen_costo)), numeroExcel(venta.resultado_ars)]);
      }
      const etiquetas = new Map([
        ['dividendo', 'Dividendos'], ['retencion', 'Retenciones'], ['renta', 'Rentas'], ['caucion_colocada', 'Caución colocada'],
        ['caucion_tomada', 'Caución tomada'], ['fci', 'FCI'], ['gastos', 'Gastos'], ['compensacion', 'Compensaciones por error operativo']
      ]);
      const ingresos = [['Concepto', 'ARS', 'USD', 'Equivalente ARS']];
      const ingreso = (etiqueta, valores) => [textoExcel(etiqueta), ...['ARS', 'USD', 'equivalente_ars'].map(moneda => numeroExcel((valores || {})[moneda]))];
      for (const [clase, valores] of Object.entries(historial.ingresos || {})) ingresos.push(ingreso(etiquetas.get(clase) || clase, valores));
      ingresos.push(ingreso('Aportes (no son ganancia)', historial.aportes), ingreso('Retiros (no son ganancia)', historial.retiros));
      hojas.push({nombre: 'Ventas', filas: ventas}, {nombre: 'Ingresos', filas: ingresos});
    }
    if (Array.isArray(datos.flujo_fondos_excel)) {
      const filasFlujo = datos.flujo_fondos_excel.map(fila => fila.map(celda =>
        celda && celda.tipo === 'fecha' ? fechaExcel(celda.valor) : celda));
      hojas.push({nombre: 'Flujo de fondos', filas: filasFlujo});
    }
    return hojas;
  }

  function columnaExcel(indice) {
    let columna = '';
    while (indice > 0) {
      indice -= 1;
      columna = String.fromCharCode(65 + indice % 26) + columna;
      indice = Math.floor(indice / 26);
    }
    return columna;
  }

  function hojaXmlExcel(filas) {
    const columnas = filas.reduce((maximo, fila) => Math.max(maximo, fila.length), 1);
    const anchos = Array.from({length: columnas}, (_, columna) => {
      const largo = filas.reduce((maximo, fila) => {
        const celda = fila[columna];
        const longitud = celda === null || celda === undefined ? 0 : String(typeof celda === 'object' ? celda.valor : celda).length;
        return Math.max(maximo, longitud);
      }, 0);
      return Math.min(65, Math.max(12, largo + 2));
    });
    const contenido = filas.map((fila, indice) => '<row r="' + (indice + 1) + '">' + fila.map((bruto, columna) => {
      if (bruto === null || bruto === undefined) return '';
      const celda = typeof bruto === 'object' ? bruto : textoExcel(bruto);
      const referencia = columnaExcel(columna + 1) + (indice + 1);
      const estilo = indice === 0 ? 1 : celda.estilo || 0;
      if (celda.tipo === 'numero' && finito(celda.valor) !== null) {
        return '<c r="' + referencia + '" s="' + estilo + '"><v>' + celda.valor + '</v></c>';
      }
      return '<c r="' + referencia + '" s="' + estilo + '" t="inlineStr"><is><t xml:space="preserve">' + xmlExcel(celda.valor) + '</t></is></c>';
    }).join('') + '</row>').join('');
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
      '<dimension ref="A1:' + columnaExcel(columnas) + Math.max(1, filas.length) + '"/>' +
      '<sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/>' +
      '<cols>' + anchos.map((ancho, i) => '<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + ancho + '" customWidth="1"/>').join('') + '</cols>' +
      '<sheetData>' + contenido + '</sheetData></worksheet>';
  }

  function estilosXmlExcel() {
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
      '<numFmts count="4"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="0.###############"/>' +
      '<numFmt numFmtId="166" formatCode="0.00%"/><numFmt numFmtId="167" formatCode="dd/mm/yyyy"/></numFmts>' +
      '<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>' +
      '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
      '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
      '<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
      '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>' +
      [164, 165, 166, 167].map(id => '<xf numFmtId="' + id + '" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>').join('') +
      '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
  }

  function archivosExcel(hojas) {
    const cabecera = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
    const relacion = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/';
    const partes = [
      ['[Content_Types].xml', cabecera + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
        hojas.map((_, i) => '<Override PartName="/xl/worksheets/sheet' + (i + 1) + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join('') + '</Types>'],
      ['_rels/.rels', cabecera + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="' + relacion + 'officeDocument" Target="xl/workbook.xml"/></Relationships>'],
      ['xl/workbook.xml', cabecera + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="' + relacion.slice(0, -1) + '">' +
        '<bookViews><workbookView/></bookViews><sheets>' + hojas.map((hoja, i) => '<sheet name="' + xmlExcel(hoja.nombre) + '" sheetId="' + (i + 1) + '" r:id="rId' + (i + 1) + '"/>').join('') + '</sheets></workbook>'],
      ['xl/_rels/workbook.xml.rels', cabecera + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        hojas.map((_, i) => '<Relationship Id="rId' + (i + 1) + '" Type="' + relacion + 'worksheet" Target="worksheets/sheet' + (i + 1) + '.xml"/>').join('') +
        '<Relationship Id="rId' + (hojas.length + 1) + '" Type="' + relacion + 'styles" Target="styles.xml"/></Relationships>'],
      ['xl/styles.xml', estilosXmlExcel()]
    ];
    hojas.forEach((hoja, i) => partes.push(['xl/worksheets/sheet' + (i + 1) + '.xml', hojaXmlExcel(hoja.filas)]));
    return partes;
  }

  let tablaCrcExcel = null;
  function crc32Excel(bytes) {
    if (tablaCrcExcel === null) {
      tablaCrcExcel = Uint32Array.from({length: 256}, (_, indice) => {
        let valor = indice;
        for (let bit = 0; bit < 8; bit += 1) valor = valor & 1 ? 0xEDB88320 ^ valor >>> 1 : valor >>> 1;
        return valor >>> 0;
      });
    }
    let crc = 0xFFFFFFFF;
    for (const byte of bytes) crc = tablaCrcExcel[(crc ^ byte) & 0xFF] ^ crc >>> 8;
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }

  function zipExcel(archivos) {
    const codificador = new TextEncoder();
    const locales = [];
    const centrales = [];
    let desplazamiento = 0;
    for (const [ruta, contenido] of archivos) {
      const nombre = codificador.encode(ruta);
      const bytes = codificador.encode(contenido);
      if (bytes.length > 0xFFFFFFFF || desplazamiento > 0xFFFFFFFF) throw new Error('Libro demasiado grande');
      const crc = crc32Excel(bytes);
      const local = new Uint8Array(30 + nombre.length);
      const vista = new DataView(local.buffer);
      vista.setUint32(0, 0x04034B50, true); vista.setUint16(4, 20, true); vista.setUint16(6, 0x800, true);
      vista.setUint16(8, 0, true); vista.setUint16(10, 0, true); vista.setUint16(12, 33, true);
      vista.setUint32(14, crc, true); vista.setUint32(18, bytes.length, true); vista.setUint32(22, bytes.length, true);
      vista.setUint16(26, nombre.length, true); local.set(nombre, 30);
      const central = new Uint8Array(46 + nombre.length);
      const directorio = new DataView(central.buffer);
      directorio.setUint32(0, 0x02014B50, true); directorio.setUint16(4, 20, true); directorio.setUint16(6, 20, true);
      directorio.setUint16(8, 0x800, true); directorio.setUint16(10, 0, true); directorio.setUint16(12, 0, true); directorio.setUint16(14, 33, true);
      directorio.setUint32(16, crc, true); directorio.setUint32(20, bytes.length, true); directorio.setUint32(24, bytes.length, true);
      directorio.setUint16(28, nombre.length, true); directorio.setUint32(42, desplazamiento, true); central.set(nombre, 46);
      locales.push(local, bytes); centrales.push(central);
      desplazamiento += local.length + bytes.length;
    }
    const tamanoDirectorio = centrales.reduce((total, parte) => total + parte.length, 0);
    const fin = new Uint8Array(22);
    const vista = new DataView(fin.buffer);
    vista.setUint32(0, 0x06054B50, true); vista.setUint16(8, archivos.length, true); vista.setUint16(10, archivos.length, true);
    vista.setUint32(12, tamanoDirectorio, true); vista.setUint32(16, desplazamiento, true);
    const longitud = desplazamiento + tamanoDirectorio + fin.length;
    if (longitud > 0xFFFFFFFF || archivos.length > 0xFFFF) throw new Error('Libro demasiado grande');
    const salida = new Uint8Array(longitud);
    let posicion = 0;
    for (const parte of [...locales, ...centrales, fin]) { salida.set(parte, posicion); posicion += parte.length; }
    return salida;
  }

  function descargarExcel() {
    let url = null;
    let enlace = null;
    try {
      const generado = fechaDescargaExcel(new Date());
      const bytes = zipExcel(archivosExcel(hojasExcel(generado)));
      const blob = new Blob([bytes], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
      url = URL.createObjectURL(blob);
      enlace = document.createElement('a');
      enlace.href = url;
      const slug = datos.cliente && typeof datos.cliente.slug === 'string' ? datos.cliente.slug : '';
      enlace.download = 'cartera-' + slug.replace(/[\\/:*?"<>|\u0000-\u001F]/g, '_') + '-' + generado.nombre + '.xlsx';
      enlace.hidden = true;
      if (document.body) document.body.appendChild(enlace);
      enlace.click();
      const liberar = url;
      setTimeout(() => { try { URL.revokeObjectURL(liberar); } catch (_) { /* La descarga ya se inició. */ } }, 1000);
      url = null;
      texto('excel-estado', 'Excel descargado · ' + generado.texto + '.');
    } catch (_) {
      texto('excel-estado', 'No se pudo generar el Excel. La página sigue funcionando.');
    } finally {
      if (url !== null) { try { URL.revokeObjectURL(url); } catch (_) { /* Sin efectos sobre la página. */ } }
      try { if (enlace && typeof enlace.remove === 'function') enlace.remove(); } catch (_) { /* La limpieza no interrumpe el tablero. */ }
    }
  }

  function actualizarDiasLetras() {
    if (!datos.letras || !Array.isArray(datos.letras.posiciones)) return;
    const partes = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(new Date()).map(parte => [parte.type, parte.value]));
    const hoy = [partes.year, partes.month, partes.day].join('-');
    const diaHoy = diaFecha(hoy);
    if (diaHoy === null) return;
    for (const [indice, posicion] of datos.letras.posiciones.entries()) {
      const vencimiento = diaFecha(posicion.vencimiento);
      const dias = vencimiento === null ? null : vencimiento - diaHoy;
      texto('letras-dias-' + indice, dias === null ? 'sin dato; falta vencimiento' :
        dias < 0 ? 'Vencida hace ' + plural(-dias) + '; cobro sin confirmar' :
        dias === 0 ? '0 días · vence hoy' : plural(dias));
    }
    texto('letras-estado', 'Días corridos al ' + dia(hoy) + ', hora de Argentina. El contador se actualiza con la página abierta.');
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
  const botonExcel = elemento('descargar-excel');
  if (botonExcel) botonExcel.addEventListener('click', descargarExcel);
  mostrarEstadoAvisos();
  renderizar();
  if (datos.letras && elemento('letras-panel')) {
    actualizarDiasLetras();
    setInterval(actualizarDiasLetras, 60000);
  }
  if (habilitada) {
    actualizar();
    setInterval(() => { renderizar(); actualizar(); }, 300000);
  }
})();
"""
