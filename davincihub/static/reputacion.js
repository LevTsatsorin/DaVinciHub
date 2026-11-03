document.querySelectorAll('[data-reputacion-rango]').forEach((barra) => {
  const numero = barra.closest('.reputacion-selector').querySelector('[data-puntuacion]');
  const actualizar = () => {
    numero.textContent = barra.value;
    barra.style.setProperty('--avance', `${((Number(barra.value) - 1) / 4) * 100}%`);
  };
  barra.addEventListener('input', actualizar);
  actualizar();
});
