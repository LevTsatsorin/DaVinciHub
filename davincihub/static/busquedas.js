const formularioBusqueda = document.querySelector("[data-form-busqueda]");
if (formularioBusqueda) {
  const modalidadBusqueda = formularioBusqueda.querySelector("[name=modalidad]");
  const campoPresupuesto = formularioBusqueda.querySelector("[data-campo-presupuesto]");
  const presupuesto = campoPresupuesto.querySelector("input");
  const actualizarPresupuesto = () => {
    const compra = modalidadBusqueda.value === "venta";
    campoPresupuesto.hidden = !compra;
    presupuesto.disabled = !compra;
    presupuesto.setCustomValidity("");
  };
  modalidadBusqueda.addEventListener("change", actualizarPresupuesto);
  actualizarPresupuesto();
}
