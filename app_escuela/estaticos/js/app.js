document.documentElement.classList.add("js");   // hay JavaScript: los estilos pueden ocultar lo que sobra

// Botón sol/luna: cambia el modo y recuerda la elección
document.getElementById("boton-tema").addEventListener("click", function () {
  var raiz = document.documentElement;
  var nuevo = raiz.getAttribute("data-theme") === "oscuro" ? "claro" : "oscuro";
  raiz.setAttribute("data-theme", nuevo);
  try { localStorage.setItem("tema", nuevo); } catch (e) {}
  document.dispatchEvent(new CustomEvent("cambio-tema"));  // los gráficos cambian sus colores
});

// Botón de imprimir (recibos)
document.querySelectorAll("[data-imprimir]").forEach(function (b) {
  b.addEventListener("click", function () { window.print(); });
});

// Confirmación antes de acciones delicadas: <form data-confirmar="¿Seguro?">
document.addEventListener("submit", function (e) {
  var mensaje = e.target.getAttribute("data-confirmar");
  if (mensaje && !window.confirm(mensaje)) e.preventDefault();
});

// <select data-alternar="id">: el bloque se muestra solo cuando el select está vacío,
// o, si tiene data-mostrar-con="valor", solo cuando el select tiene ese valor
document.querySelectorAll("select[data-alternar]").forEach(function (sel) {
  var bloque = document.getElementById(sel.getAttribute("data-alternar"));
  var valor = sel.getAttribute("data-mostrar-con") || "";
  function aplicar() { bloque.disabled = sel.value !== valor; }
  sel.addEventListener("change", aplicar);
  aplicar();
});

// Casilla "Todos": marca o desmarca todas las casillas con ese nombre (pantalla Horarios)
document.querySelectorAll("[data-marcar-todos]").forEach(function (todos) {
  var casillas = document.querySelectorAll("input[type=checkbox][name='" + todos.getAttribute("data-marcar-todos") + "']");
  function revisar() { todos.checked = Array.prototype.every.call(casillas, function (c) { return c.checked; }); }
  todos.addEventListener("change", function () { casillas.forEach(function (c) { c.checked = todos.checked; }); });
  casillas.forEach(function (c) { c.addEventListener("change", revisar); });
  revisar();
});

// Pantalla Horarios: con "Quitar entrenamiento" no se piden hora ni lugar
document.querySelectorAll(".form-horarios").forEach(function (f) {
  var bloque = f.querySelector(".solo-poner");
  function aplicar() {
    var quitar = f.querySelector("input[name=accion]:checked").value === "quitar";
    bloque.hidden = quitar;
    bloque.querySelectorAll("input, select").forEach(function (c) { c.disabled = quitar; });
    if (!quitar) {
      var sel = bloque.querySelector("select[data-alternar]");
      if (sel) sel.dispatchEvent(new Event("change"));
    }
  }
  f.querySelectorAll("input[name=accion]").forEach(function (r) { r.addEventListener("change", aplicar); });
  aplicar();
});

// Alumno nuevo: al poner la fecha de nacimiento, el sistema calcula la categoría y elige el grupo
// (el de su edad con más cupos libres). El servidor hace el mismo cálculo y valida la regla de edad.
(function () {
  var fecha = document.getElementById("fecha_nacimiento");
  var grupo = document.querySelector("#elegir-grupo select");
  if (!fecha || !grupo) return;
  var aviso = document.getElementById("ayuda-grupo");
  function edad(valor) {
    var n = new Date(valor + "T00:00:00"), hoy = new Date();
    if (!valor || isNaN(n)) return null;
    var e = hoy.getFullYear() - n.getFullYear();
    if (hoy.getMonth() < n.getMonth() || (hoy.getMonth() === n.getMonth() && hoy.getDate() < n.getDate())) e--;
    return e;
  }
  function escribir(partes) {   // [texto, negrita, texto, ...] sin usar innerHTML
    aviso.textContent = "";
    partes.forEach(function (p, i) {
      var nodo = i % 2 ? document.createElement("strong") : document.createTextNode(p);
      if (i % 2) nodo.textContent = p;
      aviso.appendChild(nodo);
    });
  }
  function calcular() {
    var e = edad(fecha.value), validos = [], llenos = [];
    Array.prototype.forEach.call(grupo.options, function (o) {
      if (!o.dataset.min) return;
      var cabe = e !== null && e >= +o.dataset.min && e <= +o.dataset.max;
      var lleno = o.dataset.lleno === "1";
      o.hidden = e !== null && !cabe;
      o.disabled = (e !== null && !cabe) || lleno;
      if (cabe && lleno) llenos.push(o);
      if (cabe && !lleno) validos.push(o);
    });
    var actual = grupo.selectedOptions[0];
    if (actual && actual.hidden) grupo.value = "auto";
    aviso.classList.remove("grupo-ok", "grupo-mal");
    if (e === null) {
      escribir(["Pon la fecha de nacimiento y el grupo se elige solo, según su edad."]);
      return;
    }
    if (e < 0 || e > 25) { aviso.classList.add("grupo-mal"); escribir(["Revisa la fecha de nacimiento: da " + e + " años."]); return; }
    if (grupo.value === "despues") { escribir(["Tiene " + e + " años. Se guardará sin grupo."]); return; }
    if (grupo.value !== "auto") {
      var o = grupo.selectedOptions[0];
      aviso.classList.add("grupo-ok");
      escribir(["Tiene " + e + " años → ", o.dataset.categoria, " · entrenará en ", o.dataset.nombre, " (elegido a mano)"]);
      return;
    }
    if (validos.length) {
      var mejor = validos.reduce(function (a, b) { return +b.dataset.libres > +a.dataset.libres ? b : a; });
      aviso.classList.add("grupo-ok");
      escribir(["Tiene " + e + " años → ", mejor.dataset.categoria, " · entrenará en ", mejor.dataset.nombre,
                " (" + mejor.dataset.libres + " cupo" + (+mejor.dataset.libres === 1 ? "" : "s") + " libre" + (+mejor.dataset.libres === 1 ? "" : "s") + ")"]);
    } else if (llenos.length) {
      aviso.classList.add("grupo-mal");
      escribir(["Tiene " + e + " años, pero ", llenos.map(function (o) { return o.dataset.nombre; }).join(" y "),
                " no tiene cupo. Se guardará sin grupo y lo inscribes cuando haya lugar (o sube el cupo del grupo)."]);
    } else {
      aviso.classList.add("grupo-mal");
      escribir(["Tiene " + e + " años y no hay ningún grupo activo de su edad. Se guardará sin grupo."]);
    }
  }
  fecha.addEventListener("change", calcular);
  fecha.addEventListener("input", calcular);
  grupo.addEventListener("change", calcular);
  calcular();
})();

// Alumno nuevo: el tutor se busca escribiendo (nombre, CI o celular) y se elige con un toque.
// Si no existe, "Tutor nuevo" pide solo nombre, apellido y celular. El apellido del alumno se copia del tutor.
(function () {
  var caja = document.getElementById("elegir-tutor");
  if (!caja) return;
  var oculto = document.getElementById("id_tutor"), elegido = document.getElementById("tutor-elegido");
  var buscar = document.getElementById("tutor-buscar"), nuevo = document.getElementById("tutor-nuevo");
  var entrada = document.getElementById("buscar_tutor"), lista = document.getElementById("resultados-tutor");
  var apellidos = document.getElementById("apellidos");
  var espera = null, pedido = 0;

  function modo(m) {
    elegido.hidden = m !== "elegido";
    buscar.hidden = m !== "buscar";
    nuevo.hidden = m !== "nuevo";
    nuevo.disabled = m !== "nuevo";
  }
  // El apellido del alumno sigue al del tutor mientras nadie lo escriba a mano
  if (apellidos) apellidos.addEventListener("input", function () { apellidos.dataset.aMano = apellidos.value ? "1" : ""; });
  function copiarApellido(texto) {
    if (apellidos && !apellidos.dataset.aMano) apellidos.value = texto || "";
  }
  function poner(campo, texto) { elegido.querySelector("[data-t=" + campo + "]").textContent = texto; }

  function elegir(t) {
    oculto.value = t.id_tutor;
    poner("nombre", t.nombres + " " + (t.apellidos || ""));
    poner("detalle", (t.celular || "Sin celular") + (t.ci ? " · CI " + t.ci : ""));
    poner("hijos", t.hijos ? "Ya tiene: " + t.hijos : "");
    copiarApellido(t.apellidos);
    modo("elegido");
    var siguiente = document.getElementById("nombres");
    if (siguiente) siguiente.focus();
  }

  function crearNuevo() {
    oculto.value = "nuevo";
    var q = entrada.value.trim();
    if (q) {  // lo que ya escribió no se pierde: números al celular, letras al nombre
      if (/^[\d\s+-]+$/.test(q)) document.getElementById("tutor_whatsapp").value = q;
      else document.getElementById("tutor_nombres").value = q;
    }
    modo("nuevo");
    document.getElementById(q && !/^[\d\s+-]+$/.test(q) ? "tutor_apellidos" : "tutor_nombres").focus();
  }

  function mostrar(tutores, q) {
    lista.innerHTML = "";
    tutores.forEach(function (t) {
      var li = document.createElement("li"), b = document.createElement("button"), s = document.createElement("strong");
      var d = document.createElement("small");
      b.type = "button";
      s.textContent = t.nombres + " " + (t.apellidos || "");
      d.textContent = [t.celular, t.ci ? "CI " + t.ci : "", t.hijos ? "hijos: " + t.hijos : ""].filter(Boolean).join(" · ");
      b.appendChild(s); b.appendChild(d);
      b.addEventListener("click", function () { elegir(t); });
      li.appendChild(b); lista.appendChild(li);
    });
    if (!tutores.length && q.length >= 2) {
      var li = document.createElement("li");
      li.className = "sin-resultados";
      li.textContent = "No hay ningún tutor con «" + q + "». Toca «Tutor nuevo».";
      lista.appendChild(li);
    }
  }

  entrada.addEventListener("input", function () {
    clearTimeout(espera);
    var q = entrada.value.trim();
    if (q.length < 2) { lista.innerHTML = ""; return; }
    espera = setTimeout(function () {
      var numero = ++pedido;
      fetch(caja.dataset.url + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (numero === pedido) mostrar(d, q); })
        .catch(function () {});
    }, 250);
  });
  // Enter en el buscador no envía el formulario
  entrada.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
  caja.querySelectorAll("[data-tutor-nuevo]").forEach(function (b) { b.addEventListener("click", crearNuevo); });
  caja.querySelectorAll("[data-cambiar-tutor]").forEach(function (b) {
    b.addEventListener("click", function () { oculto.value = ""; modo("buscar"); entrada.focus(); });
  });
  var apTutor = document.getElementById("tutor_apellidos");
  if (apTutor) apTutor.addEventListener("input", function () { copiarApellido(apTutor.value); });
  if (apellidos && apellidos.value) apellidos.dataset.aMano = "1";
  // Sin tutor elegido no se envía: se avisa ahí mismo
  caja.closest("form").addEventListener("submit", function (e) {
    if (oculto.value) return;
    e.preventDefault();
    modo("buscar");
    entrada.setAttribute("aria-invalid", "true");
    lista.innerHTML = '<li class="sin-resultados">Busca y elige al tutor, o toca «Tutor nuevo».</li>';
    entrada.focus();
  });
})();

// Aviso "Cargando…" al cambiar de pantalla o enviar un formulario. La base gratis de Azure se "duerme"
// y la primera carga puede tardar: así no parece que la app se colgó.
(function () {
  var aviso = null, tiempos = [];
  function mostrar(texto) {
    if (!aviso) {
      aviso = document.createElement("p");
      aviso.className = "cargando";
      aviso.setAttribute("role", "status");
      document.body.appendChild(aviso);
    }
    aviso.textContent = texto;
  }
  function empezar() {
    limpiar();
    tiempos.push(setTimeout(function () { mostrar("Cargando…"); }, 900));
    tiempos.push(setTimeout(function () { mostrar("Conectando con la base de datos… la primera vez del día puede tardar hasta un minuto."); }, 6000));
  }
  function limpiar() {
    tiempos.forEach(clearTimeout); tiempos = [];
    if (aviso) { aviso.remove(); aviso = null; }
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.ctrlKey || e.metaKey || e.shiftKey || a.target || a.hasAttribute("download")) return;
    if (a.origin !== location.origin || a.getAttribute("href").charAt(0) === "#") return;
    empezar();
  });
  document.addEventListener("submit", function (e) { if (!e.defaultPrevented) empezar(); });
  window.addEventListener("pageshow", limpiar);   // al volver atrás, sin aviso colgado
})();

// Beca: botones rápidos (Sin beca, 25 %, 50 %, 100 %) que llenan el campo
document.querySelectorAll("[data-beca]").forEach(function (b) {
  b.addEventListener("click", function () { document.getElementById("porcentaje_beca").value = b.dataset.beca; });
});

// Recibo recién cobrado con "Enviar por WhatsApp" marcado: WhatsApp se abre APARTE (la app queda en el recibo).
// Si el navegador no deja abrirlo solo, el botón verde queda resaltado para tocarlo.
(function () {
  var enlace = document.querySelector("[data-abrir-solo]");
  if (!enlace) return;
  try { history.replaceState(null, "", location.pathname); } catch (e) {}   // al volver atrás no se abre otra vez
  enlace.classList.add("resaltado");
  var ventana = null;
  try { ventana = window.open(enlace.href, "_blank"); } catch (e) {}
  if (ventana) { try { ventana.opener = null; } catch (e) {} }
  else { enlace.focus(); }
})();

// Búsqueda mientras se escribe: <form data-busqueda-vivo="#resultados">. Pide la misma página con lo escrito
// y cambia solo los resultados (sin recargar ni tocar "Buscar"). Si falla, el botón Buscar sigue funcionando.
document.querySelectorAll("form[data-busqueda-vivo]").forEach(function (form) {
  var destino = form.getAttribute("data-busqueda-vivo"), espera = null, pedido = 0;
  function buscar() {
    var url = (form.getAttribute("action") || location.pathname) + "?" + new URLSearchParams(new FormData(form)).toString();
    var numero = ++pedido;
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok || r.redirected) throw new Error("sin sesión"); return r.text(); })
      .then(function (html) {
        if (numero !== pedido) return;   // llegó tarde: ya se escribió otra cosa
        var nuevo = new DOMParser().parseFromString(html, "text/html").querySelector(destino);
        var actual = document.querySelector(destino);
        if (nuevo && actual) actual.innerHTML = nuevo.innerHTML;
        try { history.replaceState(null, "", url); } catch (e) {}
      })
      .catch(function () {});
  }
  form.addEventListener("input", function (e) {
    if (e.target.type !== "search" && e.target.type !== "text") return;
    clearTimeout(espera);
    espera = setTimeout(buscar, 300);
  });
  form.addEventListener("change", function (e) { if (e.target.tagName === "SELECT") buscar(); });
});

// Teclado del celular: mientras se escribe se esconde la barra de abajo (deja más lugar), el campo se centra
// en lo que queda visible y "Enter" pasa al campo siguiente en vez de enviar el formulario a medias.
(function () {
  var raiz = document.documentElement;
  var SIN_TECLADO = /^(checkbox|radio|button|submit|reset|hidden|range|color|file|date|time|month|week|datetime-local|image)$/;
  function escribe(el) {
    return !!el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && !SIN_TECLADO.test(el.type)));
  }
  function camposDe(form) {
    return Array.prototype.filter.call(form.elements, function (c) {
      return !c.disabled && c.type !== "hidden" && c.offsetParent !== null &&
             (escribe(c) || c.tagName === "SELECT" ||
              ((c.type === "date" || c.type === "time" || c.type === "month") && !c.value));   // fecha ya puesta: se salta
    });
  }

  document.addEventListener("focusin", function (e) {
    if (!escribe(e.target)) return;
    raiz.classList.add("escribiendo");
    var campo = e.target;
    setTimeout(function () {   // cuando el teclado ya subió
      try { campo.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (x) { campo.scrollIntoView(); }
    }, 320);
  });
  document.addEventListener("focusout", function () {
    setTimeout(function () { if (!escribe(document.activeElement)) raiz.classList.remove("escribiendo"); }, 120);
  });
  // Si el teclado se cierra con "atrás" sin salir del campo, la barra vuelve
  if (window.visualViewport) {
    var alto = window.visualViewport.height;
    window.visualViewport.addEventListener("resize", function () {
      var h = window.visualViewport.height;
      if (h > alto - 80 && raiz.classList.contains("escribiendo") && h >= window.innerHeight * 0.9) raiz.classList.remove("escribiendo");
      alto = Math.max(alto, h);
    });
  }

  // "Siguiente" en el teclado hasta el último campo; ahí "Listo" (envía)
  document.querySelectorAll("form").forEach(function (form) {
    if (form.hasAttribute("data-busqueda-vivo") || form.getAttribute("role") === "search") return;
    var campos = camposDe(form);
    campos.forEach(function (c, i) {
      if (escribe(c) && !c.hasAttribute("enterkeyhint")) c.setAttribute("enterkeyhint", i < campos.length - 1 ? "next" : "done");
    });
  });
  document.addEventListener("keydown", function (e) {
    var el = e.target;
    if (e.key !== "Enter" || !escribe(el) || el.tagName === "TEXTAREA" || el.type === "search" || !el.form) return;
    if (el.form.hasAttribute("data-busqueda-vivo") || el.form.getAttribute("role") === "search") return;
    var campos = camposDe(el.form), i = campos.indexOf(el);
    if (i > -1 && i < campos.length - 1) { e.preventDefault(); campos[i + 1].focus(); }
  });

  // Nombres con mayúscula inicial y sin corrector; correos sin mayúsculas
  document.querySelectorAll("input[name$='nombres'], input[name$='apellidos']").forEach(function (c) {
    c.setAttribute("autocapitalize", "words"); c.setAttribute("spellcheck", "false"); c.setAttribute("autocorrect", "off");
  });
  document.querySelectorAll("input[type=email]").forEach(function (c) {
    c.setAttribute("autocapitalize", "none"); c.setAttribute("spellcheck", "false"); c.setAttribute("autocorrect", "off");
  });
})();

// Cobrar varios meses: el monto es el total de los meses elegidos (y no se cambia a mano)
(function () {
  var grupo = document.querySelector("[data-elegir-meses]");
  if (!grupo) return;
  var monto = document.getElementById("monto"), texto = document.querySelector("[data-periodos-elegidos]");
  var soloLectura = monto && monto.readOnly;
  function poner() {
    var e = grupo.querySelector("input:checked");
    if (!e || !monto) return;
    var varios = e.value !== "1";
    monto.value = e.getAttribute("data-total");
    monto.readOnly = soloLectura || varios;
    if (texto) texto.textContent = varios ? "Meses: " + e.getAttribute("data-periodos") : "";
  }
  grupo.addEventListener("change", poner);
  poner();
})();

// Deudores: "Avisar a todos" abre los WhatsApp uno tras otro (cada toque, el siguiente)
(function () {
  var boton = document.querySelector("[data-avisar-todos]");
  if (!boton) return;
  var i = 0;
  boton.addEventListener("click", function () {
    var enlaces = document.querySelectorAll("[data-aviso-wa]");
    if (i >= enlaces.length) { i = 0; enlaces.forEach(function (a) { a.classList.remove("enviado"); }); }
    var a = enlaces[i++];
    window.open(a.href, "_blank", "noopener");
    a.classList.add("enviado");
    boton.lastChild.textContent = i < enlaces.length
      ? " Siguiente: " + enlaces[i].getAttribute("data-nombre") + " (" + (i + 1) + " de " + enlaces.length + ")"
      : " Listo: se avisó a todos";
  });
})();

// <form data-un-solo-envio>: desactiva el botón al enviar para evitar un doble cobro por doble clic
// (va al final: corre después de la confirmación, si el usuario cancela no se desactiva)
document.addEventListener("submit", function (e) {
  if (!e.defaultPrevented && e.target.hasAttribute("data-un-solo-envio")) {
    e.target.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = true; });
  }
});

// Celular: cada fila de tabla se muestra como tarjeta. A cada celda se le pone el título de su columna
// (data-label) para que el CSS lo escriba al lado del dato. No aplica al mapa de calor ni a tablas resumen.
function tablasComoTarjetas(raiz) {
  (raiz || document).querySelectorAll("table.tabla:not(.calor):not(.tabla-simple)").forEach(function (tabla) {
    var titulos = [];
    tabla.querySelectorAll("thead th").forEach(function (th) {
      for (var i = 0; i < (th.colSpan || 1); i++) titulos.push(th.textContent.trim());
    });
    tabla.querySelectorAll("tbody tr").forEach(function (fila) {
      var columna = 0;
      Array.prototype.forEach.call(fila.cells, function (celda) {
        var titulo = celda.colSpan > 1 ? "" : (titulos[columna] || "");
        if (titulo === "Acciones") titulo = "";  // los botones van solos, a lo ancho
        celda.setAttribute("data-label", titulo);
        columna += celda.colSpan || 1;
        // Junta todo el contenido de la celda en un solo bloque para que el dato no se reparta
        if (titulo && !celda.querySelector(":scope > .valor")) {
          var valor = document.createElement("div");
          valor.className = "valor";
          while (celda.firstChild) valor.appendChild(celda.firstChild);
          celda.appendChild(valor);
        }
        if (!titulo && celda.cellIndex > 0 && celda.querySelector(".boton") && !celda.querySelector(":scope > .valor")) {
          var acciones = document.createElement("div");
          acciones.className = "valor";
          while (celda.firstChild) acciones.appendChild(celda.firstChild);
          celda.appendChild(acciones);
        }
      });
    });
    tabla.classList.add("tabla-tarjetas");
    if (tabla.parentElement.classList.contains("tabla-envoltura")) tabla.parentElement.classList.add("envoltura-tarjetas");
  });
}
tablasComoTarjetas();
document.addEventListener("contenido-actualizado", function () { tablasComoTarjetas(); });

// Menú "Más" del celular: se abre con el teclado (Enter/Espacio) y se cierra con Escape
(function () {
  var casilla = document.getElementById("menu-abrir");
  if (!casilla) return;
  document.querySelectorAll("label[for=menu-abrir][role=button]").forEach(function (b) {
    b.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); casilla.checked = !casilla.checked; }
    });
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") casilla.checked = false; });
})();

// TIEMPO REAL en todas las pantallas: cada 5 s (y al volver a la app) se pregunta si cambió algo
// en la base. Si cambió, la pantalla se actualiza sola:
//  - las zonas "en vivo" (data-vivo) se refrescan sin recargar;
//  - el resto de la página se vuelve a cargar, en el mismo lugar del scroll;
//  - si la persona está escribiendo en un formulario, NO se borra nada: aparece un aviso con un botón.
(function () {
  var cuerpo = document.body, url = cuerpo.getAttribute("data-url-cambios");
  if (!url) return;
  var huella = cuerpo.getAttribute("data-huella"), revisando = false, SEGUNDOS = 5;

  // Volver al mismo lugar después de recargar
  try {
    var guardado = sessionStorage.getItem("scroll:" + location.pathname + location.search);
    if (guardado) { sessionStorage.removeItem("scroll:" + location.pathname + location.search); window.scrollTo(0, +guardado); }
  } catch (e) {}

  var editando = false;
  document.addEventListener("input", function (e) {
    if (e.target.closest("main form")) editando = true;
  });
  document.addEventListener("submit", function () { editando = false; });

  function avisar() {
    var aviso = document.getElementById("aviso-cambios");
    if (aviso) { aviso.hidden = false; return; }
    aviso = document.createElement("p");
    aviso.id = "aviso-cambios";
    aviso.className = "mensaje mensaje-aviso aviso-cambios";
    aviso.setAttribute("role", "status");
    aviso.innerHTML = "<span>Hay datos nuevos. Termina lo que estás escribiendo y actualiza.</span>";
    var boton = document.createElement("button");
    boton.type = "button"; boton.className = "boton boton-chico"; boton.textContent = "Actualizar";
    boton.addEventListener("click", recargar);
    aviso.appendChild(boton);
    var main = document.querySelector("main");
    main.insertBefore(aviso, main.firstChild);
  }

  function recargar() {
    try { sessionStorage.setItem("scroll:" + location.pathname + location.search, String(window.scrollY)); } catch (e) {}
    location.reload();
  }

  function aplicarCambio() {
    var zonas = document.querySelectorAll("[data-vivo]");
    if (zonas.length) {
      document.dispatchEvent(new CustomEvent("datos-cambiaron"));   // las zonas en vivo se refrescan solas
    } else if (editando) {
      avisar();
    } else {
      recargar();
    }
  }

  function revisar() {
    if (revisando || document.hidden) return;
    revisando = true;
    fetch(url, { credentials: "same-origin", headers: { "X-Consulta-Automatica": "1" } })
      .then(function (r) { if (!r.ok || r.redirected) throw new Error("sin sesión"); return r.json(); })
      .then(function (d) {
        if (!huella) { huella = d.huella; return; }
        if (d.huella && d.huella !== huella) { huella = d.huella; aplicarCambio(); }
      })
      .catch(function () {})
      .then(function () { revisando = false; });
  }

  setInterval(revisar, SEGUNDOS * 1000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) revisar(); });
  window.addEventListener("focus", revisar);
})();

// Pantallas en vivo: <div data-vivo="45"> se vuelve a pedir al servidor cada 45 s y se reemplaza
// sin recargar toda la página. El refresco automático no cuenta como actividad (la sesión igual expira).
(function () {
  var zona = document.querySelector("[data-vivo]");
  if (!zona) return;
  var segundos = parseInt(zona.getAttribute("data-vivo"), 10) || 45;
  var ultima = Date.now();

  function mostrarHace() {
    var el = zona.querySelector("[data-hace]");
    if (!el) return;
    var s = Math.round((Date.now() - ultima) / 1000);
    el.textContent = s < 60 ? "hace " + s + " s" : "hace " + Math.floor(s / 60) + " min";
  }

  function actualizar(automatico) {
    fetch(location.href, { credentials: "same-origin", headers: automatico ? { "X-Consulta-Automatica": "1" } : {} })
      .then(function (r) { if (!r.ok) throw new Error(r.status === 503 ? "base" : r.status); return r.text(); })
      .then(function (html) {
        var nueva = new DOMParser().parseFromString(html, "text/html").querySelector("[data-vivo]");
        if (!nueva) throw new Error("La sesión se cerró");
        zona.innerHTML = nueva.innerHTML;
        ultima = Date.now();
        mostrarHace();
        document.dispatchEvent(new CustomEvent("contenido-actualizado"));
      })
      .catch(function (error) {
        var aviso = zona.querySelector("[data-sin-conexion]");
        if (!aviso) return;
        if (error.message === "base") {
          aviso.textContent = "La base de datos no responde (SQL Server apagado). Se reintentará sola cada " + segundos + " s.";
        }
        aviso.hidden = false;
      });
  }

  zona.addEventListener("click", function (e) {
    if (e.target.closest("[data-actualizar]")) actualizar(false);
  });
  document.addEventListener("datos-cambiaron", function () { actualizar(true); });
  setInterval(function () { actualizar(true); }, segundos * 1000);
  setInterval(mostrarHace, 5000);
})();
