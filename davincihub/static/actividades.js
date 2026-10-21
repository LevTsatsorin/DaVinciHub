document.querySelectorAll("form[data-enviar-al-cambiar]").forEach((form) => {
  form.addEventListener("change", (evento) => {
    if (evento.target.name === "espacio" || evento.target.value) form.requestSubmit();
  });
});
