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
