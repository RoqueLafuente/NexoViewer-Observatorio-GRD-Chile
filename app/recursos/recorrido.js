/* Recorrido guiado del Observatorio (recorrido.py lo inyecta con st.html después de driver.js y de `datos`).
   Idempotente: Streamlit puede volver a insertar este script en cada actualización de la página. */
(function () {
  var w = window;
  var datos = w.grdRecorridoDatos || {pagina: "", pasos: []};
  var CLAVE = "grd_recorrido_";

  // Todo acceso a localStorage va en try/catch: si el navegador lo bloquea, el recorrido no se abre solo.
  function yaVisto(pagina) {
    try {
      return w.localStorage.getItem(CLAVE + pagina) !== null;
    } catch (e) {
      return null;
    }
  }
  function marcarVisto(pagina) {
    try {
      w.localStorage.setItem(CLAVE + pagina, "1");
      return true;
    } catch (e) {
      return false;
    }
  }

  function quitarMarca(pagina) {
    try {
      w.localStorage.removeItem(CLAVE + pagina);
    } catch (e) {}
  }

  w.grdRecorridoPasos = w.grdRecorridoPasos || {};
  w.grdRecorridoPasos[datos.pagina] = datos.pasos;
  w.grdRecorridoPagina = datos.pagina;

  if (!w.grdRecorrido) {
    // Un elemento se ve si tiene tamaño y cae dentro de la ventana a lo ancho (la barra lateral plegada queda a la izquierda).
    function seVe(el) {
      var r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.right > 0 && r.left < w.innerWidth;
    }

    // `.st-key-<ancla>`; un ancla con «*» al final (lectura_resumen_*) es cualquier clave con ese prefijo.
    function buscar(ancla) {
      if (ancla.charAt(ancla.length - 1) === "*") return document.querySelector("[class*='st-key-" + ancla.slice(0, -1) + "']");
      return document.querySelector(".st-key-" + ancla);
    }

    // Un ancla más alta que la ventana (el mosaico de gráficos) no deja lugar a la tarjeta: se resalta su primera tarjeta
    // de gráfico (el contenedor con borde que envuelve `st-key-figura_*`), como ejemplo.
    function objetivo(el) {
      // El ancla de pestañas envuelve también sus paneles: se resalta solo la fila de pestañas.
      var lista = el.className.indexOf("st-key-pestanas_") >= 0 && el.querySelector("[role='tablist']");
      if (lista) return lista;
      if (el.getBoundingClientRect().height <= w.innerHeight * 0.7) return el;
      var fig = el.querySelector("[class*='st-key-figura_']");
      for (var e = fig; e && e !== el; e = e.parentElement) {
        if (e.getAttribute("data-testid") === "stVerticalBlock" && parseFloat(w.getComputedStyle(e).borderTopWidth) > 0) return e;
      }
      return fig || el;
    }

    // En pantallas angostas la barra lateral abierta se dibuja sobre el contenido. Si ningún paso apunta a algo de la barra,
    // se pliega con su propio botón; devuelve true si lo hizo.
    function plegarBarra(pasos) {
      if (w.innerWidth > 768) return false;
      var barra = document.querySelector("[data-testid='stSidebar']");
      var boton = document.querySelector("[data-testid='stSidebarCollapseButton'] button");
      if (!barra || !boton || barra.getBoundingClientRect().right <= 0) return false;
      var enBarra = pasos.some(function (p) {
        var el = p.ancla && buscar(p.ancla);
        return el && barra.contains(el);
      });
      if (enBarra) return false;
      boton.click();
      return true;
    }

    // Tiempos (ms) de las transiciones entre pasos. Con «reducir movimiento» no se usa ninguno: todo es instantáneo.
    var T_SALIDA = 180;     // la tarjeta del paso anterior se desvanece antes de que nada se mueva
    var T_ESCENARIO = 900;  // opción `duration` de Driver.js: el recorte viaja al siguiente elemento (a la vista tarda ~la mitad por su curva)
    var T_TARJETA = 420;    // la tarjeta nueva aparece deslizándose desde donde estaba la anterior
    var T_CIERRE = 320;     // al terminar se desvanecen el fondo y la tarjeta
    var T_ESPERA_MAX = 3000; // tope de espera a que el desplazamiento termine antes de mostrar la tarjeta

    function igual(a, b) {
      return !!a && !!b && Math.abs(a.top - b.top) < 0.5 && Math.abs(a.left - b.left) < 0.5 &&
        Math.abs(a.width - b.width) < 0.5 && Math.abs(a.height - b.height) < 0.5;
    }
    function acotar(n) { return Math.max(-320, Math.min(320, n)); }

    // Abre el recorrido de `pagina`; cada paso cuya ancla no se dibujó en la vista se omite, y si está oculta la
    // tarjeta va al centro.
    w.grdRecorrido = function (pagina) {
      var lib = w.driver && w.driver.js;
      var pasos = (w.grdRecorridoPasos[pagina] || []).filter(function (p) {
        return !p.ancla || buscar(p.ancla);
      });
      if (!lib || !pasos.length) return false;
      w.grdRecorridoCerrar();
      var quieto = w.matchMedia && w.matchMedia("(prefers-reduced-motion: reduce)").matches;
      var ocupado = false, cerrando = false, origen = null;
      var vigente = function () { return !!w.grdRecorridoActivo && w.grdRecorridoActivo.driver === d && d.isActive(); };

      // Paso siguiente o anterior sin saltos: la tarjeta actual se desvanece, luego Driver.js mueve el recorte (y
      // desplaza la página con suavidad) y la tarjeta nueva espera a que todo se quede quieto antes de aparecer.
      var ir = function (delta) {
        if (ocupado || cerrando) return;
        var destino = (d.getConfig("steps") || [])[d.getActiveIndex() + delta];
        if (!destino) { if (delta > 0) cerrar(); return; }
        ocupado = true;
        var pop = d.getState("popover");
        var tarjeta = pop && pop.wrapper;
        origen = tarjeta ? tarjeta.getBoundingClientRect() : null;
        if (tarjeta) {
          tarjeta.style.transition = "opacity " + T_SALIDA + "ms ease";
          tarjeta.style.opacity = "0";
          tarjeta.style.pointerEvents = "none";
        }
        w.setTimeout(function () {
          if (!vigente()) return;
          if (delta > 0) d.moveNext(); else d.movePrevious();
        }, T_SALIDA);
        w.setTimeout(function () { ocupado = false; }, T_SALIDA + T_ESPERA_MAX + T_TARJETA);  // por si algo no termina
      };

      // La tarjeta recién creada nace invisible; aparece cuando el elemento resaltado lleva unos cuadros sin moverse (el
      // desplazamiento terminó) y, si el recorte aún viaja, cuando su posición ya es la definitiva.
      var preparar = function (tarjeta) {
        tarjeta.style.transition = "none";
        tarjeta.style.opacity = "0";
        tarjeta.style.pointerEvents = "none";
        var el = d.getActiveElement();
        var desde = origen, inicial = el.getBoundingClientRect(), previa = null, estables = 0;
        var t0 = Date.now(), refrescada = false;
        origen = null;
        var mostrar = function () {
          var fin = tarjeta.getBoundingClientRect();
          var dx = desde ? acotar(desde.left - fin.left) : 0, dy = desde ? acotar(desde.top - fin.top) : 14;
          tarjeta.style.transform = "translate(" + dx + "px," + dy + "px)";
          void tarjeta.offsetWidth;
          tarjeta.style.transition = "opacity " + T_TARJETA + "ms ease, transform " + T_TARJETA + "ms cubic-bezier(.4,0,.2,1)";
          tarjeta.style.opacity = "1";
          tarjeta.style.transform = "none";
          tarjeta.style.pointerEvents = "";
          w.setTimeout(function () {
            tarjeta.style.transition = tarjeta.style.transform = tarjeta.style.opacity = "";
            ocupado = false;
          }, T_TARJETA + 30);
        };
        var paso = function () {
          if (!tarjeta.isConnected || !vigente()) return;
          var r = el.getBoundingClientRect();
          estables = igual(r, previa) ? estables + 1 : 0;
          previa = r;
          var viaja = !!d.getState("__transitionCallback");
          var vencido = Date.now() - t0 > T_ESPERA_MAX;
          if (estables >= 3 && (igual(r, inicial) || !viaja) || vencido) {
            if (!igual(r, inicial) && !refrescada && !vencido) {  // hubo desplazamiento: la tarjeta se recoloca antes de mostrarse
              refrescada = true;
              inicial = r;
              d.refresh();
            } else {
              mostrar();
              return;
            }
          }
          w.requestAnimationFrame(paso);
        };
        w.requestAnimationFrame(paso);
      };

      // Cierre: el fondo y la tarjeta se desvanecen y luego se destruye el recorrido.
      var cerrar = function () {
        if (cerrando || !d.isActive()) return;
        if (quieto) { d.destroy(); return; }
        cerrando = true;
        var velo = document.querySelector(".driver-overlay");
        var pop = d.getState("popover");
        [velo, pop && pop.wrapper].forEach(function (nodo) {
          if (!nodo) return;
          nodo.style.transition = "opacity " + T_CIERRE + "ms ease";
          nodo.style.opacity = "0";
        });
        w.setTimeout(function () { if (d.isActive()) d.destroy(); }, T_CIERRE);
      };

      var d = lib.driver({
        animate: !quieto,
        smoothScroll: !quieto,
        duration: T_ESCENARIO,
        overlayColor: "#142742",
        overlayOpacity: 0.6,
        overlayClickBehavior: "none",
        disableActiveInteraction: true,
        allowClose: true,
        stagePadding: 6,
        stageRadius: 12,
        popoverClass: "grd-recorrido",
        showProgress: pasos.length > 1,
        progressText: "Paso {{current}} de {{total}}",
        showButtons: ["next", "previous"],
        nextBtnText: "Siguiente",
        prevBtnText: "Anterior",
        doneBtnText: "Listo",
        steps: pasos.map(function (p) {
          var paso = {popover: {title: p.titulo, description: p.texto}};
          var el = p.ancla && buscar(p.ancla);
          if (el && seVe(el)) paso.element = objetivo(el);
          return paso;
        }),
        onNextClick: function () { if (quieto) { if (d.hasNextStep()) d.moveNext(); else d.destroy(); } else ir(1); },
        onPrevClick: function () { if (quieto) d.movePrevious(); else ir(-1); },
        onDestroyStarted: function () { cerrar(); },
        onPopoverRender: function (popover) {
          if (!d.isLastStep()) {
            var omitir = document.createElement("button");
            omitir.type = "button";
            omitir.className = "grd-recorrido-omitir";
            omitir.textContent = "Omitir";
            omitir.addEventListener("click", cerrar);
            popover.footerButtons.insertBefore(omitir, popover.footerButtons.firstChild);
          }
          if (!quieto) preparar(popover.wrapper);
        },
        onDestroyed: function () {
          if (w.grdRecorridoActivo && w.grdRecorridoActivo.driver === d) w.grdRecorridoActivo = null;
        }
      });
      w.grdRecorridoActivo = {pagina: pagina, driver: d};
      if (plegarBarra(pasos)) {  // en pantallas angostas la barra abierta tapa el contenido: se pliega y luego se abre el recorrido
        w.setTimeout(function () {
          if (w.grdRecorridoActivo && w.grdRecorridoActivo.driver === d) d.drive();
        }, 400);
      } else {
        d.drive();
      }
      return true;
    };

    w.grdRecorridoCerrar = function () {
      var activo = w.grdRecorridoActivo;
      w.grdRecorridoActivo = null;
      if (activo && activo.driver.isActive()) activo.driver.destroy();
    };

    // «Ver recorrido» es HTML sin Streamlit: el clic abre el recorrido sin volver a ejecutar la página.
    document.addEventListener("click", function (e) {
      var boton = e.target.closest && e.target.closest(".grd-ver-recorrido");
      if (boton) w.grdRecorrido(boton.getAttribute("data-pagina"));
    });
    // Streamlit desplaza un contenedor interno, no la ventana, y Driver.js solo escucha la ventana: sin esto, el recorte
    // del fondo queda donde estaba el elemento antes de desplazarse.
    var pendiente = false;
    document.addEventListener("scroll", function () {
      if (pendiente || !w.grdRecorridoActivo) return;
      pendiente = true;
      w.requestAnimationFrame(function () {
        pendiente = false;
        var activo = w.grdRecorridoActivo;
        // Mientras Driver.js mueve el recorte hacia el paso nuevo lleva su propia cuenta; refrescar lo haría saltar.
        if (activo && activo.driver.isActive() && !activo.driver.getState("__transitionCallback")) activo.driver.refresh();
      });
    }, true);
    // Atrás/adelante del navegador cambia de página: se cierra antes de que la nueva termine de dibujarse.
    w.addEventListener("popstate", function () { w.grdRecorridoCerrar(); });
  }

  // Al cambiar de página se cierra el recorrido de la anterior.
  var activo = w.grdRecorridoActivo;
  if (activo && activo.pagina !== datos.pagina) w.grdRecorridoCerrar();

  // Primera visita: se abre solo si la marca no existe (lectura sin error); sin localStorage, nunca se abre solo.
  if (!datos.pasos.length || yaVisto(datos.pagina) !== false) return;
  w.grdRecorridoEsperando = w.grdRecorridoEsperando || {};
  if (w.grdRecorridoEsperando[datos.pagina]) return;
  w.grdRecorridoEsperando[datos.pagina] = true;
  var intentos = 0, quietas = 0;
  var reloj = w.setInterval(function () {
    intentos += 1;
    var app = document.querySelector("[data-test-script-state]");
    var corriendo = app && app.getAttribute("data-test-script-state") === "running";
    quietas = corriendo ? 0 : quietas + 1;
    if (quietas < 3 && intentos < 60) return;
    w.clearInterval(reloj);
    w.grdRecorridoEsperando[datos.pagina] = false;
    if (w.grdRecorridoPagina !== datos.pagina || w.grdRecorridoActivo) return;
    if (yaVisto(datos.pagina) !== false) return;
    // Invariante: se abre solo si la marca se pudo guardar (si no, reabriría en cada visita) y nunca queda una marca
    // de un recorrido que no se mostró.
    if (!marcarVisto(datos.pagina)) return;
    if (!w.grdRecorrido(datos.pagina)) quitarMarca(datos.pagina);
  }, 300);
})();
