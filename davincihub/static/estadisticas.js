// Cambiar el período solo actualiza la vista de estadísticas.
document.querySelector('[data-periodo-estadisticas]')?.addEventListener('change', (evento) => {
  evento.target.form.requestSubmit();
});
