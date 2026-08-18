// $("id") -> atajo para document.getElementById("id"). Busca un elemento de
// la página por su id y lo devuelve para modificarlo o leerlo.
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// ESTADO EN MEMORIA DE LA INTERFAZ
// ---------------------------------------------------------------------------
// estado      -> toda la información que llegó del servidor (/api/estado):
//                config, partido, nómina, espera, cupos, multas, jugadores...
// seleccionado-> el jugador elegido en el autocompletado (para anotar)
// sugerencias -> los resultados visibles del autocompletado «voy»
// indiceActivo-> cuál sugerencia está resaltada (flechas arriba/abajo)
// editandoConfig / editandoPartidoId / editandoMotivoId / editandoMultaId
//              -> guardan si estamos editando algo, y qué id (para guardar)
// partidoEnVista -> si estamos viendo la nómina de OTRO partido guardado
let estado = null;
let seleccionado = null;
let sugerencias = [];
let indiceActivo = -1;
let editandoConfig = false;
let editandoPartidoId = null;
let editandoMotivoId = null;
let partidoEnVista = null;

// ESTADOS -> etiquetas en pantalla para cada estado que puede tener un partido.
const ESTADOS = {
  abierta: "NÓMINA ABIERTA",
  cerrada: "NÓMINA CERRADA",
  en_juego: "EN JUEGO",
  finalizada: "FINALIZADO",
  cancelada: "CANCELADO",
};

// Envía solicitudes a la API del backend y convierte la respuesta JSON en un objeto JavaScript.
async function api(ruta, opciones = {}) {
  const res = await fetch(ruta, {
    headers: { "Content-Type": "application/json" },
    ...opciones,
    body: opciones.body ? JSON.stringify(opciones.body) : undefined,
  });
  const datos = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(datos.error || "Error inesperado");
  return datos;
}

// ------------------------------------------------------- utilidades y pintado
// pesos(1234) -> "$1.234". Formatea un número como dinero colombiano.
// esc("a<b>") -> "a&lt;b&gt;". Escapa el texto para poder mostrarlo seguro en HTML.
// emoji("F")  -> 🌹 (mujer) u ⚽ (hombre). Mismo criterio que el servidor.
const pesos = (n) => "$" + Number(n || 0).toLocaleString("es-CO");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const emoji = (g) => (g === "F" ? "🌹" : "⚽");

// pintarReglamento(texto) -> convierte el texto de las reglas/multas en HTML
// con formato: resalta horas, montos en $, cantidades (2 mujeres, 15 días...).
// Ese texto se guarda simple en la base, pero se muestra bonito en pantalla.
function pintarReglamento(texto) {
  const patron = /(\b\d{1,2}:\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)\b)|(\b\d{1,2})\s*(am|pm)\b|(\$\s?\d[\d]*(?:\.\d{3})*)|(\b\d{1,3}(?:\.\d{3})+\s*(?:pesos|peso)?)\b|(\b\d+)\s+(mujeres|hombres|mujer|hombre)\b|(\b\d+)\s+d[ií]as?\b/gi;
  return String(texto || "").split("\n").map((linea, n) => {
    let t = esc(linea.trim()).replace(/^\d+[.)]?\s*/, "");
    if (!t) return "";
    const resaltado = t.replace(patron, (m, hora, horaNum, sufijo, monto, miles, genNum, gen, diasNum) => {
      if (hora) return "<b>" + hora + "</b>";
      if (horaNum) return "<b>" + horaNum + "</b>" + (sufijo || "");
      if (monto) return '<span class="valor">' + monto + "</span>";
      if (miles) return '<span class="valor">' + miles + "</span>";
      if (genNum) return "<b>" + genNum + "</b> " + gen;
      if (diasNum) return "<b>" + diasNum + "</b> días";
      return m;
    });
    return `<div class="regla"><span class="num">${n + 1}</span><span>${resaltado}</span></div>`;
  }).join("");
}

// aviso(texto, error) -> muestra un mensaje temporal debajo del buscador.
// Con "error" = true se pinta en rojo. El mensaje se oculta solo a los 5
// segundos (no debe quedar pegado en pantalla).
let avisoTimer = null;
function aviso(texto, error = false) {
  const el = $("aviso");
  el.textContent = texto || "";
  el.classList.toggle("error", error);
  el.classList.toggle("oculto", !texto);
  clearTimeout(avisoTimer);
  if (texto) {
    avisoTimer = setTimeout(() => {
      el.textContent = "";
      el.classList.add("oculto");
    }, 5000);
  }
}

// cargar(id) -> pide al servidor el estado completo (o el de un partido con id)
// y lo guarda en "estado"; luego repinta toda la pantalla con pintar().
async function cargar(id = null) {
  estado = await api("/api/estado" + (id ? `?id=${id}` : ""));
  pintar();
}

// ------------------------------------------------------------------ pintado
// pintar() -> recibe el estado del servidor (guardado en "estado") y actualiza
// los paneles, tablas y textos visibles en la página.
function pintar() {
  const dir = estado.rol === "directiva";
  document.querySelectorAll(".solo-directiva").forEach((el) => {
    if (el.classList.contains("tab")) return;
    el.classList.toggle("oculto", !dir);
  });
  $("card-motivos-personalizados").classList.add("oculto");
  $("card-cancha-nueva").classList.add("oculto");
  // El historial de partidos siempre arranca oculto: solo se ve al pulsar "Ver".
  $("card-historial").classList.add("oculto");
  $("btn-ver-historial").textContent = "Ver";
  // El formulario de partido solo aparece al pulsar "Crear partido".
  $("card-crear-partido").classList.add("oculto");
  // El formulario de registro de multa solo aparece al pulsar "Registrar multa".
  $("card-registrar-multa").classList.add("oculto");
  // El formulario de jugador solo aparece al pulsar "Registrar jugador".
  $("card-registrar-jugador").classList.add("oculto");
  $("btn-login").classList.toggle("oculto", dir || !estado.requiere_pin);
  $("btn-logout").classList.toggle("oculto", !dir || !estado.requiere_pin);

  const c = estado.config;
  const p = estado.partido;
  $("titulo-grupo").textContent = c.nombre_grupo;
  $("d-fecha").textContent = p ? p.fecha_es : "—";
  $("d-hora").textContent = p ? p.hora_es : "—";
  $("d-cancha").textContent = p ? p.cancha : "—";

  pintarNomina();
  pintarPartidos();
  pintarCanchas();
  pintarMultas();
  pintarJugadores();
  pintarConfig();

  $("texto").textContent = estado.texto;
  $("v-reglas").innerHTML = pintarReglamento(c.reglas);
  $("v-reglamento").innerHTML = pintarReglamento(c.reglamento_multas);
}

// pintarNomina() -> dibuja las dos columnas (nómina y lista de espera),
// divididas por género, con los cupos usados y las barras de progreso.
function pintarNomina() {
  const dir = estado.rol === "directiva";
  // Un partido guardado en el historial es de solo lectura: no se anota gente
  // ni se mueve/quita a nadie hasta abrir su nómina desde Partidos.
  const guardado = estado.partido && estado.partido.estado === "guardado";
  const editable = dir && !guardado;
  $("card-anotar").classList.toggle("oculto", guardado || !dir);
  $("nota-guardado").classList.toggle("oculto", !guardado);
  const { mujeres, hombres, usadas_f: uf, usadas_m: um } = estado.cupos;
  const total = mujeres + hombres;
  $("c-mujeres").textContent = `${uf}/${mujeres}`;
  $("c-hombres").textContent = `${um}/${hombres}`;
  $("b-mujeres").style.width = `${mujeres ? (uf / mujeres) * 100 : 0}%`;
  $("b-hombres").style.width = `${hombres ? (um / hombres) * 100 : 0}%`;
  $("c-total").textContent = `(${estado.nomina.length}/${total})`;

  const nominaF = estado.nomina.filter((i) => i.genero === "F");
  const nominaM = estado.nomina.filter((i) => i.genero === "M");
  const esperaF = estado.espera.filter((i) => i.genero === "F");
  const esperaM = estado.espera.filter((i) => i.genero === "M");

  $("lista-nomina").innerHTML = `
    <div class="grupo-genero femenino">
      <div class="encabezado-genero">🌹 Mujeres <span>${nominaF.length}/${mujeres}</span></div>
      ${nominaF.length ? nominaF.map((i, n) => filaJugador(i, n + 1, editable, "espera")).join("") : '<p class="vacio">Sin mujeres en la nómina.</p>'}
    </div>
    <div class="grupo-genero masculino">
      <div class="encabezado-genero">⚽ Hombres <span>${nominaM.length}/${hombres}</span></div>
      ${nominaM.length ? nominaM.map((i, n) => filaJugador(i, n + 1, editable, "espera")).join("") : '<p class="vacio">Sin hombres en la nómina.</p>'}
    </div>`;

  $("lista-espera").innerHTML = `
    <div class="grupo-genero femenino">
      <div class="encabezado-genero">🌹 Mujeres <span>${esperaF.length}</span></div>
      ${esperaF.length ? esperaF.map((i, n) => filaJugador(i, n + 1, editable, "nomina")).join("") : '<p class="vacio">Sin mujeres en espera.</p>'}
    </div>
    <div class="grupo-genero masculino">
      <div class="encabezado-genero">⚽ Hombres <span>${esperaM.length}</span></div>
      ${esperaM.length ? esperaM.map((i, n) => filaJugador(i, n + 1, editable, "nomina")).join("") : '<p class="vacio">Sin hombres en espera.</p>'}
    </div>`;

  $("hint-corte").textContent = estado.corte_invitados.texto
    + (estado.corte_invitados.permite
      ? " Recuerda: el invitado requiere nombre de quien lo anota y queda a decisión de la directiva."
      : ` Corte: ${estado.corte_invitados.fecha} a las ${estado.corte_invitados.hora}.`);
  $("btn-cambiar-cupos").classList.toggle("oculto", !dir);
}

// filaJugador(i, n, dir, destino) -> el HTML de una fila de la nómina/espera.
// "i" es el registro anotado, "n" su número, "dir" si es directiva (muestra
// botones de mover/quitar) y "destino" hacia qué lista lleva el botón.
function filaJugador(i, n, dir, destino) {
  return `<div class="fila">
    <span class="num">${n}.</span>
    <span class="nombre">${emoji(i.genero)} ${esc(i.nombre)}
      ${i.invitado_por ? `<small>(${esc(i.invitado_por)})</small>` : ""}
      ${i.miembro ? "" : '<span class="etq gris">invitad@</span>'}</span>
    ${dir ? `<button class="btn gris chico" data-mover="${i.id}" data-lista="${destino}">${
      destino === "espera" ? "→ espera" : "→ nómina"}</button>
      <button class="icono" data-quitar="${i.id}" title="Quitar">🗑</button>` : ""}
  </div>`;
}

// pintarPartidos() -> muestra la lista de partidos guardados, con sus estados
// "en uso" / "viendo" y botones para usar, editar o borrar cada uno.
function pintarPartidos() {
  const dir = estado.rol === "directiva";
  const activoId = estado.partido_activo_id;
  const vistaId = estado.partido_vista_id;
  $("c-partidos").textContent = `(${estado.partidos.length})`;
  $("lista-partidos").innerHTML = estado.partidos.map((p) => `
    <div class="tarjeta">
      <div class="encabezado-fila">
        <div>
          <b>${esc(p.fecha_es)} · ${esc(p.hora_es)}</b>
          <p class="detalle">${esc(p.cancha)} · ${p.en_nomina} en nómina · ${p.en_espera} en espera</p>
        </div>
        <div style="text-align:right">
          ${String(p.id) === String(activoId) ? '<span class="etq verde">en uso</span>' : ""}
          ${String(p.id) === String(vistaId) && String(p.id) !== String(activoId)
            ? '<span class="etq morada">viendo</span>' : ""}
          ${dir ? `
            <button class="btn claro chico" data-usar-partido="${p.id}">Usar</button>
            <button class="icono" data-editar-partido="${p.id}" title="Editar">✏️</button>
            <button class="icono" data-guardar-partido="${p.id}" title="Guardar en historial">💾</button>
            <button class="icono" data-borrar-partido="${p.id}" title="Borrar">🗑</button>`
            : `<button class="btn claro chico" data-ver-partido="${p.id}">Ver nómina</button>`}
        </div>
      </div>
    </div>`).join("");

  pintarHistorial();
}

// pintarHistorial() -> dibuja el historial de partidos guardados (los que la
// directiva archivó con "Guardar"), ordenado del más antiguo al más reciente,
// de 5 en 5 con paginación. Cada entrada tiene "Ver nómina" y "Re abrir nómina".
const HISTORIAL_POR_PAGINA = 5;
let historialPagina = 1;
function pintarHistorial() {
  const h = estado.historial || [];
  const totalPaginas = Math.max(1, Math.ceil(h.length / HISTORIAL_POR_PAGINA));
  historialPagina = Math.max(1, Math.min(historialPagina, totalPaginas));
  const desde = (historialPagina - 1) * HISTORIAL_POR_PAGINA;
  const pagina = h.slice(desde, desde + HISTORIAL_POR_PAGINA);

  const contenido = pagina.length ? pagina.map((p) => `
    <div class="fila">
      <span class="nombre"><b>${esc(p.fecha_es)} · ${esc(p.hora_es)}</b>
        <span class="detalle">${esc(p.cancha)} · ${p.en_nomina} en nómina · ${p.en_espera} en espera</span></span>
      <button class="btn claro chico" data-ver-partido="${p.id}">Ver nómina</button>
      <button class="btn claro chico" data-abrir-nomina="${p.id}">Re abrir nómina</button>
    </div>`).join("")
    : '<p class="vacio">Aún no hay partidos en el historial. Guarda un partido desde la lista de arriba para archivarlo aquí.</p>';

  const controles = h.length > HISTORIAL_POR_PAGINA ? `
    <div class="acciones paginacion">
      <button class="btn claro chico" data-hist-prev="1" ${historialPagina <= 1 ? "disabled" : ""}>‹ Anterior</button>
      <span>Página ${historialPagina} de ${totalPaginas}</span>
      <button class="btn claro chico" data-hist-next="1" ${historialPagina >= totalPaginas ? "disabled" : ""}>Siguiente ›</button>
    </div>` : "";

  $("historial-partidos").innerHTML = contenido + controles;
}

// pintarCanchas() -> dibuja la lista de canchas guardadas (con botones para
// editar y borrar), dentro del panel que se abre con "Agregar cancha". El
// autocompletado de los inputs usa estado.canchas en memoria.
function pintarCanchas() {
  const canchas = estado.canchas || [];
  $("lista-canchas").innerHTML = canchas.length ? canchas.map((c) => `
    <div class="fila">
      <span class="nombre">🏟 ${esc(c.nombre)}</span>
      <button class="icono" data-editar-cancha="${c.id}" title="Editar cancha">✏️</button>
      <button class="icono" data-borrar-cancha="${c.id}" title="Borrar cancha">🗑</button>
    </div>`).join("") : '<p class="vacio">Aún no hay canchas guardadas.</p>';
}

// autocompletarCancha(idInput, idCont) -> hace que escribir en el campo de cancha
// muestre sugerencias de las canchas guardadas (de la base de datos).
function autocompletarCancha(idInput, idCont) {
  const input = $(idInput);
  const caja = $(idCont);
  input.addEventListener("input", () => {
    if (!input.value.trim()) { caja.classList.add("oculto"); return; }
    const texto = input.value.toLowerCase();
    const resultado = (estado.canchas || [])
      .filter((c) => c.nombre.toLowerCase().includes(texto))
      .slice(0, 6);
    caja.innerHTML = resultado.map((c) => `
      <div data-elegir-cancha="${esc(c.nombre)}"><span>🏟 ${esc(c.nombre)}</span></div>`).join("");
    caja.classList.toggle("oculto", !resultado.length);
  });
  input.addEventListener("blur", () => setTimeout(() => caja.classList.add("oculto"), 150));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") caja.classList.add("oculto");
  });
  caja.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const opcion = e.target.closest("div[data-elegir-cancha]");
    if (!opcion) return;
    input.value = opcion.dataset.elegirCancha;
    caja.classList.add("oculto");
  });
}
autocompletarCancha("n-cancha", "n-cancha-sugerencias");
autocompletarCancha("p-cancha", "p-cancha-sugerencias");

// pintarMultas() -> dibuja el resumen (deuda total, vencidas), los motivos de
// multa y las tarjetas de multas, separando activos de eliminados del grupo.
function pintarMultas() {
  const dir = estado.rol === "directiva";
  $("c-deuda").textContent = pesos(estado.resumen_multas.deuda);
  $("c-vencidas").textContent = estado.resumen_multas.vencidas;

  $("m-motivo-comun").innerHTML = '<option value="">— Elegir motivo común —</option>'
    + estado.motivos_multa.map((m) =>
      `<option value="${m.valor}" data-texto="${esc(m.texto)}">${esc(motivoCorto(m.texto))} (${pesos(m.valor)})</option>`).join("");

  const motivos = estado.motivos_multa;
  $("lista-motivos").innerHTML = motivos.length ? motivos.map((m) => `
    <div class="fila">
      <span class="nombre">${esc(m.texto)} <span class="etq naranja">${pesos(m.valor)}</span></span>
      <button class="icono" data-editar-motivo="${m.id}" title="Editar motivo">✏️</button>
      <button class="icono" data-borrar-motivo="${m.id}" title="Borrar motivo">🗑</button>
    </div>`).join("") : '<p class="vacio">Sin motivos de multa. Agrega uno aquí arriba.</p>';

  const activas = estado.multas.filter((m) => !m.expulsado);
  const expulsados = estado.multas.filter((m) => m.expulsado);

  $("lista-multas").innerHTML = `
    <h2 class="titulo-seccion">📋 LISTADO DE MULTAS <small>(${activas.length})</small></h2>
    <div class="lista-tarjetas">${activas.length ? activas.map((m) => tarjetaMulta(m, dir)).join("") : '<div class="tarjeta"><p class="vacio">Sin multas registradas.</p></div>'}</div>
    <h2 class="titulo-seccion">🚫 ELIMINADOS POR NO PAGAR MULTAS <small>(${expulsados.length})</small></h2>
    <div class="lista-tarjetas">${expulsados.length ? expulsados.map((m) => tarjetaMulta(m, dir)).join("") : '<div class="tarjeta"><p class="vacio">Sin eliminados por no pagar multas.</p></div>'}</div>`;
}

// motivoCorto("Llegó tarde (regla 4)") -> "Llegó tarde". Quita los paréntesis
// y junta los espacios, para que el texto del motivo se vea limpio.
function motivoCorto(motivo) {
  return String(motivo || "")
    .replace(/\s*\([^)]*\)\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// tarjetaMulta(m, dir) -> el HTML de una tarjeta de multa con su estado
// (pagada/vencida/pendiente), datos y botones de acción para la directiva.
function tarjetaMulta(m, dir) {
  const vencidaPendiente = m.estado === "pendiente" && m.vencida;
  const acciones = dir ? `
    <div style="text-align:right">
      ${!m.expulsado && vencidaPendiente ? `
        <button class="btn rojo chico" data-sacar-grupo="${m.participante_id}" title="Saca del grupo y pasa sus multas a Eliminados">🚫 Sacar del grupo</button>` : ""}
      ${m.expulsado ? `
        <button class="btn claro chico" data-reintegrar="${m.participante_id}" title="Vuelve a integrar al grupo">🔓 Reintegrar</button>` : ""}
      ${m.estado === "pendiente" ? `
        <button class="btn claro chico" data-abonar="${m.id}">Abonar</button>
        <button class="btn verde chico" data-pagar="${m.id}">Pagar</button>` : ""}
      <button class="icono" data-editar-multa="${m.id}" title="Editar multa">✏️</button>
      <button class="icono" data-borrar-multa="${m.id}" title="Borrar">🗑</button>
    </div>` : "";
  return `
    <div class="tarjeta">
      <div class="encabezado-fila">
        <div>
          <b>${esc(m.nombre)} ${emoji(m.genero)}</b>${m.estado === "pagada" ? ' <span class="etq verde">pagada</span>'
            : m.vencida ? ' <span class="etq roja">vencida</span>'
            : ' <span class="etq naranja">pendiente</span>'}
          <p class="dato-multa"><span>Motivo:</span>${esc(motivoCorto(m.motivo))}</p>
          <p class="dato-multa"><span>Fecha:</span>${esc(m.fecha_es)}</p>
          <p class="dato-multa"><span>Valor:</span>${pesos(m.valor)}</p>
          <p class="dato-multa"><span>Plazo:</span>${esc(m.plazo_es)}</p>
          ${m.abono ? `<p class="dato-multa"><span>Abonado:</span>${pesos(m.abono)}</p>` : ""}
          <p class="dato-multa saldo"><span>Saldo:</span><b>${pesos(m.saldo)}</b></p>
        </div>
        ${acciones}
      </div>
    </div>`;
}

// pintarJugadores() -> dibuja la lista de jugadores con su estado (activo,
// expulsado, invitad@, deuda) y botones de editar para la directiva.
// Se muestra de 10 en 10, con paginación como el historial de partidos.
const JUGADORES_POR_PAGINA = 10;
let jugadoresPagina = 1;
function pintarJugadores() {
  const dir = estado.rol === "directiva";
  $("c-jugadores").textContent = `(${estado.jugadores.length})`;
  const totalPaginas = Math.max(1, Math.ceil(estado.jugadores.length / JUGADORES_POR_PAGINA));
  jugadoresPagina = Math.max(1, Math.min(jugadoresPagina, totalPaginas));
  const desde = (jugadoresPagina - 1) * JUGADORES_POR_PAGINA;
  const pagina = estado.jugadores.slice(desde, desde + JUGADORES_POR_PAGINA);
  $("lista-jugadores").innerHTML = pagina.map((j) => `
    <div class="fila" data-jugador="${j.id}">
      <span class="nombre">${emoji(j.genero)} ${esc(j.nombre)}
        ${j.activo ? "" : '<span class="etq gris">inactivo</span>'}
        ${j.expulsado ? '<span class="etq roja">expulsado</span>' : ""}
        ${j.miembro ? "" : '<span class="etq gris">invitad@</span>'}
        ${j.deuda ? `<span class="etq naranja">debe ${pesos(j.deuda)}</span>` : ""}</span>
      ${dir ? `
        <button class="icono" data-editar-jugador="${j.id}" title="Editar nombre">✏️</button>
        <button class="icono" data-activo="${j.id}" data-valor="${j.activo ? 0 : 1}"
          title="${j.activo ? "Inactivar" : "Activar"}">${j.activo ? "🚫" : "✔️"}</button>
        <button class="icono" data-expulsado="${j.id}" data-valor="${j.expulsado ? 0 : 1}"
          title="${j.expulsado ? "Readmitir" : "Expulsar por multas"}">${j.expulsado ? "🔓" : "🔒"}</button>
<button class="icono" data-borrar-jugador="${j.id}" title="Borrar">🗑</button>` : ""}
      </div>`).join("")
    + (estado.jugadores.length > JUGADORES_POR_PAGINA ? `
    <div class="acciones paginacion">
      <button class="btn claro chico" data-jug-prev="1" ${jugadoresPagina <= 1 ? "disabled" : ""}>‹ Anterior</button>
      <span>Página ${jugadoresPagina} de ${totalPaginas}</span>
      <button class="btn claro chico" data-jug-next="1" ${jugadoresPagina >= totalPaginas ? "disabled" : ""}>Siguiente ›</button>
    </div>` : "");
}

// ------------------------------------------------------- buscar jugador
// Input autocompletable bajo "JUGADORES DEL GRUPO": sugiere jugadores de la
// base y, al elegir uno, baja a su fila y la resalta en la lista.
let jBuscarSugeridas = [];
let jBuscarActivo = -1;
let jBuscarTemporizador = null;

function jBuscarSugerencias() {
  const q = normalizar($("j-buscar").value);
  const lista = estado.jugadores.filter((j) => j.activo);
  if (!q) {
    jBuscarSugeridas = [];
  } else {
    const empieza = lista.filter((j) => normalizar(j.nombre).startsWith(q));
    const contiene = lista.filter((j) =>
      normalizar(j.nombre).includes(q) && !empieza.includes(j));
    jBuscarSugeridas = empieza.concat(contiene).slice(0, 10);
  }
  jBuscarActivo = -1;
  pintarSugerenciasBuscarJugador();
}

function pintarSugerenciasBuscarJugador() {
  const caja = $("j-buscar-sugerencias");
  if (!jBuscarSugeridas.length) { caja.classList.add("oculto"); return; }
  caja.innerHTML = jBuscarSugeridas.map((s, n) => `
    <div data-n="${n}" class="${n === jBuscarActivo ? "activa" : ""}">
      <span>${emoji(s.genero)} ${esc(s.nombre)}</span>
      <span class="meta">${s.miembro ? "grupo" : "invitad@"}${s.deuda ? ` · debe ${pesos(s.deuda)}` : ""}</span>
    </div>`).join("");
  caja.classList.remove("oculto");
}

function elegirJugadorBuscar(s) {
  $("j-buscar").value = s.nombre;
  $("j-buscar-sugerencias").classList.add("oculto");
  const idx = estado.jugadores.findIndex((j) => String(j.id) === String(s.id));
  if (idx >= 0) {
    jugadoresPagina = Math.floor(idx / JUGADORES_POR_PAGINA) + 1;
    pintarJugadores();
  }
  const fila = document.querySelector(`[data-jugador="${s.id}"]`);
  if (fila) {
    fila.scrollIntoView({ block: "center", behavior: "smooth" });
    fila.classList.add("resaltado");
    setTimeout(() => fila.classList.remove("resaltado"), 2000);
  }
}

$("j-buscar").addEventListener("input", () => {
  clearTimeout(jBuscarTemporizador);
  jBuscarTemporizador = setTimeout(jBuscarSugerencias, 140);
});
$("j-buscar").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    jBuscarActivo = Math.max(0, Math.min(jBuscarSugeridas.length - 1,
      jBuscarActivo + (e.key === "ArrowDown" ? 1 : -1)));
    pintarSugerenciasBuscarJugador();
  } else if (e.key === "Enter") {
    if (jBuscarActivo >= 0 && jBuscarSugeridas[jBuscarActivo]) {
      e.preventDefault();
      elegirJugadorBuscar(jBuscarSugeridas[jBuscarActivo]);
    }
  } else if (e.key === "Escape") {
    $("j-buscar-sugerencias").classList.add("oculto");
  }
});
$("j-buscar-sugerencias").addEventListener("click", (e) => {
  const div = e.target.closest("div[data-n]");
  if (div) elegirJugadorBuscar(jBuscarSugeridas[Number(div.dataset.n)]);
});

// pintarConfig() -> rellena los campos del formulario de configuración con
// los valores actuales (si no estamos justo editando).
function pintarConfig() {
  if (editandoConfig) return;
  Object.entries(estado.config).forEach(([k, v]) => {
    const el = $("cf-" + k);
    if (el) el.value = v;
  });
}

// ---------------------------------------------------------------- pestañas
// Permite cambiar entre las vistas de Nómina, Partidos, Multas, Jugadores y Configuración.
function activarTab(nombre) {
  const boton = document.querySelector(`.tabs button[data-tab="${nombre}"]`);
  if (!boton) nombre = "partidos";
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.remove("activa"));
  document.querySelector(`.tabs button[data-tab="${nombre}"]`).classList.add("activa");
  document.querySelectorAll(".tab").forEach((s) => s.classList.add("oculto"));
  document.querySelector(`#tab-${nombre}`).classList.remove("oculto");
  window.scrollTo({ top: 0 });
  localStorage.setItem("pestana", nombre);
}

document.querySelectorAll(".tabs button").forEach((b) => {
  b.addEventListener("click", () => activarTab(b.dataset.tab));
});

// --------------------------------------------------------- autocompletado
let temporizador = null;
$("buscar").addEventListener("input", () => {
  seleccionado = null;
  clearTimeout(temporizador);
  temporizador = setTimeout(buscarParticipantes, 140);
});
$("buscar").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    indiceActivo = Math.max(0, Math.min(sugerencias.length - 1,
      indiceActivo + (e.key === "ArrowDown" ? 1 : -1)));
    pintarSugerencias();
  } else if (e.key === "Enter") {
    if (indiceActivo >= 0 && sugerencias[indiceActivo]) elegir(sugerencias[indiceActivo]);
    else anotar();
  } else if (e.key === "Escape") {
    $("sugerencias").classList.add("oculto");
  }
});

// limpiarVoy("voy juan") -> "juan". Quita la palabra "voy" y el "invitado de"
// del texto del buscador, para mandar el nombre limpio al servidor.
const limpiarVoy = (t) =>
  t.replace(/^\s*(yo\s+)?voy\s*(\+|:|,)?\s*/i, "").replace(/\([^)]*\)/, "").trim();

async function buscarParticipantes() {
  const { resultados } = await api("/api/participantes?q="
    + encodeURIComponent(limpiarVoy($("buscar").value))
    + (partidoEnVista ? `&partido_id=${partidoEnVista}` : ""));
  sugerencias = resultados;
  indiceActivo = -1;
  pintarSugerencias();
}

// pintarSugerencias() -> dibuja la cajita con las sugerencias del autocompletado
// y resalta la que está seleccionada (indiceActivo).
function pintarSugerencias() {
  const caja = $("sugerencias");
  if (!sugerencias.length) { caja.classList.add("oculto"); return; }
  caja.innerHTML = sugerencias.map((s, n) => `
    <div data-n="${n}" class="${n === indiceActivo ? "activa" : ""}">
      <span>${emoji(s.genero)} ${esc(s.nombre)}</span>
      <span class="meta">${s.miembro ? "grupo" : "invitad@"}${s.anotado ? " · ya anotad@" : ""}${
        s.expulsado ? " · expulsad@" : ""}${s.deuda ? ` · debe ${pesos(s.deuda)}` : ""}</span>
    </div>`).join("");
  caja.classList.remove("oculto");
}

$("sugerencias").addEventListener("click", (e) => {
  const div = e.target.closest("div[data-n]");
  if (div) elegir(sugerencias[Number(div.dataset.n)]);
});

// elegir(s) -> el usuario eligió una sugerencia: se guarda como "seleccionado",
// se escribe su nombre en el buscador y se define su género.
function elegir(s) {
  seleccionado = s;
  $("buscar").value = s.nombre;
  $("a-genero").value = s.genero;
  $("sugerencias").classList.add("oculto");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".autocompletar")) {
    $("sugerencias").classList.add("oculto");
    $("invitado-sugerencias").classList.add("oculto");
    $("m-jugador-sugerencias").classList.add("oculto");
  }
});

$("a-quien").addEventListener("change", () => {
  $("campo-invita").classList.toggle("oculto", $("a-quien").value !== "invitado");
});

// ------------------------------------------- autocompletado de «invitado por»
// Igual que el buscador «voy», muestra los nombres de la lista de jugadores.
const normalizar = (s) =>
  (s || "").toString().toLowerCase().normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").trim().replace(/\s+/g, " ");

let invitadoSugerencias = [];
let invitadoActivo = -1;
let temporizadorInvita = null;

function buscarInvitadoPor() {
  const q = normalizar($("a-invita").value);
  const lista = estado.jugadores.filter((j) => j.activo);
  if (!q) {
    invitadoSugerencias = lista.slice(0, 10);
  } else {
    const empieza = lista.filter((j) => normalizar(j.nombre).startsWith(q));
    const contiene = lista.filter((j) =>
      normalizar(j.nombre).includes(q) && !empieza.includes(j));
    invitadoSugerencias = empieza.concat(contiene).slice(0, 10);
  }
  invitadoActivo = -1;
  pintarSugerenciasInvita();
}

function pintarSugerenciasInvita() {
  const caja = $("invitado-sugerencias");
  if (!invitadoSugerencias.length) { caja.classList.add("oculto"); return; }
  caja.innerHTML = invitadoSugerencias.map((s, n) => `
    <div data-n="${n}" class="${n === invitadoActivo ? "activa" : ""}">
      <span>${emoji(s.genero)} ${esc(s.nombre)}</span>
      <span class="meta">${s.miembro ? "grupo" : "invitad@"}</span>
    </div>`).join("");
  caja.classList.remove("oculto");
}

function elegirInvita(s) {
  $("a-invita").value = s.nombre;
  $("invitado-sugerencias").classList.add("oculto");
}

$("a-invita").addEventListener("input", () => {
  clearTimeout(temporizadorInvita);
  temporizadorInvita = setTimeout(buscarInvitadoPor, 140);
});
$("a-invita").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    invitadoActivo = Math.max(0, Math.min(invitadoSugerencias.length - 1,
      invitadoActivo + (e.key === "ArrowDown" ? 1 : -1)));
    pintarSugerenciasInvita();
  } else if (e.key === "Enter") {
    if (invitadoActivo >= 0 && invitadoSugerencias[invitadoActivo]) {
      e.preventDefault();
      elegirInvita(invitadoSugerencias[invitadoActivo]);
    }
  } else if (e.key === "Escape") {
    $("invitado-sugerencias").classList.add("oculto");
  }
});
$("invitado-sugerencias").addEventListener("click", (e) => {
  const div = e.target.closest("div[data-n]");
  if (div) elegirInvita(invitadoSugerencias[Number(div.dataset.n)]);
});

// ------------------------------------------------------ anotar y acciones
// anotar(forzar) -> registra al jugador en el partido (lo dice el formulario
// "voy"): quién es, género, si es invitado y quién lo invitó, y a qué lista.
// Si el servidor rechaza (expulsado, sin cupo...) y "forzar" es false, pregunta
// a la directiva si quiere anotarlo igual (decisión de la directiva).
async function anotar(forzar = false) {
  const bruto = $("buscar").value.trim();
  if (!bruto) return;
  const cuerpo = {
    participante_id: seleccionado ? seleccionado.id : null,
    texto: seleccionado ? null : bruto,
    genero: $("a-genero").value,
    miembro: $("a-quien").value !== "invitado",
    invitado_por: $("a-quien").value === "invitado" ? $("a-invita").value.trim() : "",
    lista: $("a-destino").value || null,
    forzar,
    partido_id: partidoEnVista,
  };
  if ($("a-quien").value === "invitado" && !cuerpo.invitado_por) {
    aviso("Escribe quién invitó a esta persona.", true);
    return;
  }
  try {
    const r = await api("/api/nomina", { method: "POST", body: cuerpo });
    $("buscar").value = "";
    $("a-invita").value = "";
    $("a-destino").value = "";  // siempre vuelve a "Automático (reglas)"
    seleccionado = null;
    aviso(`${r.nombre} anotad@ en ${r.lista === "nomina" ? "la nómina" : "lista de espera"}.`
      + (r.aviso ? " " + r.aviso : ""));
    await cargar();
  } catch (err) {
    if (/Regla 1|nómina está llena|expulsad|inactiv/i.test(err.message)
        && confirm(err.message + "\n\n¿Anotar igual (decisión de la directiva)?")) {
      await anotar(true);
      return;
    }
    aviso(err.message, true);
  }
}
$("btn-anotar").addEventListener("click", () => anotar());

// confirmarAgregarInvitado() -> muestra el modal de confirmación para meter a un
// invitado a la nómina antes del corte. Devuelve true si eligen "Agregar".
function confirmarAgregarInvitado() {
  return new Promise((resolver) => {
    const modal = $("modal-invitado");
    modal.classList.remove("oculto");
    const terminar = (ok) => {
      modal.classList.add("oculto");
      resolver(ok);
    };
    $("btn-agregar-invitado").onclick = () => terminar(true);
    $("btn-cancelar-invitado").onclick = () => terminar(false);
  });
}

// moverEnNomina(id, lista) -> mueve a alguien de nómina a espera o viceversa.
// Si es un invitado y el corte aún no pasó, primero pregunta a la directiva
// (modal "Agregar"/"Cancelar"); solo con "Agregar" se mete a la nómina.
async function moverEnNomina(id, lista) {
  try {
    await api(`/api/nomina/${id}/mover`, { method: "POST", body: { lista } });
  } catch (err) {
    if (lista === "nomina" && /corte de invitados/i.test(err.message)) {
      if (!(await confirmarAgregarInvitado())) return;
      await api(`/api/nomina/${id}/mover`, { method: "POST", body: { lista, forzar: true } });
      return;
    }
    throw err;
  }
}

// -------------------------------------------------------- acciones varias
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || !estado) return;
  const d = b.dataset;
  try {
    if (d.quitar) {
      const r = await api(`/api/nomina/${d.quitar}`, { method: "DELETE" });
      aviso(r.mensaje);
    } else if (d.mover) {
      await moverEnNomina(d.mover, d.lista);
    } else if (d.borrarPartido) {
      if (!confirm("¿Borrar este partido y su nómina?")) return;
      await api(`/api/partidos/${d.borrarPartido}`, { method: "DELETE" });
    } else if (d.guardarPartido) {
      if (!confirm("¿Guardar este partido en el historial? Ya no aparecerá en la lista de partidos.")) return;
      await api(`/api/partidos/${d.guardarPartido}/guardar`, { method: "POST", body: {} });
    } else if (d.abrirNomina) {
      if (!confirm("¿Re abrir la nómina de este partido? Volverá a la lista de partidos y se podrá editar.")) return;
      await api(`/api/partidos/${d.abrirNomina}/abrir`, { method: "POST", body: {} });
      partidoEnVista = d.abrirNomina;
      await cargar(partidoEnVista);
      document.querySelector('.tabs button[data-tab="nomina"]').click();
      return;
    } else if (d.histPrev) {
      historialPagina = Math.max(1, historialPagina - 1);
      pintarHistorial();
      return;
    } else if (d.histNext) {
      historialPagina++;
      pintarHistorial();
      return;
    } else if (d.jugPrev) {
      jugadoresPagina = Math.max(1, jugadoresPagina - 1);
      pintarJugadores();
      return;
    } else if (d.jugNext) {
      jugadoresPagina++;
      pintarJugadores();
      return;
    } else if (d.verPartido) {
      partidoEnVista = d.verPartido;
      await cargar(partidoEnVista);
      document.querySelector('.tabs button[data-tab="nomina"]').click();
      return;
    } else if (d.usarPartido) {
      await api(`/api/partidos/${d.usarPartido}/usar`, { method: "POST", body: {} });
      partidoEnVista = d.usarPartido;
      await cargar(partidoEnVista);
      document.querySelector('.tabs button[data-tab="nomina"]').click();
      return;
    } else if (d.editarPartido) {
      const p = estado.partidos.find((x) => String(x.id) === d.editarPartido);
      if (!p) return;
      $("n-fecha").value = p.fecha;
      $("n-hora").value = p.hora;
      $("n-cancha").value = p.cancha;
      editandoPartidoId = p.id;
      $("btn-crear-partido").textContent = "💾 Guardar cambios del partido";
      $("hint-partido-form").textContent = "Estás editando el partido guardado. Guarda los cambios o cancela.";
      document.querySelector('.tabs button[data-tab="partidos"]').click();
      mostrarFormPartido();
      return;
    } else if (d.pagar) {
      await api(`/api/multas/${d.pagar}/pagar`, { method: "POST" });
    } else if (d.abonar) {
      const monto = prompt("¿Cuánto abona?", "1000");
      if (!monto) return;
      await api(`/api/multas/${d.abonar}/abonar`, { method: "POST", body: { abono: monto } });
    } else if (d.borrarMulta) {
      if (!confirm("¿Borrar esta multa?")) return;
      await api(`/api/multas/${d.borrarMulta}`, { method: "DELETE" });
    } else if (d.editarMotivo) {
      const mot = estado.motivos_multa.find((x) => String(x.id) === d.editarMotivo);
      if (!mot) return;
      editandoMotivoId = mot.id;
      abrirFormMotivo(mot);
      return;
    } else if (d.borrarMotivo) {
      if (!confirm("¿Borrar este motivo de multa?")) return;
      await api(`/api/motivos/${d.borrarMotivo}`, { method: "DELETE" });
    } else if (d.editarCancha) {
      const cancha = (estado.canchas || []).find((x) => String(x.id) === d.editarCancha);
      if (!cancha) return;
      editandoCanchaId = cancha.id;
      $("c-cancha-nueva").value = cancha.nombre;
      $("btn-guardar-cancha").textContent = "💾 Guardar cambios";
      $("card-cancha-nueva").classList.remove("oculto");
      $("c-cancha-nueva").focus();
    } else if (d.borrarCancha) {
      if (!confirm("¿Borrar esta cancha?")) return;
      await api(`/api/canchas/${d.borrarCancha}`, { method: "DELETE" });
    } else if (d.sacarGrupo) {
      if (!confirm("¿Sacar del grupo por no pagar al plazo y pasar sus multas a Eliminados?")) return;
      await api(`/api/jugadores/${d.sacarGrupo}`, { method: "POST", body: { expulsado: 1 } });
    } else if (d.reintegrar) {
      if (!confirm("¿Reintegrar a este jugador al grupo?")) return;
      await api(`/api/jugadores/${d.reintegrar}`, { method: "POST", body: { expulsado: 0 } });
    } else if (d.editarMulta) {
      const m = estado.multas.find((x) => String(x.id) === d.editarMulta);
      if (!m) return;
      abrirEditarMulta(m);
      return;
    } else if (d.editarJugador) {
      const j = estado.jugadores.find((x) => String(x.id) === d.editarJugador);
      const nombre = prompt("Nombre del jugador:", j.nombre);
      if (!nombre) return;
      await api(`/api/jugadores/${d.editarJugador}`, { method: "POST", body: { nombre } });
    } else if (d.activo) {
      await api(`/api/jugadores/${d.activo}`, { method: "POST", body: { activo: d.valor } });
    } else if (d.expulsado) {
      await api(`/api/jugadores/${d.expulsado}`, { method: "POST", body: { expulsado: d.valor } });
    } else if (d.borrarJugador) {
      if (!confirm("¿Borrar este jugador y su historial?")) return;
      await api(`/api/jugadores/${d.borrarJugador}`, { method: "DELETE" });
    } else {
      return;
    }
    await cargar();
  } catch (err) {
    aviso(err.message, true);
    alert(err.message);
  }
});

// ---------------------------------------------------------------- partido
$("btn-editar-partido").addEventListener("click", () => {
  if (!estado.partido) return;
  $("p-fecha").value = estado.partido.fecha;
  $("p-hora").value = estado.partido.hora;
  $("p-cancha").value = estado.partido.cancha;
  $("form-partido").classList.remove("oculto");
});
$("btn-cancelar-partido").addEventListener("click", () =>
  $("form-partido").classList.add("oculto"));
$("btn-guardar-partido").addEventListener("click", async () => {
  if (!estado.partido) return;
  await api(`/api/partidos/${estado.partido.id}/editar`, {
    method: "POST",
    body: { fecha: $("p-fecha").value, hora: $("p-hora").value, cancha: $("p-cancha").value },
  });
  $("form-partido").classList.add("oculto");
  await cargar();
});
$("btn-nuevo-partido").addEventListener("click", () => {
  cancelarEdicionPartido();
  document.querySelector('.tabs button[data-tab="partidos"]').click();
  mostrarFormPartido();
});

// mostrarFormPartido() -> despliega la tarjeta de crear/editar partido.
function mostrarFormPartido() {
  $("card-crear-partido").classList.remove("oculto");
  $("n-fecha").focus();
}

// cancelarEdicionPartido() -> deja los campos de crear/editar partido en blanco
// y restaura el botón a "Guardar".
function cancelarEdicionPartido() {
  editandoPartidoId = null;
  $("n-fecha").value = "";
  $("n-hora").value = "";
  $("n-cancha").value = "";
  $("btn-crear-partido").textContent = "Guardar";
  $("card-crear-partido").classList.add("oculto");
  $("hint-partido-form").textContent = "La fecha, la hora y la cancha son obligatorias para crear el partido.";
}
$("btn-cancelar-partido-top").addEventListener("click", cancelarEdicionPartido);
$("btn-nuevo-partido-top").addEventListener("click", () => {
  const card = $("card-crear-partido");
  if (card.classList.contains("oculto")) {
    cancelarEdicionPartido();
    mostrarFormPartido();
  } else {
    card.classList.add("oculto");
  }
});

// ---------------------------------------------------------- cancha nueva
let editandoCanchaId = null;

// resetFormCancha() -> deja el formulario de cancha en blanco y en modo alta.
function resetFormCancha() {
  editandoCanchaId = null;
  $("c-cancha-nueva").value = "";
  $("btn-guardar-cancha").textContent = "Guardar cancha";
}

// abrirFormCancha() -> muestra el panel de gestión (formulario + listado).
function abrirFormCancha() {
  resetFormCancha();
  $("card-cancha-nueva").classList.remove("oculto");
  $("c-cancha-nueva").focus();
}
$("btn-nuevo-cancha").addEventListener("click", abrirFormCancha);
$("btn-ver-historial").addEventListener("click", () => {
  const card = $("card-historial");
  card.classList.toggle("oculto");
  pintarHistorial();
  $("btn-ver-historial").textContent = card.classList.contains("oculto") ? "Ver" : "Ocultar";
});
$("btn-cancelar-cancha").addEventListener("click", () => {
  resetFormCancha();
  $("card-cancha-nueva").classList.add("oculto");
});
$("btn-guardar-cancha").addEventListener("click", async () => {
  const nombre = $("c-cancha-nueva").value.trim();
  if (!nombre) { alert("Escribe el nombre de la cancha"); return; }
  try {
    if (editandoCanchaId) {
      await api(`/api/canchas/${editandoCanchaId}/editar`, { method: "POST", body: { nombre } });
    } else {
      await api("/api/canchas", { method: "POST", body: { nombre } });
      $("n-cancha").value = nombre;
    }
    $("card-cancha-nueva").classList.add("oculto");
    resetFormCancha();
    await cargar();
  } catch (err) {
    alert(err.message);
  }
});

$("btn-crear-partido").addEventListener("click", async () => {
  if (!$("n-fecha").value) { alert("Selecciona la fecha del partido"); return; }
  if (!$("n-hora").value) { alert("Selecciona la hora del partido"); return; }
  if (!$("n-cancha").value.trim()) { alert("Escribe la cancha del partido"); return; }
  try {
    if (editandoPartidoId) {
      await api(`/api/partidos/${editandoPartidoId}/editar`, {
        method: "POST",
        body: { fecha: $("n-fecha").value, hora: $("n-hora").value, cancha: $("n-cancha").value },
      });
      cancelarEdicionPartido();
      await cargar();
      document.querySelector('.tabs button[data-tab="partidos"]').click();
    } else {
      const r = await api("/api/partidos", {
        method: "POST",
        body: { fecha: $("n-fecha").value, hora: $("n-hora").value, cancha: $("n-cancha").value },
      });
      cancelarEdicionPartido();
      partidoEnVista = r.id;
      await cargar(partidoEnVista);
      document.querySelector('.tabs button[data-tab="nomina"]').click();
    }
  } catch (err) {
    alert(err.message);
  }
});

// ---------------------------------------------------------- editar multas
let editandoMultaId = null;  // id de la multa que se está editando (null = nueva)
let multaJugadorId = null;   // id del jugador de la multa (lo elige el autocompletado)
let multaValorOriginal = null;  // valor guardado de la multa en edición

// abrirEditarMulta(m) -> llena el formulario con los datos de una multa
// existente para poder modificarla.
function abrirEditarMulta(m) {
  editandoMultaId = m.id;
  multaValorOriginal = m.valor;
  const mot = (m.motivo || "").trim();
  const coincide = [...$("m-motivo-comun").options].find((o) =>
    o.dataset.texto && o.dataset.texto.trim().toLowerCase() === mot.toLowerCase());
  $("m-motivo-comun").value = coincide ? coincide.value : "";
  $("m-abono").value = m.abono || 0;
  $("m-fecha").value = m.fecha;
  $("m-plazo").value = m.plazo || "";
  $("btn-guardar-multa").textContent = "💾 Guardar cambios de la multa";
  $("card-registrar-multa").classList.remove("oculto");
  multaJugadorId = m.participante_id || null;
  $("m-jugador").value = m.nombre || "";
  window.scrollTo({ top: 0 });
}

// cerrarEditarMulta() -> vuelve el formulario de multas al modo "Registrar nueva".
function cerrarEditarMulta() {
  editandoMultaId = null;
  multaJugadorId = null;
  multaValorOriginal = null;
  $("btn-guardar-multa").textContent = "Guardar";
  $("m-motivo-comun").value = "";
}

// limpiarFormMotivo() -> deja en blanco el formulario de motivos de multa.
function limpiarFormMotivo() {
  editandoMotivoId = null;
  $("m-motivo-nuevo").value = "";
  $("m-motivo-nuevo-valor").value = "";
  $("btn-guardar-motivo").textContent = "Guardar motivo";
  $("card-motivos-personalizados").classList.add("oculto");
}
// abrirFormMotivo(mot) -> muestra el formulario para agregar o editar un motivo
// de multa (si "mot" viene con datos, es edición).
function abrirFormMotivo(mot) {
  $("m-motivo-nuevo").value = mot ? mot.texto : "";
  $("m-motivo-nuevo-valor").value = mot ? mot.valor : "";
  $("btn-guardar-motivo").textContent = mot ? "💾 Guardar cambios" : "Guardar motivo";
  $("card-motivos-personalizados").classList.remove("oculto");
  $("form-motivo-nuevo").classList.remove("oculto");
  $("m-motivo-nuevo").focus();
}
$("btn-nuevo-motivo").addEventListener("click", () => abrirFormMotivo(null));
$("btn-cancelar-editar-motivo").addEventListener("click", limpiarFormMotivo);
$("btn-guardar-motivo").addEventListener("click", async () => {
  const texto = $("m-motivo-nuevo").value.trim();
  const valor = Number($("m-motivo-nuevo-valor").value);
  if (!texto) { alert("Escribe el motivo de la multa"); return; }
  if (!valor || valor <= 0) { alert("El valor del motivo debe ser mayor a 0"); return; }
  try {
    if (editandoMotivoId) {
      await api(`/api/motivos/${editandoMotivoId}/editar`, {
        method: "POST",
        body: { texto, valor },
      });
    } else {
      await api("/api/motivos", { method: "POST", body: { texto, valor } });
    }
    limpiarFormMotivo();
    await cargar();
  } catch (err) {
    alert(err.message);
  }
});

// Autocompletado de jugador en el formulario de multa (igual que «voy»).
let multaJugadorSugeridas = [];
let multaJugadorActivo = -1;
let temporizadorMultaJugador = null;

// buscarJugadorMulta() -> busca jugadores activos para el autocompletado del
// formulario de multa, ordenando los que empiezan con lo escrito primero.
function buscarJugadorMulta() {
  const q = normalizar($("m-jugador").value);
  const lista = estado.jugadores.filter((j) => j.activo);
  if (!q) {
    multaJugadorSugeridas = [];
  } else {
    const empieza = lista.filter((j) => normalizar(j.nombre).startsWith(q));
    const contiene = lista.filter((j) =>
      normalizar(j.nombre).includes(q) && !empieza.includes(j));
    multaJugadorSugeridas = empieza.concat(contiene).slice(0, 10);
  }
  multaJugadorActivo = -1;
  pintarSugerenciasJugadorMulta();
}

// pintarSugerenciasJugadorMulta() -> dibuja las sugerencias de jugador para la
// multa y resalta la seleccionada.
function pintarSugerenciasJugadorMulta() {
  const caja = $("m-jugador-sugerencias");
  if (!multaJugadorSugeridas.length) { caja.classList.add("oculto"); return; }
  caja.innerHTML = multaJugadorSugeridas.map((s, n) => `
    <div data-n="${n}" class="${n === multaJugadorActivo ? "activa" : ""}">
      <span>${emoji(s.genero)} ${esc(s.nombre)}</span>
      <span class="meta">${s.miembro ? "grupo" : "invitad@"}${s.deuda ? ` · debe ${pesos(s.deuda)}` : ""}</span>
    </div>`).join("");
  caja.classList.remove("oculto");
}

// elegirJugadorMulta(s) -> al elegir un jugador en el autocompletado de multa,
// guarda su id y escribe su nombre en el campo.
function elegirJugadorMulta(s) {
  multaJugadorId = s.id;
  $("m-jugador").value = s.nombre;
  $("m-jugador-sugerencias").classList.add("oculto");
}

$("m-jugador").addEventListener("input", () => {
  multaJugadorId = null;
  clearTimeout(temporizadorMultaJugador);
  temporizadorMultaJugador = setTimeout(buscarJugadorMulta, 140);
});
$("m-jugador").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    multaJugadorActivo = Math.max(0, Math.min(multaJugadorSugeridas.length - 1,
      multaJugadorActivo + (e.key === "ArrowDown" ? 1 : -1)));
    pintarSugerenciasJugadorMulta();
  } else if (e.key === "Enter") {
    if (multaJugadorActivo >= 0 && multaJugadorSugeridas[multaJugadorActivo]) {
      e.preventDefault();
      elegirJugadorMulta(multaJugadorSugeridas[multaJugadorActivo]);
    }
  } else if (e.key === "Escape") {
    $("m-jugador-sugerencias").classList.add("oculto");
  }
});
$("m-jugador-sugerencias").addEventListener("click", (e) => {
  const div = e.target.closest("div[data-n]");
  if (div) elegirJugadorMulta(multaJugadorSugeridas[Number(div.dataset.n)]);
});
$("btn-cancelar-multa").addEventListener("click", () => {
  cerrarEditarMulta();
  $("card-registrar-multa").classList.add("oculto");
});
$("btn-nuevo-multa-top").addEventListener("click", () => {
  const card = $("card-registrar-multa");
  if (card.classList.contains("oculto")) {
    cerrarEditarMulta();
    $("card-registrar-multa").classList.remove("oculto");
    $("m-jugador").focus();
  } else {
    card.classList.add("oculto");
  }
});
$("btn-guardar-multa").addEventListener("click", async () => {
  const opMotivo = $("m-motivo-comun").selectedOptions[0];
  // El valor de la multa sale del motivo elegido (ya no hay campo propio).
  const valor = opMotivo && opMotivo.value ? opMotivo.value : (multaValorOriginal || 0);
  const cuerpo = {
    participante_id: multaJugadorId,
    fecha: $("m-fecha").value,
    valor,
    abono: $("m-abono").value,
    motivo: opMotivo && opMotivo.dataset.texto ? opMotivo.dataset.texto : "",
    plazo: $("m-plazo").value,
  };
  try {
    if (editandoMultaId) {
      await api(`/api/multas/${editandoMultaId}/editar`, {
        method: "POST",
        body: {
          participante_id: cuerpo.participante_id,
          fecha: cuerpo.fecha,
          valor: cuerpo.valor,
          abono: cuerpo.abono,
          motivo: cuerpo.motivo,
          plazo: cuerpo.plazo,
        },
      });
      cerrarEditarMulta();
    } else {
      await api("/api/multas", { method: "POST", body: cuerpo });
    }
    $("m-motivo-comun").value = "";
    $("m-abono").value = 0;
    $("m-plazo").value = "";
    await cargar();
  } catch (err) {
    alert(err.message);
  }
});

// -------------------------------------------------------------- jugadores
$("btn-nuevo-jugador-top").addEventListener("click", () => {
  const card = $("card-registrar-jugador");
  if (card.classList.contains("oculto")) {
    card.classList.remove("oculto");
    $("j-nombre").focus();
  } else {
    card.classList.add("oculto");
  }
});
$("btn-cancelar-jugador").addEventListener("click", () =>
  $("card-registrar-jugador").classList.add("oculto"));
$("btn-agregar-jugador").addEventListener("click", async () => {
  try {
    await api("/api/jugadores", {
      method: "POST",
      body: {
        nombre: $("j-nombre").value,
        genero: $("j-genero").value,
        miembro: 1,
      },
    });
    $("j-nombre").value = "";
    await cargar();
  } catch (err) {
    alert(err.message);
  }
});

// ----------------------------------------------------------------- config
$("btn-cambiar-cupos").addEventListener("click", () => {
  $("cupos-mujeres").value = estado.config.cupos_mujeres || 6;
  $("cupos-hombres").value = estado.config.cupos_hombres || 6;
  $("form-cupos").classList.remove("oculto");
});
$("btn-cancelar-cupos").addEventListener("click", () => $("form-cupos").classList.add("oculto"));
$("btn-guardar-cupos").addEventListener("click", async () => {
  const mujeres = Number($("cupos-mujeres").value);
  const hombres = Number($("cupos-hombres").value);
  if (!Number.isInteger(mujeres) || !Number.isInteger(hombres) || mujeres < 0 || hombres < 0) {
    alert("Ingresa números válidos para los cupos.");
    return;
  }
  try {
    await api("/api/config", {
      method: "POST",
      body: {
        cupos_mujeres: String(mujeres),
        cupos_hombres: String(hombres),
        cupos_personalizados: "1",
      },
    });
    $("form-cupos").classList.add("oculto");
    await cargar();
    alert("Cupos actualizados");
  } catch (err) {
    alert(err.message);
  }
});

document.querySelectorAll('[id^="cf-"]').forEach((el) => {
  el.addEventListener("focus", () => (editandoConfig = true));
});
$("btn-guardar-config").addEventListener("click", async () => {
  const cuerpo = {};
  document.querySelectorAll('[id^="cf-"]').forEach((el) => {
    const clave = el.id.slice(3);
    // el PIN vacío significa "dejarlo como está"; para quitarlo se escribe SIN-PIN
    if (clave === "pin") {
      if (!el.value.trim()) return;
      cuerpo.pin = el.value.trim().toUpperCase() === "SIN-PIN" ? "" : el.value.trim();
      return;
    }
    cuerpo[clave] = el.value;
  });
  try {
    await api("/api/config", { method: "POST", body: cuerpo });
    editandoConfig = false;
    await cargar();
    alert("Configuración guardada");
  } catch (err) {
    alert(err.message);
  }
});

// ------------------------------------------------------- whatsapp y login
// "estado.texto" es el mensaje listo para pegar en WhatsApp que arma el servidor.
//
// Copiar al portapapeles en el navegador tiene DOS caminos:
//   1. API moderna: navigator.clipboard.writeText(). Solo funciona si la página
//      está en un contexto seguro (HTTPS o localhost). En el computador por lo
//      general sí está disponible; en el CELULAR (si entras por la IP de tu red)
//      NO existe, por eso hay que usar el método de respaldo.
//   2. Respaldo universal: crear un <textarea> temporal invisible, seleccionar su
//      texto y llamar document.execCommand("copy"), que sí funciona en móviles.
//
// copiarAlPortapapeles(texto)  -> elige el método disponible y devuelve una
//                                 Promise que resuelve true/false si copió.
function copiarAlPortapapeles(texto) {
  return new Promise((resolver, rechazar) => {
    // window.isSecureContext = true solo si la página está servida con HTTPS
    // o es localhost. Ahí la API moderna está permitida.
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(texto).then(
        () => resolver(true),           // copió con la API moderna
        () => resolver(copiarConTextArea(texto)) // si falla, usa el respaldo
      );
    } else {
      // Celular (o cualquier navegador sin contexto seguro): respaldo directo.
      resolver(copiarConTextArea(texto));
    }
  });
}

// copiarConTextArea(texto) -> método de respaldo. Crea un textarea invisible,
// selecciona el texto y ejecuta la orden nativa de copiado. Devuelve true/false.
function copiarConTextArea(texto) {
  const temporal = document.createElement("textarea");
  temporal.value = texto;
  temporal.setAttribute("readonly", ""); // evita que el teclado se abra en el móvil
  // Lo ponemos fuera de la pantalla para que no se vea ni mueva el scroll.
  temporal.style.position = "fixed";
  temporal.style.top = "-9999px";
  document.body.appendChild(temporal);
  // Selecciona TODO el contenido del textarea.
  temporal.select();
  temporal.setSelectionRange(0, temporal.value.length);
  // Ejecuta la orden de copiado del navegador (funciona en móviles).
  const copiado = document.execCommand("copy");
  // Limpia el elemento temporal para no dejar basura en la página.
  document.body.removeChild(temporal);
  return copiado;
}

$("btn-copiar").addEventListener("click", async () => {
  const boton = $("btn-copiar"); // el <button> "Copiar" de la tarjeta de WhatsApp
  try {
    // estado.texto es el mensaje que el servidor generó para WhatsApp.
    const copiado = await copiarAlPortapapeles(estado.texto);
    // Si no se pudo copiar, avisamos para que lo haga a mano.
    boton.textContent = copiado ? "¡Copiado!" : "Copia manual";
  } catch {
    boton.textContent = "Copia manual";
  }
  // Vuelve a decir "Copiar" después de 2 segundos.
  setTimeout(() => (boton.textContent = "Copiar"), 2000);
});

$("btn-login").addEventListener("click", () => {
  $("login-error").classList.add("oculto");
  $("login-pin").value = "";
  $("modal-login").classList.remove("oculto");
  $("login-pin").focus();
});
$("btn-cerrar-login").addEventListener("click", () => $("modal-login").classList.add("oculto"));
$("login-pin").addEventListener("keydown", (e) => e.key === "Enter" && entrar());
$("btn-entrar").addEventListener("click", entrar);

async function entrar() {
  try {
    await api("/api/login", { method: "POST", body: { pin: $("login-pin").value } });
    $("modal-login").classList.add("oculto");
    await cargar();
  } catch (err) {
    $("login-error").textContent = err.message;
    $("login-error").classList.remove("oculto");
  }
}

$("btn-logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  await cargar();
});

$("m-fecha").value = new Date().toISOString().slice(0, 10);

// Al cargar (o volver a la pestaña con el estado restaurado del navegador),
// el destino siempre queda en "Automático (reglas)" y sin mensajes viejos.
window.addEventListener("pageshow", () => {
  $("a-destino").value = "";
  $("aviso").textContent = "";
  $("aviso").classList.add("oculto");
});

cargar().then(() => {
  const guardada = localStorage.getItem("pestana");
  const valida = guardada && document.querySelector(`.tabs button[data-tab="${guardada}"]`);
  if (guardada === "config" && estado.rol !== "directiva") {
    activarTab("partidos");
  } else if (valida) {
    activarTab(guardada);
  } else {
    activarTab("partidos");
  }
});
