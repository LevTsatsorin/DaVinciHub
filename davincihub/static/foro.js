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

const campoArchivo = document.querySelector("[data-archivo]");

if (campoArchivo) {
  const entrada = campoArchivo.querySelector("input[type=file]");
  const nombre = campoArchivo.querySelector("[data-archivo-nombre]");
  const vista = campoArchivo.querySelector("[data-archivo-vista]");
  const textoInicial = nombre.textContent;

  entrada.addEventListener("change", () => {
    const archivo = entrada.files[0];
    if (vista.src) URL.revokeObjectURL(vista.src);
    nombre.textContent = archivo ? archivo.name : textoInicial;
    campoArchivo.classList.toggle("campo-archivo-lleno", Boolean(archivo));
    vista.hidden = !archivo;
    if (archivo) vista.src = URL.createObjectURL(archivo);
  });
  ["dragenter", "dragover"].forEach((evento) => campoArchivo.addEventListener(evento, () => campoArchivo.classList.add("campo-archivo-arrastrando")));
  ["dragleave", "drop"].forEach((evento) => campoArchivo.addEventListener(evento, () => campoArchivo.classList.remove("campo-archivo-arrastrando")));
}
