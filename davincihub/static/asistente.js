const asistente = document.querySelector("[data-asistente]");

if (asistente) {
  const pasos = [...asistente.querySelectorAll("[data-paso]")];
  const indicadores = [...document.querySelectorAll("[data-indicador]")];
  const duracion = asistente.querySelector("[data-duracion]");
  const resumen = asistente.querySelector("[data-resumen]");
  const ordinal = (n) => `${n}.${n === 1 || n === 3 ? "er" : "º"}`;

  const nombresDe = (cuatrimestre) =>
    [...cuatrimestre.querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);

  const actualizarCantidad = (cuatrimestre) => {
    const cantidad = nombresDe(cuatrimestre).length;
    cuatrimestre.querySelector("[data-cantidad]").textContent = cantidad ? `· ${cantidad}` : "";
  };

  const actualizarAnios = () => {
    const anios = Number(duracion.value);
    asistente.querySelectorAll("[data-anio]").forEach((anio) => {
      const fuera = Number(anio.dataset.anio) > anios;
      anio.hidden = fuera;
      anio.querySelectorAll("input").forEach((input) => { input.disabled = fuera; });
    });
  };

  const armarResumen = () => {
    const visibles = [...asistente.querySelectorAll("[data-anio]:not([hidden])")];
    const titulo = asistente.elements.titulo.value.trim();
    resumen.replaceChildren();
    const cabecera = document.createElement("div");
    cabecera.className = "resumen-asistente-cabecera";
    const nombre = document.createElement("h2");
    nombre.textContent = asistente.elements.nombre.value.trim();
    const detalle = document.createElement("p");
    detalle.textContent = [titulo, duracion.selectedOptions[0].textContent].filter(Boolean).join(" · ");
    cabecera.append(nombre, detalle);
    resumen.append(cabecera);
    let total = 0;
    visibles.forEach((anio) => {
      const bloque = document.createElement("div");
      bloque.className = "resumen-asistente-anio";
      const encabezado = document.createElement("h3");
      const lista = document.createElement("ul");
      lista.className = "reserva-chips";
      let delAnio = 0;
      anio.querySelectorAll("[data-cuatrimestre]").forEach((cuatrimestre) => {
        nombresDe(cuatrimestre).forEach((materia) => {
          const chip = document.createElement("li");
          chip.textContent = `${materia} · ${cuatrimestre.dataset.cuatrimestre}.º cuatr.`;
          lista.append(chip);
          delAnio += 1;
        });
      });
      total += delAnio;
      encabezado.textContent = `${ordinal(Number(anio.dataset.anio))} año · ${delAnio} ${delAnio === 1 ? "materia" : "materias"}`;
      bloque.append(encabezado);
      if (delAnio) bloque.append(lista);
      resumen.append(bloque);
    });
    if (!total) {
      const nota = document.createElement("p");
      nota.className = "nota";
      nota.textContent = "Todavía no cargaste materias. Podés crear la carrera igual y armar el plan después.";
      resumen.append(nota);
    }
  };

  const mostrar = (numero, desplazar = true) => {
    pasos.forEach((paso) => { paso.hidden = paso.dataset.paso !== String(numero); });
    indicadores.forEach((indicador) => {
      const n = Number(indicador.dataset.indicador);
      indicador.classList.toggle("paso-actual", n === numero);
      indicador.classList.toggle("paso-hecho", n < numero);
    });
    if (numero === 3) armarResumen();
    if (desplazar) {
      const barra = document.querySelector(".barra").offsetHeight;
      const arriba = indicadores[0].getBoundingClientRect().top + window.scrollY - barra - 16;
      if (window.scrollY > arriba) window.scrollTo({ top: arriba, behavior: "instant" });
    }
  };

  asistente.classList.add("asistente-activo");

  asistente.addEventListener("click", (evento) => {
    const ir = evento.target.closest("[data-ir]");
    if (ir) {
      const destino = Number(ir.dataset.ir);
      const actual = pasos.find((paso) => !paso.hidden);
      if (destino > Number(actual.dataset.paso)) {
        const invalido = [...actual.querySelectorAll("input, select")].find((c) => !c.disabled && !c.checkValidity());
        if (invalido) {
          invalido.reportValidity();
          return;
        }
      }
      mostrar(destino);
      return;
    }
    const agregar = evento.target.closest("[data-agregar-materia]");
    if (agregar) {
      const lista = agregar.parentElement.querySelector("[data-lista-materias]");
      const vacia = [...lista.querySelectorAll("input")].find((i) => !i.value.trim());
      if (vacia) {
        vacia.focus();
        return;
      }
      const fila = lista.lastElementChild.cloneNode(true);
      fila.querySelector("input").value = "";
      lista.append(fila);
      fila.querySelector("input").focus();
      return;
    }
    const quitar = evento.target.closest("[data-quitar-materia]");
    if (quitar) {
      const fila = quitar.closest("li");
      const cuatrimestre = fila.closest("[data-cuatrimestre]");
      if (fila.parentElement.children.length > 1) fila.remove();
      else fila.querySelector("input").value = "";
      actualizarCantidad(cuatrimestre);
    }
  });

  asistente.addEventListener("keydown", (evento) => {
    if (evento.key !== "Enter" || evento.target.tagName !== "INPUT") return;
    evento.preventDefault();
    const fila = evento.target.closest(".fila-materia");
    if (!fila) return;
    if (!evento.target.value.trim()) return;
    const siguiente = fila.nextElementSibling?.querySelector("input");
    if (siguiente) {
      siguiente.focus();
      return;
    }
    const nueva = fila.cloneNode(true);
    nueva.querySelector("input").value = "";
    fila.after(nueva);
    nueva.querySelector("input").focus();
  });

  asistente.addEventListener("input", (evento) => {
    const cuatrimestre = evento.target.closest("[data-cuatrimestre]");
    if (cuatrimestre) actualizarCantidad(cuatrimestre);
  });

  duracion.addEventListener("change", actualizarAnios);
  asistente.querySelectorAll("[data-cuatrimestre]").forEach(actualizarCantidad);
  actualizarAnios();
  mostrar(Number(asistente.dataset.pasoInicial) || 1, false);
}
