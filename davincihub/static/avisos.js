const avisos = document.querySelector("[data-avisos-flotantes]");

if (avisos) {
  const cerrar = (aviso) => {
    aviso.classList.add("aviso-saliendo");
    aviso.addEventListener("animationend", () => {
      aviso.remove();
      if (!avisos.children.length) avisos.remove();
    }, { once: true });
  };

  [...avisos.children].forEach((aviso) => {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "aviso-cerrar";
    boton.setAttribute("aria-label", "Cerrar aviso");
    boton.textContent = "×";
    boton.addEventListener("click", () => cerrar(aviso));
    aviso.append(boton);

    let espera = setTimeout(() => cerrar(aviso), aviso.classList.contains("aviso-error") ? 9000 : 5000);
    aviso.addEventListener("pointerenter", () => clearTimeout(espera));
    aviso.addEventListener("pointerleave", () => {
      espera = setTimeout(() => cerrar(aviso), 2500);
    });
  });
}

const campanaViva = document.querySelector(".campana[data-contador]");

if (campanaViva && !document.querySelector("[data-nuevos], [data-bandeja][data-estado]")) {
  const consultar = async () => {
    if (document.hidden) return;
    try {
      const respuesta = await fetch(campanaViva.dataset.contador, { headers: { "X-Requested-With": "fetch" } });
      if (!respuesta.ok) return;
      const { avisos: cantidad } = await respuesta.json();
      if (Number(campanaViva.dataset.avisos) === cantidad) return;
      campanaViva.dataset.avisos = cantidad;
      campanaViva.setAttribute("aria-label", cantidad ? `Notificaciones: ${cantidad} sin leer` : "Notificaciones");
      let globo = campanaViva.querySelector(".campana-cantidad");
      if (!cantidad) return globo?.remove();
      if (!globo) {
        globo = document.createElement("span");
        globo.className = "campana-cantidad";
        campanaViva.append(globo);
      }
      globo.textContent = cantidad < 10 ? cantidad : "9+";
    } catch {
      // se reintenta en la próxima vuelta
    }
  };
  setInterval(consultar, 30000);
  document.addEventListener("visibilitychange", consultar);
}
