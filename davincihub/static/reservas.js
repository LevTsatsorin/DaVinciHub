const panel = document.querySelector("[data-panel-reserva]");

if (panel) {
  const turnos = [...document.querySelectorAll(".turno")];
  const desde = panel.querySelector("[data-desde]");
  const hasta = panel.querySelector("[data-hasta]");
  const resumen = panel.querySelector("[data-resumen]");
  const error = panel.querySelector("[data-error]");
  const boton = panel.querySelector("[data-confirmar-reserva]");
  const ayuda = document.querySelector("[data-ayuda]");
  let ancla = null;

  const minutos = (hora) => {
    const [h, m] = hora.split(":").map(Number);
    return h * 60 + m;
  };

  const duracion = (inicio, fin) => {
    const total = minutos(fin) - minutos(inicio);
    const horas = Math.floor(total / 60);
    const resto = total % 60;
    return [horas && `${horas} h`, resto && `${resto} min`].filter(Boolean).join(" ");
  };

  const turnosEntre = (inicio, fin) =>
    turnos.filter((t) => t.dataset.inicio >= inicio && t.dataset.fin <= fin);

  const rangoValido = (inicio, fin) => {
    if (!inicio || !fin || minutos(fin) <= minutos(inicio)) return false;
    const dentro = turnosEntre(inicio, fin);
    if (!dentro.length || dentro.some((t) => !t.classList.contains("turno-libre"))) return false;
    if (dentro.some((t) => t.parentElement !== dentro[0].parentElement)) return false;
    return dentro.every((t, i) => i === 0 || dentro[i - 1].dataset.fin === t.dataset.inicio);
  };

  const marcarRango = (clase, inicio, fin) => {
    const dentro = inicio && fin ? turnosEntre(inicio, fin) : [];
    turnos.forEach((t) => {
      const i = dentro.indexOf(t);
      t.classList.toggle(clase, i >= 0);
      t.classList.toggle(`${clase}-inicio`, i === 0);
      t.classList.toggle(`${clase}-fin`, i >= 0 && i === dentro.length - 1);
    });
  };

  const pintar = () => {
    const inicio = desde.value;
    const fin = hasta.value;
    const valido = rangoValido(inicio, fin);
    marcarRango("turno-elegido", valido ? inicio : null, fin);
    turnos.forEach((t) => t.setAttribute("aria-pressed", String(t.classList.contains("turno-elegido"))));
    resumen.textContent = valido
      ? `${resumen.dataset.dia} · ${inicio} → ${fin} · ${duracion(inicio, fin)}`
      : "Elegí un horario en la línea de tiempo";
    if (ayuda) {
      ayuda.textContent = ancla
        ? `Inicio: ${ancla.dataset.inicio}. Ahora tocá hasta qué hora la necesitás.`
        : "Tocá la hora de inicio y después la de fin.";
    }
    const incompleto = inicio && fin && !valido;
    error.hidden = !incompleto;
    error.textContent = incompleto
      ? "Ese rango incluye horarios ocupados o pasa de una franja a otra. Elegí un horario dentro de una sola franja."
      : "";
    boton.disabled = !valido;
    panel.classList.toggle("panel-listo", valido);
    actualizarConfirmacion();
  };

  const actualizarConfirmacion = () => {
    const personas = panel.elements.personas.value;
    const motivo = panel.elements.motivo.value.trim();
    const quienes = [personas && (personas === "1" ? "1 persona" : `${personas} personas`), motivo];
    panel.dataset.confirmarTexto = [
      panel.dataset.espacio,
      resumen.textContent,
      quienes.filter(Boolean).join(" · "),
      "",
      "Podés cancelarla desde Mis reservas hasta que empiece.",
    ].join("\n");
  };

  panel.addEventListener("input", actualizarConfirmacion);

  const elegirSolo = (turno) => {
    ancla = turno;
    desde.value = turno.dataset.inicio;
    hasta.value = turno.dataset.fin;
  };

  turnos.forEach((turno) => {
    turno.addEventListener("click", () => {
      if (ancla === null || turno.dataset.inicio < ancla.dataset.inicio) {
        elegirSolo(turno);
      } else if (rangoValido(ancla.dataset.inicio, turno.dataset.fin)) {
        desde.value = ancla.dataset.inicio;
        hasta.value = turno.dataset.fin;
        ancla = null;
      } else {
        elegirSolo(turno);
      }
      marcarRango("turno-previa", null, null);
      pintar();
    });

    turno.addEventListener("pointerenter", () => {
      if (ancla && turno.dataset.inicio >= ancla.dataset.inicio
          && rangoValido(ancla.dataset.inicio, turno.dataset.fin)) {
        marcarRango("turno-previa", ancla.dataset.inicio, turno.dataset.fin);
      }
    });
  });

  document.querySelectorAll(".pista").forEach((pista) =>
    pista.addEventListener("pointerleave", () => marcarRango("turno-previa", null, null)));

  [desde, hasta].forEach((select) => select.addEventListener("change", () => {
    ancla = null;
    pintar();
  }));

  pintar();
}
