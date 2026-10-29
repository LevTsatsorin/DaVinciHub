const ESPERA_CHAT = 3000;
const ESPERA_BANDEJA = 8000;

const repetir = (tarea, espera) => {
  let temporizador = null;
  const programar = () => {
    clearTimeout(temporizador);
    if (!document.hidden) temporizador = setTimeout(correr, espera);
  };
  const correr = async () => {
    try {
      await tarea();
    } catch {
      // sin conexión: se reintenta en la próxima vuelta
    }
    programar();
  };
  document.addEventListener("visibilitychange", () => (document.hidden ? clearTimeout(temporizador) : correr()));
  programar();
  return correr;
};

const actualizarCampana = (cantidad) => {
  const campana = document.querySelector(".campana[data-avisos]");
  if (!campana || Number(campana.dataset.avisos) === cantidad) return;
  campana.dataset.avisos = cantidad;
  campana.setAttribute("aria-label", cantidad ? `Notificaciones: ${cantidad} sin leer` : "Notificaciones");
  let globo = campana.querySelector(".campana-cantidad");
  if (!cantidad) return globo?.remove();
  if (!globo) {
    globo = document.createElement("span");
    globo.className = "campana-cantidad";
    campana.append(globo);
  }
  globo.textContent = cantidad < 10 ? cantidad : "9+";
};

const lista = document.querySelector(".chat-mensajes[data-nuevos]");

if (lista) {
  const formulario = document.querySelector("[data-chat-enviar]");
  const campo = formulario.querySelector("textarea");
  const boton = formulario.querySelector("button[type=submit]");
  const error = formulario.querySelector("[data-chat-error]");
  const ids = new Set([...lista.querySelectorAll("[data-mensaje-id]")].map((li) => Number(li.dataset.mensajeId)));
  const ultimo = () => Math.max(0, ...ids);
  const pegadoAbajo = () => lista.scrollHeight - lista.scrollTop - lista.clientHeight < 80;
  const bajar = () => { lista.scrollTop = lista.scrollHeight; };

  const crear = (mensaje) => {
    const item = document.createElement("li");
    item.className = `chat-mensaje ${mensaje.propio ? "chat-mensaje-propio" : "chat-mensaje-ajeno"}`;
    item.dataset.mensajeId = mensaje.id;
    const autor = document.createElement("span");
    autor.className = "chat-mensaje-autor";
    autor.textContent = mensaje.autor;
    const texto = document.createElement("p");
    texto.textContent = mensaje.cuerpo;
    const hora = document.createElement("time");
    hora.dateTime = mensaje.creado;
    hora.textContent = mensaje.hora;
    item.append(autor, texto, hora);
    return item;
  };

  const pintar = (mensaje) => {
    if (ids.has(mensaje.id)) return;
    ids.add(mensaje.id);
    lista.querySelector(".chat-vacio")?.remove();
    lista.append(crear(mensaje));
  };

  const cargando = lista.querySelector("[data-chat-cargando]");
  let pidiendo = false;
  const primeroCargado = () => Number(lista.querySelector("[data-mensaje-id]")?.dataset.mensajeId || 0);

  const traerAnteriores = async () => {
    if (pidiendo || !cargando?.isConnected) return;
    pidiendo = true;
    try {
      const respuesta = await fetch(`${lista.dataset.anteriores}?antes=${primeroCargado()}`, { headers: { "X-Requested-With": "fetch" } });
      if (!respuesta.ok) return;
      const datos = await respuesta.json();
      const alturaAntes = lista.scrollHeight;
      const tanda = document.createDocumentFragment();
      datos.mensajes.filter((m) => !ids.has(m.id)).forEach((m) => {
        ids.add(m.id);
        tanda.append(crear(m));
      });
      cargando.after(tanda);
      lista.scrollTop += lista.scrollHeight - alturaAntes;
      if (!datos.hay_mas) cargando.remove();
    } finally {
      pidiendo = false;
    }
  };

  if (cargando) {
    new IntersectionObserver((entradas) => {
      if (entradas.some((e) => e.isIntersecting)) traerAnteriores();
    }, { root: lista, rootMargin: "200px 0px 0px 0px" }).observe(cargando);
  }

  const traerNuevos = async () => {
    const respuesta = await fetch(`${lista.dataset.nuevos}?desde=${ultimo()}`, { headers: { "X-Requested-With": "fetch" } });
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    const abajo = pegadoAbajo();
    datos.mensajes.forEach(pintar);
    if (datos.mensajes.length && abajo) bajar();
    actualizarCampana(datos.avisos);
  };
  const ahora = repetir(traerNuevos, ESPERA_CHAT);

  const mostrarError = (texto) => {
    error.textContent = texto;
    error.hidden = !texto;
  };

  const ajustar = () => {
    campo.style.height = "auto";
    campo.style.height = `${Math.min(campo.scrollHeight, 160)}px`;
  };

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!campo.value.trim() || boton.disabled) return;
    boton.disabled = true;
    try {
      const respuesta = await fetch(formulario.action || location.pathname, {
        method: "POST",
        body: new FormData(formulario),
        headers: { "X-Requested-With": "fetch" },
      });
      const datos = await respuesta.json();
      if (!respuesta.ok) return mostrarError(datos.error || "No pudimos enviar el mensaje.");
      mostrarError("");
      pintar(datos.mensaje);
      campo.value = "";
      ajustar();
      bajar();
    } catch {
      mostrarError("No pudimos enviar el mensaje. Revisá tu conexión y probá de nuevo.");
    } finally {
      boton.disabled = false;
      campo.focus();
    }
  });

  campo.addEventListener("input", ajustar);
  campo.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
      evento.preventDefault();
      formulario.requestSubmit();
    }
  });
  window.addEventListener("focus", ahora);
  const primerNuevo = lista.querySelector("[data-primer-nuevo]");
  if (primerNuevo) lista.scrollTop += primerNuevo.getBoundingClientRect().top - lista.getBoundingClientRect().top - 12;
  else bajar();
  ajustar();
  campo.focus();
}

const bandeja = document.querySelector("[data-bandeja][data-estado]");

if (bandeja) {
  const contador = document.querySelector("[data-bandeja-sin-leer]");
  repetir(async () => {
    const respuesta = await fetch(bandeja.dataset.estado, { headers: { "X-Requested-With": "fetch" } });
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    bandeja.innerHTML = datos.bandeja;
    if (contador) contador.querySelector("strong").textContent = datos.con_sin_leer;
    actualizarCampana(datos.avisos);
  }, ESPERA_BANDEJA);
}
