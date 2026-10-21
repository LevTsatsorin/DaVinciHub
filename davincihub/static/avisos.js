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
