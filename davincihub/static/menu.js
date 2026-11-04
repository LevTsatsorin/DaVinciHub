const botonMenu = document.querySelector("[data-menu-abrir]");
const panelMenu = document.getElementById("menu-movil");

function alternarMenu(abrir) {
  document.body.classList.toggle("menu-abierto", abrir);
  botonMenu.setAttribute("aria-expanded", String(abrir));
  panelMenu.setAttribute("aria-hidden", String(!abrir));
}

botonMenu.addEventListener("click", () => alternarMenu(true));
document.querySelectorAll("[data-menu-cerrar]").forEach((el) => {
  el.addEventListener("click", () => alternarMenu(false));
});
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") alternarMenu(false);
});

document.addEventListener("click", (evento) => {
  document.querySelectorAll(".menu-perfil[open], .chat-temas[open], .reporte-detalles[open]").forEach((menu) => {
    if (!menu.contains(evento.target)) menu.open = false;
  });
});
document.addEventListener("keydown", (evento) => {
  if (evento.key !== "Escape") return;
  document.querySelectorAll(".menu-perfil[open], .chat-temas[open], .reporte-detalles[open]").forEach((menu) => {
    menu.open = false;
  });
});

const filtrosFijos = document.querySelectorAll(".filtros-fijos");

if (filtrosFijos.length) {
  const marcarPegados = () => {
    const alto = document.querySelector(".barra")?.getBoundingClientRect().height ?? 0;
    filtrosFijos.forEach((filtro) => {
      const fijo = getComputedStyle(filtro).position === "sticky";
      filtro.classList.toggle("filtros-pegados", fijo && filtro.getBoundingClientRect().top <= alto + 0.5);
    });
  };
  window.addEventListener("scroll", marcarPegados, { passive: true });
  window.addEventListener("resize", marcarPegados);
  marcarPegados();
}
