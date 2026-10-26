PREGUNTAS = [
    {
        "autor": "cami",
        "carrera": "multimedial",
        "materia": "Lógica de la Programación",
        "titulo": "No me sale el while del TP de adivinar el número, se queda en loop infinito",
        "cuerpo": (
            "Hola! Estoy con el TP 2 de Lógica y no entiendo qué estoy haciendo mal. La consigna es:\n\n"
            "1. La compu elige un número al azar entre 1 y 100.\n"
            "2. El usuario tiene que adivinarlo.\n"
            "3. Después de cada intento hay que decir si el número es mayor o menor.\n"
            "4. Cuando acierta, mostrar en cuántos intentos lo logró.\n\n"
            "Esto es lo que tengo:\n\n"
            "import random\n\n"
            "secreto = random.randint(1, 100)\n"
            "intento = input('Adiviná el número: ')\n"
            "intentos = 0\n\n"
            "while intento != secreto:\n"
            "    if intento < secreto:\n"
            "        print('Es mayor')\n"
            "    else:\n"
            "        print('Es menor')\n"
            "    intentos = intentos + 1\n\n"
            "print('Ganaste en', intentos, 'intentos')\n\n"
            "Cuando lo corro en VS Code me pide el número una sola vez y después me tira 'Es mayor' para siempre, "
            "o a veces me tira error: TypeError: '<' not supported between instances of 'str' and 'int'. "
            "Probé cambiar el < por > y obvio no cambió nada jaja. ¿Alguien me explica qué pasa? La entrega es el viernes."
        ),
        "creado": "2026-09-28T13:15:00+00:00",
        "respuestas": [
            {
                "autor": "joaco",
                "cuerpo": (
                    "Tenés dos problemas distintos y los dos son re clásicos:\n\n"
                    "1. input() siempre devuelve texto (str). Entonces estás comparando '50' con 37, y Python no sabe si un texto "
                    "es menor que un número: de ahí el TypeError. Lo convertís con int(input(...)).\n\n"
                    "2. El loop infinito es porque el input está afuera del while. Le preguntás una sola vez, y como intento nunca "
                    "cambia adentro del bucle, la condición es verdadera para siempre.\n\n"
                    "Quedaría algo así:\n\n"
                    "secreto = random.randint(1, 100)\n"
                    "intentos = 0\n"
                    "intento = None\n\n"
                    "while intento != secreto:\n"
                    "    intento = int(input('Adiviná el número: '))\n"
                    "    intentos += 1\n"
                    "    if intento < secreto:\n"
                    "        print('Es mayor')\n"
                    "    elif intento > secreto:\n"
                    "        print('Es menor')\n\n"
                    "print('Ganaste en', intentos, 'intentos')\n\n"
                    "Ojo que puse elif para que cuando acierte no te diga 'Es menor'. Y el contador lo sumo apenas pide el número, "
                    "así el intento ganador también cuenta."
                ),
                "creado": "2026-09-28T14:02:00+00:00",
                "aceptada": True,
                "utiles": ["cami", "mica", "nacho", "mariangeles", "valen"],
                "hilo": [
                    {"autor": "cami", "cuerpo": "Me salvaste!! Ahora entiendo por qué se colgaba. Una pregunta: ¿para qué es el intento = None antes del while?", "creado": "2026-09-28T14:20:00+00:00"},
                    {"autor": "joaco", "cuerpo": "Porque la variable tiene que existir antes de la primera comparación del while. Con None te asegurás de que sea distinta del secreto y entre al bucle sí o sí.", "creado": "2026-09-28T14:31:00+00:00"},
                ],
            },
            {
                "autor": "mica",
                "cuerpo": "Sumo un detalle: si alguien escribe una letra, int() te tira ValueError y se corta el programa. En mi comisión el profe no lo pedía, pero si querés quedar bien podés envolverlo en un try/except y volver a pedir el número.",
                "creado": "2026-09-28T15:10:00+00:00",
                "utiles": ["cami", "joaco"],
            },
            {
                "autor": "nacho",
                "cuerpo": "Alto dato lo del input adentro del while. A mí me pasó lo mismo el año pasado y por no preguntar casi recurso jaja",
                "creado": "2026-09-28T18:45:00+00:00",
                "utiles": [],
            },
        ],
    },
    {
        "autor": "ludmi",
        "carrera": "cine",
        "materia": "Iluminación y Cámara",
        "titulo": "Me aparecen franjas oscuras que se mueven al filmar con luces LED",
        "cuerpo": "Estábamos grabando el ejercicio de clave baja en casa con dos paneles LED baratos y una lámpara de techo, y en el material aparecen unas franjas oscuras que suben y bajan por la imagen. Grabé con una Canon T7 en 1080p a 60 fps con obturación a 1/125. En el visor no se notaba tanto, pero en la compu se ve horrible. ¿Es la cámara o las luces?",
        "creado": "2026-09-28T20:30:00+00:00",
        "respuestas": [
            {
                "autor": "franco",
                "cuerpo": (
                    "Es flicker, y pasa por la combinación de luces y obturación. En Argentina la red eléctrica es de 50 Hz, así que "
                    "muchas luces (sobre todo LED baratos y tubos) parpadean 100 veces por segundo. Si tu velocidad de obturación no "
                    "calza con ese ciclo, cada fotograma agarra la luz en un momento distinto del parpadeo y aparecen las bandas.\n\n"
                    "Qué podés hacer:\n"
                    "- Usar 1/50 o 1/100. A 60 fps te conviene 1/100, aunque si el proyecto lo permite pensá en 25 o 50 fps, que es lo natural con 50 Hz.\n"
                    "- Si querés 24 fps, 1/50 es lo más cercano a la regla de los 180° y además no parpadea.\n"
                    "- Si el panel tiene regulación de intensidad, probá ponerlo al máximo: los dimmers por PWM suelen empeorar el flicker.\n"
                    "- La T7 no tiene anti-flicker en video, así que es todo a mano.\n\n"
                    "A 1/125 con luces de 50 Hz es casi seguro que te salgan franjas."
                ),
                "creado": "2026-09-28T22:05:00+00:00",
                "aceptada": True,
                "utiles": ["ludmi", "martu"],
            },
            {
                "autor": "martu",
                "cuerpo": "Confirmo, me pasó en el ejercicio de Dirección I con unas tiras LED del cuarto. Cambié a 1/50 y desapareció. Lo que no se arregla tan fácil es si ya lo filmaste: hay efectos de deflicker en Resolve, pero en la versión gratuita no viene.",
                "creado": "2026-09-29T09:12:00+00:00",
                "utiles": ["ludmi"],
                "hilo": [
                    {"autor": "ludmi", "cuerpo": "Uh, lo filmé todo así. Creo que vuelvo a grabar el finde, gracias a los dos!", "creado": "2026-09-29T10:00:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "gonza",
        "carrera": "sistemas",
        "materia": "Introducción a la Programación",
        "titulo": "ValueError cuando el usuario deja el input vacío en Python",
        "cuerpo": "Tengo un programa que pide la edad con edad = int(input('Edad: ')). Si alguien aprieta Enter sin escribir nada me tira ValueError: invalid literal for int() with base 10: ''. ¿Cómo hago para que vuelva a preguntar en vez de cortarse? Vimos while pero todavía no try/except.",
        "creado": "2026-09-29T11:40:00+00:00",
        "respuestas": [
            {
                "autor": "nico",
                "cuerpo": (
                    "Tenés dos caminos. Si no vieron try/except, podés validar el texto antes de convertirlo:\n\n"
                    "texto = input('Edad: ')\n"
                    "while not texto.isdigit():\n"
                    "    print('Ingresá un número válido')\n"
                    "    texto = input('Edad: ')\n"
                    "edad = int(texto)\n\n"
                    "isdigit() devuelve False para el string vacío y para cosas como 'abc', así que el while sigue preguntando. "
                    "La limitación es que tampoco acepta negativos ni decimales, pero para una edad está perfecto.\n\n"
                    "La versión con try/except es la que vas a usar más adelante, porque es más general:\n\n"
                    "while True:\n"
                    "    try:\n"
                    "        edad = int(input('Edad: '))\n"
                    "        break\n"
                    "    except ValueError:\n"
                    "        print('Ingresá un número válido')\n\n"
                    "Si usás esta en el TP, tené clara la explicación por si el profe pregunta."
                ),
                "creado": "2026-09-29T12:30:00+00:00",
                "aceptada": True,
                "utiles": ["gonza", "ivan", "euge", "cami"],
            },
            {
                "autor": "ivan",
                "cuerpo": "Lo del isdigit es lo que nos aceptaron el año pasado en el parcial, tranqui.",
                "creado": "2026-09-29T14:15:00+00:00",
                "utiles": ["gonza"],
            },
        ],
    },
    {
        "autor": "tomi",
        "carrera": "grafico",
        "materia": "Tratamiento Digital de la Imagen I",
        "titulo": "Imprimí el afiche y los colores salieron re apagados, en pantalla se veían bien",
        "cuerpo": "Hice un afiche en Photoshop para el TP de color, con un turquesa y un naranja bien saturados. Lo llevé a imprimir a una copistería cerca de la escuela y salió todo como lavado, el turquesa casi gris. El archivo estaba en RGB a 72 dpi porque así se creó el documento por defecto. ¿Qué tendría que haber hecho?",
        "creado": "2026-09-29T16:00:00+00:00",
        "respuestas": [
            {
                "autor": "delfi",
                "cuerpo": (
                    "Ahí tenés dos temas mezclados.\n\n"
                    "Color: la pantalla trabaja en RGB, que tiene una gama más amplia que la tinta. Muchos turquesas y naranjas "
                    "eléctricos directamente no existen en CMYK, entonces la impresora los aproxima como puede y salen apagados. "
                    "Lo ideal es trabajar desde el principio en CMYK (Edición > Convertir en perfil, por ejemplo Coated FOGRA39 si es "
                    "offset, o el perfil que te pase la imprenta) y ajustar los colores mirando ese resultado. También sirve "
                    "Vista > Prueba de colores (Ctrl+Y) para simular cómo va a salir sin convertir.\n\n"
                    "Resolución: 72 dpi es para pantalla. Para impresión trabajá a 300 dpi al tamaño final. Si agrandás un archivo "
                    "de 72 a 300 después, no ganás detalle, solo píxeles interpolados.\n\n"
                    "Tip extra: preguntá en la copistería qué les conviene recibir. Las láser digitales a veces imprimen mejor un PDF "
                    "en RGB que un CMYK mal convertido, y preguntar ahorra plata."
                ),
                "creado": "2026-09-29T17:20:00+00:00",
                "aceptada": True,
                "utiles": ["tomi", "sofia", "abril", "mica", "valen", "cami", "nacho"],
            },
            {
                "autor": "sofia",
                "cuerpo": "Me pasó en primero con un violeta. Sumale que la pantalla de la notebook con el brillo al palo engaña un montón: bajale el brillo cuando revises colores.",
                "creado": "2026-09-29T19:05:00+00:00",
                "utiles": ["tomi", "delfi"],
            },
            {
                "autor": "abril",
                "cuerpo": "Posta, me pasó lo mismo",
                "creado": "2026-09-30T08:40:00+00:00",
                "utiles": [],
            },
        ],
    },
    {
        "autor": "lauti",
        "carrera": "web",
        "materia": "Maquetado y Desarrollo Web",
        "titulo": "¿Flexbox o Grid para la galería de cards del TP?",
        "cuerpo": "Tengo que maquetar una galería de 9 cards que en desktop sean 3 columnas, en tablet 2 y en celu 1. La empecé con flexbox y flex-wrap, pero la última fila me queda con las cards estiradas o desalineadas cuando sobran. Vi que algunos lo hacen con grid. ¿Cuál conviene y por qué? No quiero llenar todo de media queries.",
        "creado": "2026-09-30T10:10:00+00:00",
        "respuestas": [
            {
                "autor": "pili",
                "cuerpo": "Yo lo hice con grid y fue mucho más fácil, pero no sé explicarte bien por qué jaja",
                "creado": "2026-09-30T10:40:00+00:00",
                "utiles": ["lauti"],
            },
            {
                "autor": "mai",
                "cuerpo": (
                    "Para una grilla de cards, grid. La regla que uso: flexbox para alinear cosas en una sola dirección (un navbar, "
                    "los botones de una card) y grid cuando querés controlar filas y columnas a la vez.\n\n"
                    "Lo que te pasa con flex-wrap es que cada fila reparte el espacio por su cuenta, entonces si en la última quedan "
                    "dos cards con flex-grow: 1, se estiran para llenar. En grid las columnas son de toda la grilla, así que la "
                    "última fila respeta el mismo ancho.\n\n"
                    "Y sin media queries:\n\n"
                    ".galeria {\n"
                    "  display: grid;\n"
                    "  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));\n"
                    "  gap: 24px;\n"
                    "}\n\n"
                    "auto-fit mete tantas columnas como entren con un mínimo de 260px. Ajustá ese número hasta que te dé 3 en desktop, "
                    "2 en tablet y 1 en celu. Si el profe pide exactamente esos cortes, ahí sí ponés dos media queries con "
                    "repeat(3, 1fr) y repeat(2, 1fr)."
                ),
                "creado": "2026-09-30T11:25:00+00:00",
                "aceptada": True,
                "utiles": ["lauti", "pili", "kevin", "fede", "nico", "mica", "valen", "euge"],
                "hilo": [
                    {"autor": "lauti", "cuerpo": "Lo probé y anduvo a la primera. ¿auto-fit y auto-fill no son lo mismo?", "creado": "2026-09-30T11:50:00+00:00"},
                    {"autor": "mai", "cuerpo": "Casi. Con pocas cards se nota: auto-fill deja columnas vacías reservadas y auto-fit las colapsa para que las cards se estiren. Con tus 9 cards no vas a ver diferencia.", "creado": "2026-09-30T12:05:00+00:00"},
                ],
            },
            {
                "autor": "kevin",
                "cuerpo": "Consulta relacionada: ¿gap funciona también en flexbox? Siempre usé margin.",
                "creado": "2026-09-30T13:30:00+00:00",
                "utiles": [],
                "hilo": [
                    {"autor": "fede", "cuerpo": "Sí, gap anda en flexbox en todos los navegadores actuales. Te ahorra el lío de sacarle el margin a la última card.", "creado": "2026-09-30T13:45:00+00:00"},
                ],
            },
            {
                "autor": "fede",
                "cuerpo": "Sumo: si las cards tienen distinto largo de texto y querés que el botón quede siempre abajo, adentro de cada card usá flex en columna y margin-top: auto en el botón. Grid afuera, flex adentro: es la combinación que más uso.",
                "creado": "2026-09-30T14:00:00+00:00",
                "utiles": ["lauti", "mai", "pili"],
            },
            {
                "autor": "nico",
                "cuerpo": "No es mi carrera, pero en Programación Web I nos pasó igual. Abrí las DevTools de Chrome, seleccioná el contenedor y activá el overlay de grid: te dibuja las líneas y ves enseguida qué está pasando.",
                "creado": "2026-09-30T16:20:00+00:00",
                "utiles": ["lauti", "kevin"],
            },
            {
                "autor": "mica",
                "cuerpo": "Alto dato el overlay, no lo conocía. Me viene bárbaro para Maquetado en Multimedial también.",
                "creado": "2026-09-30T19:10:00+00:00",
                "utiles": [],
            },
            {
                "autor": "mariangeles",
                "cuerpo": "Me guardo este post para cuando me toque Maquetado el cuatri que viene jaja",
                "creado": "2026-10-01T09:00:00+00:00",
                "utiles": [],
            },
        ],
    },
    {
        "autor": "juli",
        "carrera": "animacion",
        "materia": "Principios de la Animación",
        "titulo": "La pelotita que rebota se ve robótica, ¿qué le falta?",
        "cuerpo": "Estoy haciendo el ejercicio de la pelota rebotando en Krita a 24 fps. Hice 5 rebotes que van bajando de altura, pero se ve todo a la misma velocidad, como flotando. Ya le puse un poco de squash cuando toca el piso.",
        "creado": "2026-09-30T18:00:00+00:00",
        "respuestas": [
            {
                "autor": "mateo",
                "cuerpo": (
                    "Lo que te falta casi seguro es el spacing, no el timing. Revisá esto:\n\n"
                    "- Cerca del punto más alto los dibujos tienen que estar muy juntos (la pelota frena) y cerca del piso muy "
                    "separados (va rápido). Si los espaciaste parejo, se ve flotante.\n"
                    "- Cada rebote dura menos que el anterior, no solo es más bajo. Si el primero tarda 12 cuadros, el siguiente puede "
                    "andar por 9, después 7, y así.\n"
                    "- El squash va justo en el cuadro de contacto, y en los cuadros de antes y después va stretch en el sentido del "
                    "movimiento. Sin stretch el squash se lee como un error.\n"
                    "- Mantené el volumen: si se aplasta a lo ancho, que se achique de alto en la misma proporción.\n\n"
                    "Dibujá primero los arcos y las posiciones extremas, y recién después los intermedios. En Krita activá el papel "
                    "cebolla con 2 o 3 cuadros para ver el espaciado."
                ),
                "creado": "2026-09-30T19:40:00+00:00",
                "aceptada": True,
                "utiles": ["juli", "benja", "cami", "lucia"],
            },
            {
                "autor": "benja",
                "cuerpo": "Lo del stretch antes del contacto me cambió la vida en primero. Otra: no cortes en el último rebote, terminá con la pelota rodando un poco, queda más natural.",
                "creado": "2026-10-01T10:15:00+00:00",
                "utiles": ["juli"],
            },
        ],
    },
    {
        "autor": "tomas",
        "carrera": "videojuegos",
        "materia": "Elementos de Matemática",
        "titulo": "¿Para qué sirve normalizar un vector? En diagonal mi personaje va más rápido",
        "cuerpo": "En el ejercicio de movimiento en Unity, si aprieto W y D al mismo tiempo el personaje se mueve más rápido que yendo derecho. El profe dijo 'normalizalo' y lo hice, funciona, pero no entiendo qué hace matemáticamente y lo toman en el parcial.",
        "creado": "2026-10-01T12:00:00+00:00",
        "respuestas": [
            {
                "autor": "flor",
                "cuerpo": (
                    "Pensalo con números. Si apretás solo D, la dirección es (1, 0) y su longitud es 1. Si apretás W y D, es (1, 1), "
                    "y su longitud por Pitágoras es raíz de (1² + 1²) = 1,41. Como multiplicás esa dirección por la velocidad, en "
                    "diagonal vas un 41% más rápido.\n\n"
                    "Normalizar es dividir el vector por su propia longitud: (1, 1) / 1,41 = (0,707; 0,707). Sigue apuntando para el "
                    "mismo lado pero ahora mide 1. En Unity es input.normalized.\n\n"
                    "Para el parcial suelen pedir justamente eso: calcular el módulo, dividir cada componente y verificar que el "
                    "resultado mida 1. Un detalle: con joystick conviene usar Vector2.ClampMagnitude(input, 1) en vez de normalized, "
                    "porque si no el personaje va siempre a máxima velocidad aunque inclines el stick un poquito."
                ),
                "creado": "2026-10-01T13:10:00+00:00",
                "aceptada": True,
                "utiles": ["tomas", "santi", "rocio", "jo", "agus"],
                "hilo": [
                    {"autor": "tomas", "cuerpo": "Ahora sí lo entendí, con el ejemplo del 1,41 se ve clarísimo. Gracias Flor!", "creado": "2026-10-01T13:30:00+00:00"},
                ],
            },
            {
                "autor": "santi",
                "cuerpo": "Re útil. Yo lo había resuelto multiplicando por 0.7 a mano jaja",
                "creado": "2026-10-01T15:00:00+00:00",
                "utiles": [],
                "hilo": [
                    {"autor": "flor", "cuerpo": "Con teclado zafa, pero cuando agregues joystick se te rompe. Mejor usar normalized.", "creado": "2026-10-01T15:20:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "mica",
        "carrera": "multimedial",
        "materia": "Experiencia de Usuario",
        "titulo": "En Figma el prototipo no respeta el scroll, se mueve toda la pantalla",
        "cuerpo": "Estoy armando el prototipo de la app de turnos para UX. Quiero que el header y la barra de navegación de abajo queden fijos y solo scrollee la lista del medio, pero cuando lo pruebo en Present se mueve todo junto, incluso la barra. El frame es de iPhone 14 y la lista se pasa del alto de la pantalla.",
        "creado": "2026-10-01T17:30:00+00:00",
        "respuestas": [
            {
                "autor": "lucia",
                "cuerpo": (
                    "Lo tuve que hacer en el mismo TP. Son dos cosas:\n\n"
                    "1. Seleccioná el header y la barra de abajo, y en el panel de Prototype, en Scroll behavior > Position, poné "
                    "Fixed (stay in place). Tienen que estar arriba de la lista en el orden de capas, si no la lista les pasa por encima.\n\n"
                    "2. Si querés que scrollee solo una parte, metela en un frame propio con el alto visible (lo que queda entre header "
                    "y nav), activá Clip content y en Overflow poné Vertical. Así el frame de la pantalla tiene el alto del celular y la "
                    "lista scrollea por adentro.\n\n"
                    "Si el frame principal mide más de 844 px de alto, Figma asume que toda la pantalla scrollea. Dejalo en el alto del dispositivo."
                ),
                "creado": "2026-10-01T18:40:00+00:00",
                "aceptada": True,
                "utiles": ["mica", "valen", "cami", "nacho"],
                "hilo": [
                    {"autor": "mica", "cuerpo": "Era eso! Tenía el frame estirado a 1600 de alto. Gracias Lu, te debo una.", "creado": "2026-10-01T19:00:00+00:00"},
                ],
            },
            {
                "autor": "valen",
                "cuerpo": "Guardado. Una más: si usás auto layout en la lista, cuando agregás items el frame interno crece solo y no se rompe el scroll.",
                "creado": "2026-10-01T20:15:00+00:00",
                "utiles": ["mica"],
            },
        ],
    },
    {
        "autor": "bauti",
        "carrera": "marketing",
        "materia": "Posicionamiento Web",
        "titulo": "Mi página no aparece en Google aunque la publiqué hace dos semanas",
        "cuerpo": "Para el TP de SEO armamos un sitio en Wix de una pastelería ficticia. Lo busco por el nombre exacto y no aparece nada. ¿Hay que pagar algo para que Google lo indexe?",
        "creado": "2026-10-02T10:00:00+00:00",
        "respuestas": [
            {
                "autor": "sol",
                "cuerpo": (
                    "No hay que pagar. Que no aparezca a las dos semanas es normal si nadie le avisó a Google que existe. Pasos:\n\n"
                    "1. Entrá a Google Search Console, agregá la propiedad con la URL del sitio y verificala (Wix tiene un asistente que lo hace casi solo).\n"
                    "2. Mandá el sitemap: en Wix es tudominio/sitemap.xml.\n"
                    "3. Usá Inspección de URLs con la home y apretá Solicitar indexación.\n"
                    "4. Revisá que en la configuración de SEO de Wix la página esté habilitada para aparecer en buscadores. Con los sitios de prueba pasa más de lo que pensás.\n\n"
                    "Después de eso puede tardar de unos días a un par de semanas. Para el TP, una captura de Search Console con la página indexada suma un montón."
                ),
                "creado": "2026-10-02T11:30:00+00:00",
                "aceptada": True,
                "utiles": ["bauti", "cande", "mai"],
            },
            {
                "autor": "cande",
                "cuerpo": "Lo del punto 4 era lo nuestro! Estaba desactivado en el sitio del grupo. Gracias Sol",
                "creado": "2026-10-02T13:00:00+00:00",
                "utiles": ["bauti"],
            },
            {
                "autor": "mai",
                "cuerpo": "Desde web sumo: fijate también que el title y la meta description de la home no queden con lo que trae la plantilla. No cambia que te indexe, pero sí cómo aparecés en los resultados.",
                "creado": "2026-10-02T15:40:00+00:00",
                "utiles": ["sol", "bauti"],
            },
        ],
    },
    {
        "autor": "agus",
        "carrera": "videojuegos",
        "materia": "Programación II",
        "titulo": "NullReferenceException al llamar a GetComponent en Start",
        "cuerpo": "Tengo un script Jugador que en Start hace vida = GetComponent<Vida>(); y después en Update llamo a vida.RecibirDanio(10). Me tira NullReferenceException: Object reference not set to an instance of an object en esa línea. El script Vida está en el mismo prefab, lo juro jaja.",
        "creado": "2026-10-03T09:30:00+00:00",
        "respuestas": [
            {
                "autor": "nico",
                "cuerpo": (
                    "Ese error significa que vida quedó en null, o sea que GetComponent no encontró nada en ese GameObject. Lo más común:\n\n"
                    "- El script Vida está en un hijo del prefab y no en el objeto raíz donde está Jugador. GetComponent busca solo en "
                    "el mismo objeto; para hijos es GetComponentInChildren<Vida>().\n"
                    "- Hay dos Jugador en la escena y uno no tiene Vida (pasa cuando arrastrás el script a otro objeto sin querer).\n"
                    "- La clase se llama distinto que el archivo y Unity no la reconoce como componente.\n\n"
                    "Para confirmarlo poné Debug.Log(vida == null, gameObject); después del GetComponent. Al hacer clic en el mensaje de "
                    "la consola, Unity te resalta el objeto culpable. También podés agregar [RequireComponent(typeof(Vida))] arriba de la "
                    "clase para que Unity no te deje tener uno sin el otro."
                ),
                "creado": "2026-10-03T10:20:00+00:00",
                "aceptada": True,
                "utiles": ["agus", "thiago", "flor", "santi", "tomas"],
            },
            {
                "autor": "flor",
                "cuerpo": "Lo de Nico. Otra alternativa que usamos mucho en Programación II: declarás [SerializeField] private Vida vida; y lo arrastrás desde el inspector. Así ves de un vistazo si está asignado.",
                "creado": "2026-10-03T11:05:00+00:00",
                "utiles": ["agus", "nico"],
                "hilo": [
                    {"autor": "agus", "cuerpo": "Era un hijo! El script estaba en el modelo y no en el padre. Gracias a los dos.", "creado": "2026-10-03T11:30:00+00:00"},
                ],
            },
            {
                "autor": "thiago",
                "cuerpo": "Posta, me pasó lo mismo la semana pasada",
                "creado": "2026-10-03T12:00:00+00:00",
                "utiles": [],
            },
        ],
    },
    {
        "autor": "sofia",
        "carrera": "grafico",
        "materia": "Tipografía",
        "titulo": "Diferencia entre kerning métrico y óptico en Illustrator",
        "cuerpo": "Estoy armando un logotipo con la palabra VALTO en una sans bold y entre la V y la A queda un hueco enorme. En Illustrator el kerning está en Métrico. Vi que hay una opción Óptico. ¿Cuál se usa? ¿Lo tengo que corregir a mano igual?",
        "creado": "2026-10-04T14:00:00+00:00",
        "respuestas": [
            {
                "autor": "delfi",
                "cuerpo": (
                    "Métrico usa las tablas de pares que trae la fuente (el diseñador definió cuánto acercar VA, To, etc). Óptico ignora "
                    "eso y calcula el espacio según la forma de las letras. Para texto corrido, métrico suele andar mejor si la fuente es "
                    "buena; óptico sirve cuando la fuente tiene un kerning pobre o cuando mezclás dos tipografías.\n\n"
                    "Pero en un logotipo siempre se corrige a mano, ninguno de los dos alcanza. Poné el cursor entre la V y la A y usá "
                    "Alt + flechas (Option en Mac) para ajustar de a 20 unidades. Truco: mirá el logo dado vuelta o desenfocado, así "
                    "juzgás las manchas de blanco y no las letras.\n\n"
                    "Cuando lo tengas, pasalo a contornos en una copia, así no depende de que la fuente esté instalada."
                ),
                "creado": "2026-10-04T15:30:00+00:00",
                "aceptada": True,
                "utiles": ["sofia", "abril", "tomi"],
                "hilo": [
                    {"autor": "sofia", "cuerpo": "¿El tracking lo toco antes o después del kerning?", "creado": "2026-10-04T15:50:00+00:00"},
                    {"autor": "delfi", "cuerpo": "Primero el tracking general, para definir si el logo es más abierto o más cerrado. Después el kerning par por par.", "creado": "2026-10-04T16:05:00+00:00"},
                    {"autor": "sofia", "cuerpo": "Perfecto, gracias Delfi!", "creado": "2026-10-04T16:10:00+00:00"},
                ],
            },
            {
                "autor": "abril",
                "cuerpo": "En mayúsculas, pares como VA o LT casi siempre hay que cerrarlos bastante. No te asustes si te queda en -80 o más.",
                "creado": "2026-10-04T18:20:00+00:00",
                "utiles": ["sofia"],
            },
        ],
    },
    {
        "autor": "euge",
        "carrera": "sistemas",
        "materia": "Base de Datos II",
        "titulo": "El COUNT no me muestra los clientes que tienen cero pedidos",
        "cuerpo": (
            "Tengo que listar todos los clientes con la cantidad de pedidos que hicieron. Mi consulta:\n\n"
            "SELECT c.nombre, COUNT(p.id) AS cantidad\n"
            "FROM clientes c\n"
            "JOIN pedidos p ON p.cliente_id = c.id\n"
            "GROUP BY c.nombre;\n\n"
            "Me devuelve bien los que tienen pedidos, pero los que nunca compraron directamente no salen, y el enunciado dice que tienen que aparecer con 0."
        ),
        "creado": "2026-10-05T10:00:00+00:00",
        "respuestas": [
            {
                "autor": "nico",
                "cuerpo": (
                    "El problema es el JOIN. JOIN a secas es INNER JOIN: solo devuelve las filas que tienen pareja en las dos tablas. "
                    "Un cliente sin pedidos no tiene pareja, así que desaparece antes de llegar al GROUP BY.\n\n"
                    "Usá LEFT JOIN, que conserva todas las filas de la tabla de la izquierda y completa con NULL lo que falta:\n\n"
                    "SELECT c.id, c.nombre, COUNT(p.id) AS cantidad\n"
                    "FROM clientes c\n"
                    "LEFT JOIN pedidos p ON p.cliente_id = c.id\n"
                    "GROUP BY c.id, c.nombre\n"
                    "ORDER BY cantidad DESC;\n\n"
                    "Fijate que es COUNT(p.id) y no COUNT(*). COUNT(*) cuenta filas, y el cliente sin pedidos igual tiene una fila "
                    "(con NULLs), entonces te daría 1. COUNT(p.id) ignora los NULL y da 0.\n\n"
                    "También agregué c.id al GROUP BY: si hay dos clientes que se llaman igual, agrupando solo por nombre te los suma juntos."
                ),
                "creado": "2026-10-05T10:45:00+00:00",
                "aceptada": True,
                "utiles": ["euge", "ivan", "gonza", "fede", "mai", "agus", "mica"],
                "hilo": [
                    {"autor": "euge", "cuerpo": "Lo de COUNT(*) me iba a pasar seguro. Zarpado, gracias!", "creado": "2026-10-05T11:00:00+00:00"},
                ],
            },
            {
                "autor": "ivan",
                "cuerpo": "Pregunta que siempre me queda: si en el WHERE filtro por p.fecha, ¿se me vuelve a romper?",
                "creado": "2026-10-05T12:30:00+00:00",
                "utiles": ["euge"],
                "hilo": [
                    {"autor": "nico", "cuerpo": "Sí, porque el WHERE descarta las filas con p.fecha en NULL y el LEFT JOIN termina funcionando como un INNER. Poné la condición en el ON: LEFT JOIN pedidos p ON p.cliente_id = c.id AND p.fecha >= '2026-01-01'.", "creado": "2026-10-05T12:50:00+00:00"},
                    {"autor": "ivan", "cuerpo": "Alto dato, eso no lo explicaron en clase.", "creado": "2026-10-05T13:05:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "mica",
        "carrera": "multimedial",
        "materia": "Desarrollo de Videojuegos",
        "titulo": "En Unity mi personaje atraviesa el piso cuando cae desde muy alto",
        "cuerpo": "Estoy haciendo el plataformero 2D para Desarrollo de Videojuegos. El personaje tiene Rigidbody2D y BoxCollider2D, el piso es un Tilemap con Tilemap Collider 2D. Saltando normal anda bien, pero si cae de una plataforma alta a veces lo atraviesa y se va al vacío. Lo muevo con transform.position en Update. Ya probé agrandar el collider y no cambió nada.",
        "creado": "2026-10-06T15:00:00+00:00",
        "respuestas": [
            {
                "autor": "tomas",
                "cuerpo": "Me pasó en un ejercicio del primer cuatri! Creo que era algo del Rigidbody pero no me acuerdo qué toqué. Perdón, aporte cero jaja",
                "creado": "2026-10-06T15:30:00+00:00",
                "utiles": [],
            },
            {
                "autor": "flor",
                "cuerpo": (
                    "El problema principal es que lo movés con transform.position. Eso es teletransportarlo: la física no se entera del "
                    "recorrido entre un frame y otro, así que si en un frame está arriba del piso y en el siguiente ya está abajo, nunca "
                    "hubo colisión.\n\n"
                    "Movelo con el Rigidbody: en FixedUpdate, rb.velocity = new Vector2(input * velocidad, rb.velocity.y); y dejá que "
                    "la gravedad haga el resto. Y en el Rigidbody2D poné Collision Detection en Continuous, que es justamente para "
                    "objetos rápidos que pueden atravesar colliders finos."
                ),
                "creado": "2026-10-06T16:10:00+00:00",
                "utiles": ["mica", "tomas", "agus", "joaco", "santi", "valen"],
                "hilo": [
                    {"autor": "mica", "cuerpo": "Pero si lo muevo con velocity, ¿el salto lo hago con AddForce o también con velocity?", "creado": "2026-10-06T16:30:00+00:00"},
                    {"autor": "flor", "cuerpo": "Cualquiera de los dos. AddForce(Vector2.up * fuerza, ForceMode2D.Impulse) es lo más prolijo, pero asignando velocity.y directo tenés un salto más predecible.", "creado": "2026-10-06T16:45:00+00:00"},
                ],
            },
            {
                "autor": "joaco",
                "cuerpo": "Sumo a lo de Flor: en el Tilemap Collider 2D tildá Used By Composite y agregá un Composite Collider 2D. Así el piso es un solo collider y no un montón de cuadraditos, y de paso el personaje deja de trabarse en las uniones entre tiles.",
                "creado": "2026-10-06T17:20:00+00:00",
                "utiles": ["mica", "flor"],
            },
            {
                "autor": "agus",
                "cuerpo": "Otra cosa: limitá la velocidad de caída. Algo como rb.velocity = new Vector2(rb.velocity.x, Mathf.Max(rb.velocity.y, -20f)); En casi todos los plataformeros la caída tiene un tope; si no, se siente rara y encima te genera estos problemas.",
                "creado": "2026-10-06T19:00:00+00:00",
                "utiles": ["mica", "thiago"],
            },
            {
                "autor": "lucia",
                "cuerpo": "Cuando lo cursé, el profe bajaba puntos si el personaje se giraba al chocar contra una pared, así que de paso tildá Freeze Rotation Z en el Rigidbody2D. Te ahorrás una corrección en la entrega.",
                "creado": "2026-10-07T09:15:00+00:00",
                "utiles": ["mica"],
            },
            {
                "autor": "valen",
                "cuerpo": "Yo tenía lo mismo en mi plataformero. Lo cambié a velocity y ya no atraviesa nada, pero quedó medio resbaloso al frenar. ¿A alguien más le pasa?",
                "creado": "2026-10-07T11:00:00+00:00",
                "utiles": [],
                "hilo": [
                    {"autor": "agus", "cuerpo": "Para frenar seco poné velocity.x en 0 cuando no hay input. Y si se pega a las paredes, creá un Physics Material 2D con friction en 0 y asignáselo al collider del personaje.", "creado": "2026-10-07T11:30:00+00:00"},
                ],
            },
            {
                "autor": "nacho",
                "cuerpo": "Me salvaron a mí también, tenía exactamente el mismo bug.",
                "creado": "2026-10-07T14:00:00+00:00",
                "utiles": [],
            },
        ],
    },
    {
        "autor": "martu",
        "carrera": "cine",
        "materia": "Montaje Avanzado",
        "titulo": "DaVinci Resolve se traba con el material de la GoPro, ¿proxies u optimized media?",
        "cuerpo": "Estoy editando el corto con material 4K de una GoPro Hero 9 en H.265. La timeline se reproduce a 5 fps, todo trabado. Tengo una notebook con 16 GB de RAM y gráfica integrada. Vi que existen proxies y optimized media pero no entiendo la diferencia.",
        "creado": "2026-10-07T18:00:00+00:00",
        "respuestas": [
            {
                "autor": "franco",
                "cuerpo": (
                    "El cuello de botella es el códec. H.265 comprime muchísimo y para decodificarlo en tiempo real necesitás una gráfica "
                    "que lo acelere; con integrada sufre. Las dos opciones generan copias más livianas para editar:\n\n"
                    "- Optimized media: Resolve las crea y las administra solo. Clic derecho en los clips > Generate Optimized Media. "
                    "Quedan atadas al proyecto.\n"
                    "- Proxies: archivos que quedan en una carpeta y podés llevarte a otra compu. Clic derecho > Generate Proxy Media.\n\n"
                    "Para tu caso cualquiera va. Yo uso proxies a la mitad de resolución en DNxHR LB o ProRes Proxy. Después en "
                    "Playback > Use Proxy Media if Available los prendés para editar, y el render final siempre sale de los originales.\n\n"
                    "Si todavía se traba, en Playback > Timeline Proxy Resolution poné Quarter."
                ),
                "creado": "2026-10-07T19:30:00+00:00",
                "aceptada": True,
                "utiles": ["martu", "ludmi", "mateo"],
                "hilo": [
                    {"autor": "martu", "cuerpo": "Generó los proxies en 40 minutos y ahora va fluido. Una banda de gracias, Franco.", "creado": "2026-10-07T20:10:00+00:00"},
                ],
            },
            {
                "autor": "ludmi",
                "cuerpo": "¿Y para exportar a Instagram qué conviene?",
                "creado": "2026-10-08T09:00:00+00:00",
                "utiles": [],
                "hilo": [
                    {"autor": "franco", "cuerpo": "H.264, 1080x1920 si es vertical, y el mismo frame rate con el que filmaste. Con 10 a 15 Mbps alcanza, Instagram lo recomprime igual.", "creado": "2026-10-08T09:40:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "thiago",
        "carrera": "videojuegos",
        "materia": "Física aplicada",
        "titulo": "¿Leo el input del salto en Update o en FixedUpdate?",
        "cuerpo": "En clase dijeron que todo lo de física va en FixedUpdate. Puse el Input.GetKeyDown(KeyCode.Space) adentro de FixedUpdate y a veces aprieto espacio y no salta. Si lo paso a Update funciona siempre, pero entonces estoy aplicando la fuerza fuera de FixedUpdate. ¿Qué es lo correcto?",
        "creado": "2026-10-08T11:00:00+00:00",
        "respuestas": [
            {
                "autor": "agus",
                "cuerpo": (
                    "Se separa en dos: leés el input en Update y aplicás la física en FixedUpdate.\n\n"
                    "private bool quiereSaltar;\n\n"
                    "void Update() {\n"
                    "    if (Input.GetKeyDown(KeyCode.Space)) quiereSaltar = true;\n"
                    "}\n\n"
                    "void FixedUpdate() {\n"
                    "    if (quiereSaltar) {\n"
                    "        rb.AddForce(Vector2.up * fuerzaSalto, ForceMode2D.Impulse);\n"
                    "        quiereSaltar = false;\n"
                    "    }\n"
                    "}\n\n"
                    "GetKeyDown es true solo durante el frame en que apretaste. FixedUpdate no corre en todos los frames (por defecto va "
                    "a 50 por segundo y tu juego puede ir a 144), entonces si justo en ese frame no hubo FixedUpdate, el input se pierde."
                ),
                "creado": "2026-10-08T11:40:00+00:00",
                "aceptada": True,
                "utiles": ["thiago", "santi", "rocio", "flor", "tomas"],
                "hilo": [
                    {"autor": "flor", "cuerpo": "Para un impulso único yo lo dejaría directo en Update. AddForce con Impulse se aplica en el próximo paso de física igual, no pasa nada.", "creado": "2026-10-08T12:00:00+00:00"},
                    {"autor": "agus", "cuerpo": "Funciona, pero si después hacés salto variable (mantener apretado para saltar más alto) vas a necesitar el flag igual. Prefiero acostumbrarme a separarlo desde el principio.", "creado": "2026-10-08T12:20:00+00:00"},
                    {"autor": "flor", "cuerpo": "Ok, en eso tenés razón. Con salto variable lo de Update se complica. Me quedo con el flag.", "creado": "2026-10-08T12:35:00+00:00"},
                    {"autor": "thiago", "cuerpo": "Bueno, si ustedes dos se ponen de acuerdo me quedo tranquilo jaja. Gracias!", "creado": "2026-10-08T13:00:00+00:00"},
                ],
            },
            {
                "autor": "flor",
                "cuerpo": "Y para que el salto se sienta bien, aumentá la gravedad cuando el personaje está cayendo: rb.gravityScale = rb.velocity.y < 0 ? 3f : 1.5f; Es lo que hace casi todo plataformero: la caída más rápida que la subida.",
                "creado": "2026-10-08T12:10:00+00:00",
                "utiles": ["thiago", "agus"],
            },
        ],
    },
    {
        "autor": "benja",
        "carrera": "animacion",
        "materia": "Animación Digital 3D I",
        "titulo": "El codo del rig se deforma como si fuera de goma en Maya",
        "cuerpo": "Hice el skin del personaje con Bind Skin por defecto y cuando doblo el brazo a 90 grados el codo se aplasta y pierde volumen, parece una manguera. ¿Tengo que repintar todos los pesos?",
        "creado": "2026-10-09T16:00:00+00:00",
        "respuestas": [
            {
                "autor": "mateo",
                "cuerpo": (
                    "No hace falta empezar de cero. Ese efecto manguera casi siempre viene de dos cosas:\n\n"
                    "1. Topología: para que el codo doble bien necesitás al menos tres loops de aristas alrededor de la articulación. "
                    "Si tenés uno solo, no hay geometría para deformar.\n"
                    "2. Pesos: el bind por defecto reparte la influencia entre muchos huesos. Con Paint Skin Weights, en la zona del codo "
                    "dejá el loop central 50/50 entre brazo y antebrazo, y los loops de al lado más cargados hacia su hueso. Usá Smooth "
                    "con poca intensidad para la transición.\n\n"
                    "Antes de pintar, en las opciones de Bind Skin bajá Max Influences a 3 o 4 y usá Geodesic Voxel en vez de Closest "
                    "Distance: da un punto de partida mucho mejor.\n\n"
                    "Y dejá el brazo en pose a 90 y a 120 mientras pintás, así ves el resultado al toque."
                ),
                "creado": "2026-10-09T17:15:00+00:00",
                "aceptada": True,
                "utiles": ["benja", "juli", "lucia", "joaco"],
                "hilo": [
                    {"autor": "benja", "cuerpo": "Tenía un solo loop, ahí está todo. Agrego dos y repinto. Gracias!", "creado": "2026-10-09T17:40:00+00:00"},
                ],
            },
            {
                "autor": "juli",
                "cuerpo": "Todavía no llegué a 3D pero lo guardo jaja",
                "creado": "2026-10-09T19:00:00+00:00",
                "utiles": [],
            },
        ],
    },
    {
        "autor": "pili",
        "carrera": "web",
        "materia": "Lógica de la Programación",
        "titulo": "Sumo dos números con prompt y me da 23 en vez de 5",
        "cuerpo": (
            "let a = prompt('Primer número');\n"
            "let b = prompt('Segundo número');\n"
            "alert(a + b);\n\n"
            "Si pongo 2 y 3 me muestra 23. ¿Por qué?"
        ),
        "creado": "2026-10-10T12:00:00+00:00",
        "respuestas": [
            {
                "autor": "mai",
                "cuerpo": "prompt siempre devuelve texto, y en JavaScript el + entre dos textos los concatena. Convertilos antes: let a = Number(prompt('Primer número')); Si alguien escribe letras, Number te da NaN, así que podés chequearlo con isNaN(a).",
                "creado": "2026-10-10T12:30:00+00:00",
                "utiles": ["pili", "lauti"],
            },
            {
                "autor": "fede",
                "cuerpo": "Lo de Mai. Un detalle: el -, el * y el / sí convierten solos ('5' - '2' da 3), por eso confunde tanto que el + no lo haga. Yo uso parseInt si el ejercicio dice enteros y Number si puede haber decimales.",
                "creado": "2026-10-10T12:45:00+00:00",
                "aceptada": True,
                "utiles": ["pili", "kevin", "lauti"],
                "hilo": [
                    {"autor": "pili", "cuerpo": "Ahhh por eso la resta me andaba bien y no entendía nada. Gracias!", "creado": "2026-10-10T13:10:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "abril",
        "carrera": "grafico",
        "materia": "Diseño Editorial",
        "titulo": "¿Cuánto sangrado le dejo a la revista para la imprenta?",
        "cuerpo": "Tenemos que mandar la revista del TP a una imprenta de verdad. Me pidieron PDF con sangrado y marcas de corte. Las fotos llegan hasta el borde de la página. ¿Cuánto sangrado dejo? ¿Y cómo exporto en InDesign?",
        "creado": "2026-10-11T10:00:00+00:00",
        "respuestas": [
            {
                "autor": "delfi",
                "cuerpo": "Lo estándar acá es 3 mm por lado, pero preguntale a la imprenta porque algunas piden 5. En InDesign: Archivo > Configurar documento > Sangrado y área de anotación, poné 3 mm con el candado activado. Después estirá las fotos hasta la línea roja del sangrado, no hasta el borde de la página.",
                "creado": "2026-10-11T11:00:00+00:00",
                "utiles": ["abril", "sofia"],
            },
            {
                "autor": "sofia",
                "cuerpo": "Para exportar: Archivo > Exportar > PDF de Adobe (imprenta), con el ajuste PDF/X-1a si no te dan otro. En Marcas y sangrados tildá Marcas de recorte y Usar configuración de sangrado del documento. Y dejá el texto importante a por lo menos 5 mm del corte, porque la guillotina nunca es exacta.",
                "creado": "2026-10-11T11:40:00+00:00",
                "aceptada": True,
                "utiles": ["abril", "delfi", "tomi"],
                "hilo": [
                    {"autor": "abril", "cuerpo": "Lo mandé así y me lo aprobaron sin cambios. Gracias chicas!", "creado": "2026-10-11T12:00:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "valen",
        "carrera": "multimedial",
        "materia": "Diseño y Programación Web I",
        "titulo": "El fetch de un JSON local me tira error de CORS",
        "cuerpo": "Tengo un productos.json en la misma carpeta que el index.html y hago fetch('productos.json'). Abro el HTML con doble clic y en la consola aparece: Access to fetch at 'file:///...' has been blocked by CORS policy. ¿Qué tengo mal en el código?",
        "creado": "2026-10-12T14:30:00+00:00",
        "respuestas": [
            {
                "autor": "mai",
                "cuerpo": (
                    "El código está bien, el problema es cómo abrís el archivo. Con doble clic el navegador lo carga con file://, y por "
                    "seguridad no deja que una página lea otros archivos del disco con fetch.\n\n"
                    "Necesitás servirlo con un servidor local. Lo más fácil en VS Code es la extensión Live Server: clic derecho en el "
                    "index.html > Open with Live Server, y te abre en http://127.0.0.1:5500. Si tenés Python instalado, también sirve "
                    "correr python -m http.server en la carpeta.\n\n"
                    "Cuando lo suban a GitHub Pages o Netlify para la entrega, va a andar sin tocar nada."
                ),
                "creado": "2026-10-12T15:00:00+00:00",
                "aceptada": True,
                "utiles": ["valen", "mica", "nacho", "joaco", "lauti"],
            },
            {
                "autor": "joaco",
                "cuerpo": "Me pasó lo mismo en Web I. Ojo que si abrís en VS Code la carpeta de arriba, Live Server sirve desde ahí y la ruta cambia: si te tira 404, revisá que el fetch apunte bien desde donde queda el index.",
                "creado": "2026-10-12T16:20:00+00:00",
                "utiles": ["valen"],
            },
        ],
    },
    {
        "autor": "lucia",
        "carrera": "multimedial",
        "materia": "Texturas, iluminación y Render 3D",
        "titulo": "Fireflies en Cycles que no se van ni con 4000 samples",
        "cuerpo": "Estoy renderizando un interior con una ventana y luz de sol entrando, en Blender 4.2 con Cycles. Por más que suba los samples me quedan puntitos blancos sueltos en toda la pared, y un frame ya tarda 25 minutos. El denoiser los borronea pero quedan manchas. ¿Qué más puedo tocar?",
        "creado": "2026-10-13T20:00:00+00:00",
        "respuestas": [
            {
                "autor": "mateo",
                "cuerpo": (
                    "Los fireflies en interiores suelen venir de luz que rebota en superficies brillantes y encuentra caminos raros, y "
                    "subir samples no los saca porque son muy improbables. Lo que más me funcionó:\n\n"
                    "1. Render > Light Paths > Clamping: Indirect entre 5 y 10. Es lo que más ayuda, a costa de perder un poco de brillo en los rebotes.\n"
                    "2. Filter Glossy en 1, en el mismo panel. Suaviza los caminos de reflejo que generan los puntitos.\n"
                    "3. En la ventana poné un Light Portal (un área light con la opción Portal), así Cycles sabe por dónde entra la luz de afuera y muestrea mucho mejor.\n"
                    "4. Revisá los materiales: un roughness en 0 en el piso o algún metal pulido son los sospechosos de siempre.\n\n"
                    "Con eso podés bajar a 512 o 1024 samples con denoise y ganar mucho tiempo. Si tenés placa, en Preferences > System "
                    "elegí OptiX o CUDA; con CPU, 25 minutos es lo esperable."
                ),
                "creado": "2026-10-13T21:10:00+00:00",
                "aceptada": True,
                "utiles": ["lucia", "joaco", "benja", "mica", "valen", "nacho"],
                "hilo": [
                    {"autor": "lucia", "cuerpo": "Con clamping y el portal bajé a 6 minutos por frame y casi sin puntitos. Sos un genio.", "creado": "2026-10-13T21:40:00+00:00"},
                ],
            },
            {
                "autor": "joaco",
                "cuerpo": "Agrego: podés renderizar con menos samples, activar el pase Denoising Data y hacer el denoise en el compositor con el nodo Denoise. Tenés más control que con el denoise automático del render.",
                "creado": "2026-10-14T09:00:00+00:00",
                "utiles": ["lucia"],
            },
        ],
    },
    {
        "autor": "ivan",
        "carrera": "sistemas",
        "materia": "Ingeniería de Requerimientos",
        "titulo": "En el diagrama de casos de uso, ¿include o extend para 'Validar tarjeta'?",
        "cuerpo": "Estoy armando el diagrama UML de un sistema de compras. Tengo el caso Pagar compra y otro Validar tarjeta. En el grupo no nos ponemos de acuerdo si va con include o extend. También tengo Aplicar cupón de descuento, que es opcional.",
        "creado": "2026-10-14T11:00:00+00:00",
        "respuestas": [
            {
                "autor": "euge",
                "cuerpo": (
                    "La pregunta para decidir es: ¿el caso base se puede completar sin el otro?\n\n"
                    "- Validar tarjeta: siempre que pagás con tarjeta se valida, es obligatorio. Va con include, y la flecha sale de "
                    "Pagar compra hacia Validar tarjeta.\n"
                    "- Aplicar cupón: pasa solo a veces. Va con extend, y la flecha sale de Aplicar cupón hacia Pagar compra (al revés "
                    "que el include, es lo que más se confunde). Si querés ser prolijo, marcá el punto de extensión en Pagar compra.\n\n"
                    "Ojo con un caso: si también se puede pagar en efectivo, Validar tarjeta ya no es obligatorio para todos los pagos y hay que repensarlo."
                ),
                "creado": "2026-10-14T11:45:00+00:00",
                "aceptada": True,
                "utiles": ["ivan", "gonza", "nico"],
            },
            {
                "autor": "nico",
                "cuerpo": "Coincido con Euge. Solo agrego que no abusen de los include: si cada paso es un caso de uso, el diagrama termina siendo un diagrama de flujo, y en Requerimientos eso lo marcan siempre.",
                "creado": "2026-10-14T13:00:00+00:00",
                "utiles": ["ivan", "euge"],
                "hilo": [
                    {"autor": "ivan", "cuerpo": "Justo nos pasó eso en la primera entrega, nos lo marcaron en rojo. Gracias a los dos.", "creado": "2026-10-14T13:20:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "santi",
        "carrera": "videojuegos",
        "materia": "Animación 2D para Videojuegos",
        "titulo": "El sprite sheet que exporté de Krita se ve borroso en Unity",
        "cuerpo": "Animé el personaje en pixel art en Krita (32x32 por frame) y exporté la hoja como PNG. Cuando lo pongo en Unity se ve todo borroso, como con blur, y además los bordes de cada frame tienen una línea del frame de al lado.",
        "creado": "2026-10-15T17:00:00+00:00",
        "respuestas": [
            {
                "autor": "agus",
                "cuerpo": (
                    "En el Import Settings del PNG cambiá:\n\n"
                    "- Filter Mode: Point (no filter). Es lo que te saca el borroso.\n"
                    "- Compression: None.\n"
                    "- Pixels Per Unit: 32, para que un frame mida una unidad.\n\n"
                    "Lo de la línea del frame vecino también es por el filtro, pero si sigue, en el Sprite Editor cortalo con Grid By "
                    "Cell Size en 32x32 y dejá 1 o 2 px de separación entre frames cuando exportes desde Krita."
                ),
                "creado": "2026-10-15T17:30:00+00:00",
                "aceptada": True,
                "utiles": ["santi", "rocio", "jo", "tomas"],
            },
            {
                "autor": "flor",
                "cuerpo": "Y para que no tiemble cuando se mueve la cámara, agregale el componente Pixel Perfect Camera a la cámara con Assets PPU en 32. Con pixel art hace una diferencia enorme.",
                "creado": "2026-10-15T18:15:00+00:00",
                "utiles": ["santi", "agus"],
                "hilo": [
                    {"autor": "santi", "cuerpo": "Quedó perfecto, nítido nítido. Gracias!", "creado": "2026-10-15T18:40:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "mica",
        "carrera": "multimedial",
        "materia": "Animación en 2D y 3D",
        "titulo": "Las animaciones de After Effects se ven duras aunque les puse Easy Ease",
        "cuerpo": "Estoy animando la intro del TP de motion. Puse F9 (Easy Ease) en todos los keyframes de posición y escala, pero igual se ve mecánico, como si arrancara y frenara siempre igual. Vi videos donde el movimiento tiene mucha más onda y no sé cómo lo hacen.",
        "creado": "2026-10-16T13:00:00+00:00",
        "respuestas": [
            {
                "autor": "joaco",
                "cuerpo": (
                    "Easy Ease es un punto de partida, la gracia está en el Graph Editor. Seleccioná la propiedad, abrí el editor de "
                    "gráficos y pasá a Speed Graph. Ahí estirá las manijas de influencia: si llevás la salida del primer keyframe a "
                    "80% o 90%, el objeto arranca lento y llega rápido, y eso se siente mucho más vivo.\n\n"
                    "Otras cosas:\n"
                    "- No uses la misma curva en todo, eso es lo que da el efecto mecánico.\n"
                    "- Separá las dimensiones de la posición (clic derecho > Separate Dimensions) para animar X e Y con curvas distintas.\n"
                    "- Sumale overshoot a la escala: que pase a 105% y vuelva a 100%."
                ),
                "creado": "2026-10-16T14:00:00+00:00",
                "utiles": ["mica", "valen", "cami", "lucia"],
                "hilo": [
                    {"autor": "mica", "cuerpo": "Lo del Speed Graph no lo había tocado nunca. ¿Y el Value Graph cuándo se usa?", "creado": "2026-10-16T14:30:00+00:00"},
                    {"autor": "joaco", "cuerpo": "Value te muestra el valor en sí, sirve para ver arcos y overshoots. Speed te muestra qué tan rápido cambia. Para ajustar el ease, Speed es más intuitivo.", "creado": "2026-10-16T14:50:00+00:00"},
                    {"autor": "lucia", "cuerpo": "Coincido con Joaco, aunque para la escala yo uso Value porque ves clarito el rebote. Probá los dos y quedate con el que te resulte más cómodo.", "creado": "2026-10-16T15:20:00+00:00"},
                    {"autor": "mica", "cuerpo": "Hice el overshoot de escala y cambió todo. Mañana pruebo separar dimensiones.", "creado": "2026-10-16T16:00:00+00:00"},
                ],
            },
            {
                "autor": "valen",
                "cuerpo": "Si querés un atajo, hay extensiones como Flow que te dejan aplicar curvas con un clic. Pero el profe quiere ver que lo resolviste en el Graph Editor, así que primero aprendelo a mano.",
                "creado": "2026-10-16T18:00:00+00:00",
                "utiles": ["mica"],
            },
        ],
    },
    {
        "autor": "fede",
        "carrera": "web",
        "materia": "Programación II",
        "titulo": "Me aparecen <<<<<<< HEAD en el código después de hacer git pull",
        "cuerpo": "Somos tres en el grupo trabajando en el mismo repo. Hice git pull y me dijo CONFLICT (content): Merge conflict in js/app.js. Ahora el archivo tiene cosas como <<<<<<< HEAD, ======= y >>>>>>> origin/main y no anda nada. ¿Cómo lo arreglo sin perder lo que hizo mi compañero?",
        "creado": "2026-10-17T10:30:00+00:00",
        "respuestas": [
            {
                "autor": "nico",
                "cuerpo": (
                    "Tranqui, no se perdió nada. Git encontró que vos y tu compañero tocaron las mismas líneas y no sabe con cuál "
                    "quedarse, entonces te marca las dos versiones:\n\n"
                    "<<<<<<< HEAD\n"
                    "(tu versión)\n"
                    "=======\n"
                    "(la versión del remoto)\n"
                    ">>>>>>> origin/main\n\n"
                    "Pasos:\n"
                    "1. Abrí app.js en VS Code. Arriba de cada conflicto aparecen opciones: Accept Current Change, Accept Incoming Change "
                    "o Accept Both Changes. Si necesitás partes de las dos, editalo a mano y borrá las marcas.\n"
                    "2. Cuando no quede ninguna marca, probá que el código ande.\n"
                    "3. git add js/app.js\n"
                    "4. git commit (git ya te propone el mensaje del merge).\n"
                    "5. git push\n\n"
                    "Si te mareaste y querés volver a como estaba antes del pull: git merge --abort. Para que pase menos, hagan pull "
                    "antes de empezar a laburar, commits chicos y, si pueden, cada uno en su rama."
                ),
                "creado": "2026-10-17T11:00:00+00:00",
                "aceptada": True,
                "utiles": ["fede", "mai", "lauti", "euge", "ivan", "gonza", "pili", "kevin", "agus"],
                "hilo": [
                    {"autor": "fede", "cuerpo": "Lo resolví con Accept Both y ajustando dos líneas. Me salvaste el TP.", "creado": "2026-10-17T11:30:00+00:00"},
                ],
            },
            {
                "autor": "mai",
                "cuerpo": "Lo de las ramas, posta. En mi grupo hacemos una rama por tarea y un pull request para mergear a dev. Al principio parece mucho lío, pero los conflictos casi desaparecen.",
                "creado": "2026-10-17T12:15:00+00:00",
                "utiles": ["fede", "nico"],
            },
            {
                "autor": "euge",
                "cuerpo": "Y no hagan git push --force para arreglarlo, que le pisás los commits al resto. Lo digo por experiencia jaja",
                "creado": "2026-10-17T14:00:00+00:00",
                "utiles": ["fede", "mai", "nico"],
            },
        ],
    },
    {
        "autor": "sofia",
        "carrera": "grafico",
        "materia": "Fotografía",
        "titulo": "Fotos de producto con luz de ventana y lámpara: el fondo blanco me sale celeste y la piel naranja, ¿cómo corrijo el balance de blancos en Lightroom?",
        "cuerpo": "Para el TP de Fotografía saqué fotos de unos aros sobre cartulina blanca y algunas con una amiga sosteniéndolos. Usé luz de ventana a la mañana y una lámpara cálida de relleno, en RAW con balance automático. En Lightroom, si corrijo el fondo para que quede blanco, la piel queda rara, y si arreglo la piel, el fondo se pone celeste.",
        "creado": "2026-10-18T18:00:00+00:00",
        "respuestas": [
            {
                "autor": "franco",
                "cuerpo": (
                    "El problema es que mezclaste dos temperaturas: la ventana (luz de día, fría) y la lámpara (cálida). Ningún balance "
                    "global puede dejar bien las dos a la vez, porque cada zona está iluminada por una fuente distinta.\n\n"
                    "Lo más sano es evitarlo en la toma: apagá la lámpara y rellená con una cartulina blanca o un telgopor del lado "
                    "opuesto a la ventana. Si no podés repetir, en Lightroom hacé el balance con el cuentagotas sobre el fondo y después "
                    "corregí la piel con una máscara (las versiones nuevas detectan personas solas) con temperatura y matiz propios.\n\n"
                    "Para la próxima, una carta gris en la primera foto te salva."
                ),
                "creado": "2026-10-18T19:00:00+00:00",
                "utiles": ["sofia", "delfi", "martu"],
                "hilo": [
                    {"autor": "sofia", "cuerpo": "Creo que voy a repetir las fotos sin la lámpara, me parece más prolijo. Dejo la pregunta abierta por si alguien tiene un truco para salvar las que ya saqué.", "creado": "2026-10-18T19:30:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "juli",
        "carrera": "animacion",
        "materia": "Animación 2D",
        "titulo": "Lip sync en Toon Boom Harmony: ¿cómo uso la detección automática?",
        "cuerpo": "Tengo un diálogo de 10 segundos y el personaje tiene sus dibujos de boca A, B, C, D, E, F, G y X. Vi que Harmony puede hacer el lip sync solo a partir del audio, pero cuando lo intento me pone las bocas mal y no sé dónde se cambia.",
        "creado": "2026-10-19T15:00:00+00:00",
        "respuestas": [
            {
                "autor": "mateo",
                "cuerpo": (
                    "Se puede. Seleccioná la capa de sonido en la Timeline: en Layer Properties hay una opción de Lip-Sync Detection que "
                    "analiza el audio y asigna las letras de Preston Blair (A a G, y X para el silencio). Después, clic derecho en la capa "
                    "de la boca > Lip-Sync > Map Lip-Sync, y ahí elegís qué dibujo corresponde a cada letra. Si te mapea mal, casi seguro "
                    "tus dibujos no se llaman igual que las letras.\n\n"
                    "Igual, la detección automática es un borrador. Lo profesional es usarla de base y corregir a mano: adelantá las bocas "
                    "uno o dos cuadros respecto del sonido, porque el ojo lee la boca antes de que llegue el audio, y sacá las bocas que "
                    "duran un solo cuadro, que hacen que tiemble."
                ),
                "creado": "2026-10-19T16:20:00+00:00",
                "utiles": ["juli", "benja"],
            },
            {
                "autor": "lucia",
                "cuerpo": "En Multimedial no usamos Harmony, pero en After lo que hacía era marcar las sílabas fuertes con marcadores sobre el audio antes de animar. Capaz te sirve para corregir lo automático.",
                "creado": "2026-10-20T10:00:00+00:00",
                "utiles": ["juli"],
            },
            {
                "autor": "benja",
                "cuerpo": "¿Te funcionó? Yo lo probé con un audio que tenía música de fondo y detectó cualquier cosa.",
                "creado": "2026-10-20T12:00:00+00:00",
                "utiles": [],
                "hilo": [
                    {"autor": "juli", "cuerpo": "Renombré los dibujos y mejoró bastante, pero me pasa lo mismo que a vos con la música. Voy a pedir el audio de la voz sola.", "creado": "2026-10-20T12:30:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "mateo",
        "carrera": "animacion",
        "materia": "Simulación de Partículas y Fluidos II",
        "titulo": "El bake del fluido en Blender ocupa 60 GB y todavía no terminó",
        "cuerpo": "Estoy simulando agua cayendo en un vaso con Mantaflow, dominio con resolución 256, 120 frames. El caché ya ocupa 60 GB y va por el frame 70. Necesito que se vea bien en un plano cerrado. ¿Bajo la resolución o hay otra forma?",
        "creado": "2026-10-20T10:00:00+00:00",
        "respuestas": [
            {
                "autor": "benja",
                "cuerpo": (
                    "Antes de bajar la resolución, achicá el dominio. Si el vaso ocupa un tercio del dominio, estás simulando un montón "
                    "de aire: ajustalo al vaso con un poco de margen arriba para la caída. Con la misma resolución en un dominio más chico "
                    "ganás detalle y espacio.\n\n"
                    "También:\n"
                    "- Activá Adaptive Domain si el líquido no llena todo el volumen.\n"
                    "- Poné el caché en Modular y bakeá primero solo Data a resolución 128 para ajustar el timing. Cuando te guste, subí "
                    "la resolución o sumá el Mesh con Upres Factor.\n"
                    "- Si no vas a renderizar spray ni espuma, no actives esas partículas, son de lo que más pesa.\n"
                    "- Usá formato OpenVDB con compresión Blosc."
                ),
                "creado": "2026-10-20T11:00:00+00:00",
                "aceptada": True,
                "utiles": ["mateo", "juli"],
            },
            {
                "autor": "joaco",
                "cuerpo": "Coincido con lo del dominio. Y mandá el caché a un disco con espacio, no al mismo SSD del sistema, que si se llena se cuelga todo.",
                "creado": "2026-10-20T13:30:00+00:00",
                "utiles": ["mateo"],
            },
        ],
    },
    {
        "autor": "jo",
        "carrera": "videojuegos",
        "materia": "Introducción al Diseño de Juegos",
        "titulo": "¿Qué es exactamente una mecánica y qué una dinámica en el MDA?",
        "cuerpo": "Para el TP tenemos que analizar un juego con el framework MDA. Elegí Celeste. La estética la entiendo, pero me mezclo con mecánicas y dinámicas. ¿El dash es una mecánica o una dinámica?",
        "creado": "2026-10-20T18:00:00+00:00",
        "respuestas": [
            {
                "autor": "flor",
                "cuerpo": (
                    "El dash es una mecánica: es una regla del juego, algo que el diseñador definió (apretás un botón y el personaje se "
                    "impulsa en ocho direcciones, una vez en el aire hasta que tocás el piso).\n\n"
                    "La dinámica es lo que aparece cuando el jugador usa esas mecánicas jugando. Por ejemplo, encadenar dash, agarrarse "
                    "de la pared y saltar para cruzar una pantalla, o el ritmo de prueba y error de morir y reaparecer al toque. Nadie "
                    "programó que el jugador lo intente diez veces: surge de las reglas.\n\n"
                    "Y la estética es lo que siente el jugador: desafío, superación. Truco para el TP: por cada estética que nombres, "
                    "explicá qué dinámica la genera y de qué mecánicas sale esa dinámica."
                ),
                "creado": "2026-10-20T19:10:00+00:00",
                "utiles": ["jo", "rocio", "santi"],
            },
        ],
    },
    {
        "autor": "sol",
        "carrera": "marketing",
        "materia": "Marketing Digital II",
        "titulo": "La campaña de Meta Ads quedó en Aprendizaje limitado",
        "cuerpo": "Estoy manejando una campaña real de una marca de ropa (es parte de la práctica). Optimización por compras, presupuesto de 5000 pesos por día, tres conjuntos de anuncios. Hace una semana que dice Aprendizaje limitado y el costo por resultado está altísimo. ¿Junto los conjuntos? ¿Subo el presupuesto?",
        "creado": "2026-10-21T09:00:00+00:00",
        "respuestas": [
            {
                "autor": "bauti",
                "cuerpo": "Todavía no vi Ads, pero leí que Meta necesita unas 50 conversiones por semana por conjunto para salir del aprendizaje. Con 5000 por día repartido en tres capaz no llegás nunca.",
                "creado": "2026-10-21T10:30:00+00:00",
                "utiles": ["sol"],
            },
            {
                "autor": "cande",
                "cuerpo": "Lo que dice Bauti lo escuché en una charla. Ahí recomendaban dos cosas: juntar los tres conjuntos en uno solo con públicos amplios, u optimizar por un evento anterior, como agregar al carrito, que pasa más seguido. No lo probé con plata real así que no sé cuál anda mejor.",
                "creado": "2026-10-21T12:00:00+00:00",
                "utiles": ["sol", "bauti"],
                "hilo": [
                    {"autor": "sol", "cuerpo": "Tiene sentido, con tres conjuntos tengo como 8 compras por semana en cada uno. Voy a probar juntarlos y les cuento la semana que viene.", "creado": "2026-10-21T12:40:00+00:00"},
                ],
            },
        ],
    },
    {
        "autor": "franco",
        "carrera": "cine",
        "materia": "Guion y Preproducción de Proyecto Final",
        "titulo": "¿Cómo armaron el plan de rodaje para el proyecto final?",
        "cuerpo": "Tenemos 18 escenas, 6 locaciones y cuatro días de rodaje. Estoy armando el plan en una planilla pero me cuesta decidir el orden. ¿Ordenan por locación, por actores o por luz natural? Si alguien tiene una plantilla que le haya servido, mejor.",
        "creado": "2026-10-22T11:00:00+00:00",
        "respuestas": [
            {
                "autor": "martu",
                "cuerpo": "Con el corto de Dirección II ordenamos primero por locación, después dentro de cada locación por disponibilidad de actores, y la luz natural la usamos para decidir el horario. Mudarse de locación es lo que más tiempo te come. Para la planilla adaptamos el desglose de StudioBinder a Google Sheets, después te lo paso.",
                "creado": "2026-10-22T13:00:00+00:00",
                "utiles": ["franco", "ludmi"],
            },
        ],
    },
    {
        "autor": "rocio",
        "carrera": "videojuegos",
        "materia": "Ilustración Conceptual",
        "titulo": "¿Cómo hacen thumbnails rápidos para el concept del personaje?",
        "cuerpo": "El profe pidió 30 thumbnails de siluetas para el jueves y yo tardo una banda en cada uno porque me pongo a detallar. ¿Qué pincel usan en Krita? ¿Cuánto tiempo le dedican a cada uno?",
        "creado": "2026-10-22T20:00:00+00:00",
        "respuestas": [],
    },
    {
        "autor": "kevin",
        "carrera": "web",
        "materia": "Diseño de Interfaces",
        "titulo": "¿Cuántos tamaños de fuente conviene usar en una interfaz?",
        "cuerpo": "Estoy diseñando la home de una app en Figma y tengo como 9 tamaños de texto distintos. El profe me dijo que es demasiado. ¿Hay alguna regla o escala que se use?",
        "creado": "2026-10-23T09:30:00+00:00",
        "respuestas": [],
    },
    {
        "autor": "delfi",
        "carrera": "grafico",
        "materia": "Dirección de Arte",
        "titulo": "Referencias de dirección de arte para una campaña de yerba setentosa",
        "cuerpo": "Estoy armando el moodboard para Dirección de Arte. Elegimos una marca de yerba ficticia con estética de los 70. ¿Alguien tiene referencias de campañas argentinas de esa época o fotógrafos que trabajen esa paleta? Ya tengo bastante de Pinterest y quiero salir de ahí.",
        "creado": "2026-10-23T17:00:00+00:00",
        "respuestas": [],
    },
    {
        "autor": "ludmi",
        "carrera": "cine",
        "materia": "Montaje",
        "titulo": "Premiere me pregunta si cambio la secuencia para que coincida con el clip",
        "cuerpo": "Grabé con el celu a 30 fps pero la secuencia del ejercicio tiene que ser a 24. Cuando arrastro el primer clip me aparece el cartel de que no coincide la configuración. ¿Qué le pongo? ¿Se va a ver mal?",
        "creado": "2026-10-24T10:00:00+00:00",
        "respuestas": [],
    },
    {
        "autor": "cande",
        "carrera": "marketing",
        "materia": "Herramientas de Diseño Digital I",
        "titulo": "Exporté el carrusel para Instagram y se ve pixelado",
        "cuerpo": "Diseñé un carrusel de 5 placas en Illustrator a 1080x1350 y lo exporté en JPG. Cuando lo subo a Instagram el texto se ve borroso. ¿Exporto en PNG? ¿Más grande?",
        "creado": "2026-10-24T15:30:00+00:00",
        "respuestas": [],
    },
    {
        "autor": "mica",
        "carrera": "multimedial",
        "materia": "Modelado 3D",
        "titulo": "En Blender el modificador Mirror me deja una costura en el medio",
        "cuerpo": "Estoy modelando la cabeza del personaje con Mirror en el eje X y cuando le pongo Subdivision Surface se ve una línea en el centro. Ya tengo activado Clipping. ¿Qué me falta?",
        "creado": "2026-10-25T01:10:00+00:00",
        "respuestas": [],
    },
]
