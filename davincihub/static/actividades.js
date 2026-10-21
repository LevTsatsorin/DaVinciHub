document.querySelectorAll("form[data-enviar-al-cambiar]").forEach((form) => {
  form.addEventListener("change", (evento) => {
    if (evento.target.name === "espacio" || evento.target.value) form.requestSubmit();
  });
});

const agenda = document.querySelector("[data-agenda]");

if (agenda) {
  let pedido = null;

  const cargar = async (url, empujar) => {
    pedido?.abort();
    const actual = new AbortController();
    pedido = actual;
    agenda.setAttribute("aria-busy", "true");
    try {
      const respuesta = await fetch(url, { headers: { "X-Requested-With": "fetch" }, signal: actual.signal });
      if (!respuesta.ok) throw new Error(respuesta.status);
      const pagina = new DOMParser().parseFromString(await respuesta.text(), "text/html");
      const nueva = pagina.querySelector("[data-agenda]");
      if (!nueva) throw new Error("sin agenda");
      agenda.innerHTML = nueva.innerHTML;
      if (empujar) history.pushState({ agenda: true }, "", url);
    } catch (error) {
      if (error.name !== "AbortError") window.location.href = url;
    } finally {
      if (pedido === actual) {
        pedido = null;
        agenda.removeAttribute("aria-busy");
      }
    }
  };

  agenda.addEventListener("click", (evento) => {
    const enlace = evento.target.closest("a[href]");
    if (!enlace || !enlace.closest(".calendario, .paginacion, .lista-actividades-cabecera")) return;
    if (evento.metaKey || evento.ctrlKey || evento.shiftKey) return;
    evento.preventDefault();
    const lista = agenda.querySelector(".lista-actividades");
    const desdePaginacion = Boolean(enlace.closest(".paginacion"));
    cargar(enlace.href, true).then(() => {
      if (desdePaginacion && lista && lista.getBoundingClientRect().top < 0) {
        agenda.querySelector(".lista-actividades").scrollIntoView({ block: "start" });
      }
    });
  });

  window.addEventListener("popstate", () => cargar(window.location.href, false));
}
