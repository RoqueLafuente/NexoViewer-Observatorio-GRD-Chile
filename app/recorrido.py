"""Recorrido guiado: por página, unos pocos pasos que oscurecen la pantalla y resaltan un elemento con una tarjeta al lado.

Usa Driver.js (MIT), copiado en `recursos/driver/` (versión fija, sin CDN), y el script `recursos/recorrido.js`. Todo
corre en el navegador: Siguiente, Anterior y Omitir no vuelven a ejecutar la página. Se abre solo la primera vez que se
entra a cada página con recorrido (marca `grd_recorrido_<página>` en `localStorage`; si el navegador no la deja leer o
escribir, no se abre solo) y se repite con el botón «Ver recorrido».

Cada `ancla` es una clave de `anclas.ANCLAS[página]` (selector `.st-key-<ancla>`; con «*» al final, cualquier clave con ese
prefijo); `None` es una burbuja centrada. El
script salta los pasos cuya ancla no se dibujó en la vista, centra la tarjeta si el elemento está oculto (barra lateral
plegada) y, si el ancla es más alta que la ventana (el mosaico), resalta su primera tarjeta de gráfico.
"""
import base64
import json
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path

import streamlit as st

import anclas

_RECURSOS = Path(__file__).parent / "recursos"
_DRIVER_JS = _RECURSOS / "driver" / "driver.js.iife.js"
_DRIVER_CSS = _RECURSOS / "driver" / "driver.css"
_SCRIPT = _RECURSOS / "recorrido.js"


@dataclass(frozen=True)
class Paso:
    ancla: str | None  # clave de anclas.ANCLAS; None = burbuja centrada
    titulo: str
    texto: str  # cabe en dos líneas de la tarjeta


RECORRIDOS: dict[str, list[Paso]] = {
    "Inicio": [
        Paso(None, "Bienvenida a NexoViewer",
             "Esto es el resumen. En el menú de arriba están Análisis, Hospitales, Descargas y Metodología."),
        Paso("pie_filtros", "Filtros y «Aplicar»",
             "Eliges los filtros en la barra lateral; los números cambian solo al pulsar «Aplicar»."),
        Paso("kpis_inicio", "Cifras clave",
             "Egresos (episodios, no personas), estancia mediana, casemix y mortalidad de lo aplicado."),
        Paso("mosaico_inicio", "Gráficos del resumen",
             "Bajo cada gráfico, como este, hay una lectura rápida; el «?» explica qué muestra."),
        Paso("plantillas", "Plantillas",
             "Aquí puedes cargar una plantilla predefinida como ejemplo y luego pulsar «Aplicar»."),
    ],
    "Análisis": [
        Paso("pestanas_analisis", "Una pestaña por pregunta",
             "Cada pestaña responde una pregunta; los filtros que no usa quedan apagados."),
        Paso("lectura_resumen_*", "El resumen de la pregunta",
             "Una línea dice lo principal de lo aplicado."),
        Paso("graficos_analisis", "Gráficos con su lectura",
             "Cada gráfico, como este, trae una lectura rápida y un «?» que explica qué muestra."),
        Paso("metodo_analisis", "Cómo se calcula",
             "Este desplegable trae la fórmula, las tablas de origen y las advertencias."),
    ],
    "Hospitales": [  # como en Análisis: solo lo siempre visible y la pestaña inicial (Actividad)
        Paso("hosp_selector", "Elige un hospital",
             "Búscalo por su nombre o su código DEIS; cambia la ficha, el mapa y todas las pestañas."),
        Paso("hosp_ficha", "Ficha del hospital",
             "Datos del catálogo del DEIS y, debajo, sus cifras del año; al lado, el mapa con su ubicación."),
        Paso("pestanas_hospitales", "Una pestaña por tema",
             "Actividad, edad y origen, casos y estancia, comorbilidad y camas; solo se calcula la abierta."),
        Paso("hosp_actividad", "Actividad frente a la referencia",
             "Arriba eliges con qué compararlo: país, su región u otra. Egresos (episodios, no personas) y más."),
    ],
    "Descargas": [
        Paso("descargas_tablas", "Una tabla, dos formatos",
             "Cada tabla va en CSV y, las pequeñas, también en Excel, con hoja de filtros y cita."),
        Paso(None, "Solo egresos agrupados",
             "Los archivos traen episodios agrupados, nunca filas con datos de una persona."),
        Paso("franja", "Los filtros usados",
             "Lo que ves aplicado aquí arriba es lo que trae el archivo, y el Excel lo detalla."),
    ],
}

# Botón «Ver recorrido»: se inyecta al inicio de app.py (componentes.estilos) para que se vea bien antes de que
# termine de calcularse la página; montar() corre al final.
ESTILOS_BOTON = """
.grd-ver-recorrido { all: unset; cursor: pointer; display: inline-flex; align-items: center; gap: .3rem;
  color: #142742; font: inherit; font-size: .875rem; padding: .25rem .5rem; border-radius: 8px; }
.grd-ver-recorrido:hover { color: #1D5FAD; }
.grd-ver-recorrido:focus-visible { outline: 2px solid #1D5FAD; outline-offset: 2px; }
.grd-ver-recorrido .material-symbols-rounded { font-family: "Material Symbols Rounded"; font-size: 1.15rem; line-height: 1; }
"""

# Popover de Driver.js con los colores de la app (config.toml): fucsia #D6197A solo en «Siguiente»/«Listo».
_ESTILOS = """
.st-key-recorrido { display: none; }
.driver-overlay { z-index: 999995 !important; }  /* sobre la barra lateral (999991) y el menú de arriba (999990) */
.driver-popover.grd-recorrido { --driver-popover-font-family: Inter, "Source Sans Pro", sans-serif; color: #142742;
  border-radius: 12px; padding: 16px; min-width: 0; max-width: min(340px, calc(100vw - 32px)); }
.grd-recorrido .driver-popover-title { font-size: 16px; line-height: 1.35; padding-right: 0; }
.grd-recorrido .driver-popover-description { font-size: 14px; line-height: 1.45; }
.grd-recorrido .driver-popover-footer { flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.grd-recorrido .driver-popover-progress-text { color: #142742; opacity: .7; font-size: 13px; }
.grd-recorrido .driver-popover-navigation-btns { gap: 6px; }
.grd-recorrido .driver-popover-navigation-btns button + button { margin-left: 0; }
.grd-recorrido .driver-popover-footer-btn, .grd-recorrido .grd-recorrido-omitir { all: unset; box-sizing: border-box;
  cursor: pointer; font-size: 13px; line-height: 1.2; padding: 6px 10px; border-radius: 8px; color: #142742;
  background: #FFFFFF; border: 1px solid #E2E8F0; text-shadow: none; }
.grd-recorrido .grd-recorrido-omitir { border-color: transparent; }
.grd-recorrido .driver-popover-next-btn { background: #D6197A; border-color: #D6197A; color: #FFFFFF; }
.grd-recorrido .driver-popover-footer-btn:focus-visible, .grd-recorrido .grd-recorrido-omitir:focus-visible {
  outline: 2px solid #1D5FAD; outline-offset: 2px; }
.grd-recorrido .driver-popover-arrow-side-left { border-left-color: #FFFFFF; }
.grd-recorrido .driver-popover-arrow-side-right { border-right-color: #FFFFFF; }
.driver-fade .driver-popover.grd-recorrido { animation: none; }  /* la aparición de la tarjeta la anima recorrido.js */
.driver-fade .driver-overlay { animation-duration: .5s; }  /* apertura: el fondo se oscurece con suavidad */
@media (prefers-reduced-motion: reduce) { .driver-fade .driver-overlay, .driver-fade .driver-popover { animation: none; } }
"""

# Carga un script desde base64: DOMPurify (dentro de st.html) borra un <script> cuyo texto tiene «<» seguido de una letra,
# y Driver.js minificado los tiene. El script que se agrega con textContent corre una vez y se quita del <head>.
_CARGADOR = ("function grdCorrer(b){var t=new TextDecoder().decode(Uint8Array.from(atob(b),function(c){return c.charCodeAt(0)}));"
             "var s=document.createElement('script');s.textContent=t;document.head.appendChild(s);s.remove();}")


def _json(objeto) -> str:
    """JSON seguro dentro de <script>: sin «<» literal."""
    return json.dumps(objeto, ensure_ascii=False).replace("<", "\\u003c")


def pasos_json(pagina: str) -> str:
    """Los pasos de `pagina` en JSON; omite los de un ancla que no es de esa página (el JS salta además las que la vista
    no dibujó). Lista vacía si la página no tiene recorrido."""
    validas = set(anclas.ANCLAS.get(pagina, ()))

    def valida(ancla: str | None) -> bool:  # «x_*» vale si alguna clave de la página empieza con «x_» (una por pestaña)
        if ancla is None:
            return True
        return any(v.startswith(ancla[:-1]) for v in validas) if ancla.endswith("*") else ancla in validas

    # Driver.js pinta título y texto como innerHTML: se escapan para que nunca se lean como etiquetas.
    return _json([asdict(p) | {"titulo": escape(p.titulo), "texto": escape(p.texto)}
                  for p in RECORRIDOS.get(pagina, []) if valida(p.ancla)])


def script() -> str:
    """El JavaScript del recorrido (sin la librería)."""
    return _SCRIPT.read_text(encoding="utf-8")


def _b64(texto: str) -> str:
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


def html(pagina: str) -> str:
    """Estilos, Driver.js (una sola vez por pestaña del navegador) y el script con los pasos de `pagina`."""
    datos = f'{{"pagina": {_json(pagina)}, "pasos": {pasos_json(pagina)}}}'
    codigo = (f"{_CARGADOR}if(!(window.driver&&window.driver.js))grdCorrer('{_b64(_DRIVER_JS.read_text(encoding='utf-8'))}');"
              f"window.grdRecorridoDatos={datos};grdCorrer('{_b64(script())}');")
    return f"<style>{_DRIVER_CSS.read_text(encoding='utf-8')}{_ESTILOS}</style><script>{codigo}</script>"


def montar(pagina: str) -> None:
    """Inyecta el recorrido de `pagina`; va al final de app.py, cuando sus anclas ya están dibujadas. En una página sin
    recorrido solo cierra el de otra página que hubiera quedado abierto."""
    with st.container(key="recorrido"):
        st.html(html(pagina), unsafe_allow_javascript=True)


def boton_ver_recorrido(pagina: str) -> None:
    """«Ver recorrido»: un botón HTML (no `st.button`) que abre el recorrido en el navegador sin volver a ejecutar la
    página. No dibuja nada si `pagina` no tiene recorrido."""
    if not RECORRIDOS.get(pagina):
        return
    st.html(f'<button type="button" class="grd-ver-recorrido" data-pagina="{escape(pagina)}" '
            f'title="Muestra de nuevo el recorrido de esta página">'
            f'<span class="material-symbols-rounded" aria-hidden="true">help</span>Ver recorrido</button>')
