// Ayudas para los gráficos de Chart.js (Resumen de caja).
window.Graficos = (function () {
  // Color de una variable CSS del tema actual (claro u oscuro)
  function color(nombre) {
    return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
  }

  // Valores por defecto de Chart.js con los colores y la letra del tema actual
  function aplicarTema() {
    Chart.defaults.font.family = "Rubik, 'Segoe UI', Arial, sans-serif";
    Chart.defaults.color = color("--texto-suave");
    Chart.defaults.borderColor = color("--borde");
  }

  // Redibuja con los colores nuevos cuando se cambia el modo claro/oscuro
  function alCambiarTema(dibujar) {
    document.addEventListener("cambio-tema", function () { aplicarTema(); dibujar(); });
  }

  // Escribe el valor al final de cada barra (etiqueta directa, no solo color)
  var etiquetasBarras = {
    id: "etiquetasBarras",
    afterDatasetsDraw: function (chart, args, opciones) {
      var ctx = chart.ctx, formato = opciones.formato || String;
      ctx.save();
      ctx.fillStyle = color("--texto");
      ctx.font = "700 12px Rubik, sans-serif";
      chart.data.datasets.forEach(function (ds, i) {
        var meta = chart.getDatasetMeta(i);
        if (meta.hidden || meta.type !== "bar") return;
        meta.data.forEach(function (barra, j) {
          var v = ds.data[j];
          if (v === null || v === undefined) return;
          var horizontal = chart.options.indexAxis === "y";
          ctx.textAlign = horizontal ? "left" : "center";
          ctx.textBaseline = horizontal ? "middle" : "bottom";
          ctx.fillText(formato(v), horizontal ? barra.x + 5 : barra.x, horizontal ? barra.y : barra.y - 3);
        });
      });
      ctx.restore();
    }
  };

  aplicarTema();
  return { color: color, alCambiarTema: alCambiarTema, etiquetasBarras: etiquetasBarras };
})();
