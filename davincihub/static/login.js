document.querySelectorAll("[data-password-toggle]").forEach((boton) => {
    boton.addEventListener("click", () => {
        const campo = document.getElementById(
            boton.dataset.passwordToggle
        );

        const mostrar = campo.type === "password";

        campo.type = mostrar ? "text" : "password";
        boton.setAttribute("aria-pressed", String(mostrar));
        boton.setAttribute(
            "aria-label",
            mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
        );
    });
});


