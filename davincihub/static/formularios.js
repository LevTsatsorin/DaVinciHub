const fechaLegible = (valor) => {
  const [anio, mes, dia] = valor.split("-");
  return dia ? `${dia}/${mes}/${anio}` : valor;
};

const limite = (campo, valor) => (campo.type === "date" ? fechaLegible(valor) : valor);

const mensajeDeValidacion = (campo) => {
  const v = campo.validity;
  if (v.valueMissing) {
    if (campo.tagName === "SELECT") return "Elegí una opción.";
    if (campo.type === "checkbox") return "Marcá esta casilla para continuar.";
    return "Completá este campo.";
  }
  if (v.typeMismatch) {
    return campo.type === "email"
      ? "Ingresá un email válido, por ejemplo nombre@davinci.edu.ar."
      : "El formato no es válido.";
  }
  if (v.badInput) return campo.type === "number" ? "Ingresá un número." : "El valor no es válido.";
  if (v.rangeUnderflow) return `El mínimo es ${limite(campo, campo.min)}.`;
  if (v.rangeOverflow) return `El máximo es ${limite(campo, campo.max)}.`;
  if (v.stepMismatch) return "Ingresá un número entero.";
  if (v.tooShort) return `Usá al menos ${campo.minLength} caracteres.`;
  if (v.tooLong) return `Usá como máximo ${campo.maxLength} caracteres.`;
  if (v.patternMismatch) return campo.title || "El formato no es válido.";
  return "";
};

document.addEventListener("invalid", (evento) => {
  const campo = evento.target;
  campo.setCustomValidity("");
  if (!campo.validity.valid) campo.setCustomValidity(mensajeDeValidacion(campo));
}, true);

["input", "change"].forEach((tipo) => document.addEventListener(tipo, (evento) => {
  if (evento.target.setCustomValidity) evento.target.setCustomValidity("");
}, true));
