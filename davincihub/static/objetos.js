const formularioObjeto = document.querySelector("[data-form-objeto]");
if (formularioObjeto) {
  const modalidad = formularioObjeto.querySelector("[name=modalidad]");
  const campoPrecio = formularioObjeto.querySelector("[data-campo-precio]");
  const precio = campoPrecio.querySelector("input");
  const actualizarPrecio = () => {
    const venta = modalidad.value === "venta";
    campoPrecio.hidden = !venta;
    precio.disabled = !venta;
    precio.required = venta;
    precio.setCustomValidity("");
  };
  modalidad.addEventListener("change", actualizarPrecio);
  actualizarPrecio();
}
