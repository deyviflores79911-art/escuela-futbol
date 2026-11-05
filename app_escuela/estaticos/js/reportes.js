// Resumen de caja: gráfico de lo cobrado por método, con datos de /api/reportes/caja.
// Se vuelve a dibujar cuando la zona en vivo se actualiza sola y al cambiar el tema.
(function () {
  var grafico = null;

  function dibujar() {
    var zona = document.getElementById("caja-vivo");
    var lienzo = document.getElementById("grafico-caja");
    if (!zona || !lienzo) return;
    fetch(zona.dataset.urlDatos, { credentials: "same-origin", headers: { "X-Consulta-Automatica": "1" } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (grafico) grafico.destroy();
        var metodos = d.por_metodo.map(function (m) { return m.metodo; });
        var totales = d.por_metodo.map(function (m) { return m.total; });
        var maximo = Math.max.apply(null, totales);
        grafico = new Chart(lienzo, {
          type: "bar",
          data: { labels: metodos, datasets: [{
            data: totales, borderRadius: 6, maxBarThickness: 30,
            // El método con más cobro en naranja; los demás en plomo (además llevan su monto escrito)
            backgroundColor: totales.map(function (t) {
              return t === maximo && t > 0 ? Graficos.color("--naranja") : Graficos.color("--grafico-bajo");
            })
          }] },
          options: {
            indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 90 } },
            plugins: {
              legend: { display: false },
              etiquetasBarras: { formato: function (v) { return "Bs " + v.toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); } },
              tooltip: { callbacks: { label: function (c) {
                var m = d.por_metodo[c.dataIndex];
                return m.cantidad + " pago" + (m.cantidad === 1 ? "" : "s") + " · Bs " + m.total.toFixed(2).replace(".", ",");
              } } }
            },
            scales: { x: { beginAtZero: true }, y: { ticks: { color: Graficos.color("--texto") }, grid: { display: false } } }
          },
          plugins: [Graficos.etiquetasBarras]
        });
      })
      .catch(function () {});
  }

  dibujar();
  document.addEventListener("contenido-actualizado", dibujar);
  Graficos.alCambiarTema(dibujar);
})();
