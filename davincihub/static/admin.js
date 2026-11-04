const formEspacio = document.querySelector("form[data-confirmar-salida]");
const dialogoSalir = document.getElementById("dialogo-salir");
const dialogoConfirmar = document.getElementById("dialogo-confirmar");

let marcarCambios = () => {};

if (formEspacio) {
  const estadoCambios = formEspacio.querySelector("[data-estado-cambios]");
  const instantanea = () => {
    const datos = new FormData(formEspacio);
    datos.delete("csrf_token");
    datos.delete("siguiente");
    return new URLSearchParams(datos).toString();
  };
  const inicial = instantanea();
  let hayCambios = false;
  let saliendo = false;
  let destino = null;

  marcarCambios = () => {
    hayCambios = instantanea() !== inicial;
    formEspacio.classList.toggle("con-cambios", hayCambios);
    estadoCambios.textContent = hayCambios ? "Cambios sin guardar" : "Sin cambios";
  };

  formEspacio.addEventListener("input", marcarCambios);
  formEspacio.addEventListener("change", marcarCambios);
  formEspacio.addEventListener("submit", () => {
    saliendo = true;
  });

  window.addEventListener("beforeunload", (evento) => {
    if (hayCambios && !saliendo) {
      evento.preventDefault();
      evento.returnValue = "";
    }
  });

  document.addEventListener("click", (evento) => {
    const enlace = evento.target.closest("a[href]");
    if (!enlace || !hayCambios || saliendo) return;
    if (enlace.target || evento.metaKey || evento.ctrlKey || evento.shiftKey) return;
    const url = new URL(enlace.href, location.href);
    if (url.origin !== location.origin) return;
    evento.preventDefault();
    destino = url.pathname + url.search;
    dialogoSalir.showModal();
  });

  dialogoSalir.querySelector("[data-salir-seguir]").addEventListener("click", () => {
    dialogoSalir.close();
  });
  dialogoSalir.querySelector("[data-salir-descartar]").addEventListener("click", () => {
    saliendo = true;
    location.href = destino;
  });
  dialogoSalir.querySelector("[data-salir-guardar]").addEventListener("click", () => {
    formEspacio.elements.siguiente.value = destino;
    dialogoSalir.close();
    formEspacio.requestSubmit();
  });
}

const listaFranjas = document.querySelector("[data-lista-franjas]");

if (listaFranjas) {
  const plantilla = document.querySelector("[data-plantilla-franja]");
  const sinFranjas = document.querySelector("[data-sin-franjas]");
  const actualizarVacio = () => {
    sinFranjas.hidden = listaFranjas.children.length > 0;
  };

  document.querySelector("[data-agregar-franja]").addEventListener("click", () => {
    const fila = plantilla.content.firstElementChild.cloneNode(true);
    const anterior = listaFranjas.lastElementChild;
    if (anterior) {
      const dia = Number(anterior.querySelector("select").value);
      fila.querySelector("select").value = String((dia + 1) % 7);
      fila.querySelector('[name="abre"]').value = anterior.querySelector('[name="abre"]').value;
      fila.querySelector('[name="cierra"]').value = anterior.querySelector('[name="cierra"]').value;
    }
    listaFranjas.append(fila);
    fila.querySelector("select").focus();
    actualizarVacio();
    marcarCambios();
  });

  listaFranjas.addEventListener("click", (evento) => {
    const quitar = evento.target.closest("[data-quitar-franja]");
    if (!quitar) return;
    quitar.closest("li").remove();
    actualizarVacio();
    marcarCambios();
  });
}

if (dialogoConfirmar) {
  let formPendiente = null;
  const aceptar = dialogoConfirmar.querySelector("[data-dialogo-aceptar]");
  const cancelar = dialogoConfirmar.querySelector("[data-dialogo-cancelar]");

  document.querySelectorAll("form[data-confirmar]").forEach((form) => {
    form.addEventListener("submit", (evento) => {
      if (form.dataset.confirmado) return;
      evento.preventDefault();
      formPendiente = form;
      dialogoConfirmar.querySelector("#dialogo-confirmar-titulo").textContent = form.dataset.confirmar;
      dialogoConfirmar.querySelector("#dialogo-confirmar-texto").textContent =
        form.dataset.confirmarTexto || "";
      aceptar.textContent = form.dataset.confirmarBoton || "Confirmar";
      const positivo = form.dataset.confirmarTono === "positivo";
      dialogoConfirmar.querySelector("[data-icono-peligro]").hidden = positivo;
      dialogoConfirmar.querySelector("[data-icono-ok]").hidden = !positivo;
      aceptar.classList.toggle("boton-peligro", !positivo);
      aceptar.classList.toggle("boton-primario", positivo);
      cancelar.textContent = form.dataset.confirmarVolver || "Cancelar";
      dialogoConfirmar.showModal();
    });
  });

  cancelar.addEventListener("click", () => {
    dialogoConfirmar.close();
  });
  aceptar.addEventListener("click", () => {
    formPendiente.dataset.confirmado = "1";
    dialogoConfirmar.close();
    formPendiente.requestSubmit();
  });
}

document.querySelectorAll("dialog.dialogo").forEach((dialogo) => {
  dialogo.addEventListener("click", (evento) => {
    if (evento.target === dialogo) dialogo.close();
  });
});
