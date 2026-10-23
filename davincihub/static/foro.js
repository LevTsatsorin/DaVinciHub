const selectorCarrera = document.querySelector("[data-foro-carrera]");
const selectorMateria = document.querySelector("[data-foro-materia]");

if (selectorCarrera && selectorMateria) {
  const filtrarMaterias = () => {
    const carreraId = selectorCarrera.value;
    let seleccionDisponible = false;

    for (const opcion of selectorMateria.options) {
      if (!opcion.value) continue;
      opcion.hidden = opcion.dataset.carrera !== carreraId;
      opcion.disabled = opcion.hidden;
      if (opcion.selected && !opcion.hidden) seleccionDisponible = true;
    }

    if (!seleccionDisponible) selectorMateria.value = "";
  };

  selectorCarrera.addEventListener("change", filtrarMaterias);
  filtrarMaterias();
}
