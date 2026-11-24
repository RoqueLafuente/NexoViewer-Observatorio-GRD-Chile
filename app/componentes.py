"""Piezas pequeñas de interfaz Streamlit del dashboard."""
from __future__ import annotations

import streamlit as st

from graficos import ALTURA_MAPA_HOSPITAL, ALTURA_MAPA_HOSPITAL_CELULAR
from indicadores import Variacion
from recorrido import ESTILOS_BOTON
from textos import GLOSARIO


_COLOR = {"positivo": "green", "negativo": "red", "neutro": "gray"}

# Filas que se reparten y pasan de línea: cada elemento crece hasta llenar la fila y, si no cabe con su ancho
# mínimo (px), baja a la línea siguiente. El prefijo va en la `key` del contenedor (clase CSS `st-key-<key>`).
FILAS = {
    "fkpi": 440,  # pares de KPI: dos tarjetas de 210 px más el espacio entre ellas
    "fpar": 210,  # tarjetas de KPI: lo mínimo para que «898.911» y su variación no se corten
    "fgraf": 360,  # tarjetas de gráfico del mosaico
    "fdato": 170,  # datos rotulados de la ficha de un hospital
    "fmitad": 448,  # mitades lado a lado (hospital y referencia) solo si cada tabla por severidad (~440 px) cabe entera
}
ANCHO_KPI_CAMAS = 145  # px mínimos de las 5 tarjetas de camas: caben las 5 en una fila desde 1280 px y no quedan 4 + 1
ANCHO_CIFRA_RESUMEN = 130  # px mínimos de cada cifra de «En cifras» (Hospitales): 3 por línea en la ficha, 2 en un celular


def rem(px: float) -> str:
    """Ancho mínimo en rem (16 px = 1 rem): mide lo mismo con el texto normal y crece si la persona agranda el texto, así
    las tarjetas pasan de línea antes de que su texto se corte."""
    return f"{px / 16:g}rem"
# Fila de dos columnas («fcol»): los gráficos a la izquierda crecen 3 veces más que la columna de la derecha (el mapa);
# si no caben las dos, la derecha baja y ocupa todo el ancho.
ANCHO_IZQUIERDA, ANCHO_DERECHA = 740, 300
ANCHO_FICHA, ANCHO_MAPA_FICHA = 480, 260  # px mínimos de la ficha y de su mapa en Hospitales
ANCHO_DATO_CELULAR = 120  # px mínimos de cada dato de la ficha de un hospital en pantallas angostas
# Hospitales › cabecera, desde VENTANA_FICHA_MAPA px de ventana (PC y proyector): ficha y mapa van siempre lado a lado y
# la columna de la ficha (con «En cifras») manda el alto. La columna del mapa sale del flujo (`position: absolute`), así
# su contenido no estira la fila, y llena el alto que deja la ficha: el gráfico crece o se encoge (nunca bajo
# ALTO_MIN_MAPA_FICHA px) y el título, la lectura y los controles conservan su alto. Bajo ese ancho, el mapa pasa debajo con
# su alto de siempre.
VENTANA_FICHA_MAPA = 1000
ALTO_MIN_MAPA_FICHA = 200
ESTILO_MAPA_FICHA = (
    f'@media (min-width: {VENTANA_FICHA_MAPA}px) {{\n'
    '  .st-key-fcol_hosp { flex-wrap: nowrap !important; align-items: stretch !important; }\n'
    '  .st-key-fcol_hosp > div:last-child { position: relative; align-self: stretch; }\n'
    '  .st-key-fcol_hosp .st-key-hosp_mapa { position: absolute; inset: 0; display: flex; flex-direction: column; }\n'
    # el <style> del zoom no ocupa sitio (oculto sigue valiendo); la tarjeta, su bloque y el envoltorio del gráfico crecen
    '  .st-key-hosp_mapa > .stElementContainer:has(style) { display: none; }\n'
    '  .st-key-hosp_mapa > [data-testid="stLayoutWrapper"], '
    '.st-key-hosp_mapa > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"], '
    '.st-key-hosp_mapa [data-testid="stLayoutWrapper"]:has(> .st-key-figura_g_hosp_mapa) '
    '{ flex: 1 1 0 !important; min-height: 0 !important; display: flex !important; flex-direction: column !important; }\n'
    '  .st-key-figura_g_hosp_mapa { flex: 1 1 0 !important; min-height: 0 !important; }\n'
    # el gráfico toma el alto que sobra (nunca menos del mínimo): su marco va en absoluto dentro y Plotly lo sigue
    '  .st-key-figura_g_hosp_mapa > .stElementContainer:has(.stPlotlyChart) '
    f'{{ position: relative; flex: 1 1 0 !important; min-height: {ALTO_MIN_MAPA_FICHA}px !important; }}\n'
    '  .st-key-figura_g_hosp_mapa > .stElementContainer:has(.stPlotlyChart) > div '
    '{ position: absolute !important; inset: 0 !important; height: auto !important; }\n'
    '  .st-key-figura_g_hosp_mapa .stPlotlyChart { height: 100% !important; }\n'
    '}\n')

# Animaciones de entrada, solo CSS: se ven al abrir una página o una pestaña y cuando un gráfico se vuelve a dibujar
# (al cambiar un filtro). Se animan capas sin `transform` ni `clip-path` propios de Plotly, y con «backwards»: al
# terminar no queda nada aplicado. Las tarjetas suben y aparecen de a una; los gráficos con ejes se dibujan de izquierda a
# derecha; el donut gira; el mapa se pinta región por región, de norte a sur. Nada se mueve si el sistema pide
# reducir el movimiento.
PASO_TARJETAS, PASO_REGIONES = 0.07, 0.04  # s entre una tarjeta (o región) y la siguiente
ANIMACIONES = """
@keyframes grd-entrar { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes grd-barrer { from { clip-path: inset(-20% 100% -20% -20%); } to { clip-path: inset(-20%); } }
@keyframes grd-girar { from { opacity: 0; transform: rotate(-100deg) scale(.6); } to { opacity: 1; transform: none; } }
@keyframes grd-aparecer { from { opacity: 0; } to { opacity: 1; } }
@media (prefers-reduced-motion: no-preference) {
  TARJETAS, [data-testid="stMain"] [data-testid="stAlert"] { animation: grd-entrar .5s cubic-bezier(.2, .7, .2, 1) backwards; }
  .stPlotlyChart .overplot .mlayer { animation: grd-barrer .9s cubic-bezier(.3, .6, .2, 1) .15s backwards; }
  .stPlotlyChart .pielayer { animation: grd-girar .8s cubic-bezier(.2, .7, .2, 1) .15s backwards; transform-box: fill-box;
    transform-origin: center; }
  .stPlotlyChart .choroplethlocation { animation: grd-aparecer .5s ease-out backwards; }
}
"""


def estilos() -> str:
    """CSS chico para los anchos mínimos de las filas de `FILAS` y de «fcol», y las animaciones de entrada; se inyecta
    una vez en `app.py`."""
    reglas = "".join(f'[class*="st-key-{prefijo}_"] > div {{ flex: 1 1 {rem(minimo)}; }}\n'
                     for prefijo, minimo in FILAS.items())
    reglas += (f'[class*="st-key-fcol_"] > div:first-child {{ flex: 3 1 {rem(ANCHO_IZQUIERDA)}; }}\n'
               f'[class*="st-key-fcol_"] > div:last-child {{ flex: 1 1 {rem(ANCHO_DERECHA)}; }}\n'
               # Hospitales › cabecera: ficha con «En cifras» 2/3 y mapa 1/3; caben lado a lado desde ~760 px de contenido y
               # bajo eso el mapa pasa debajo
               f'.st-key-fcol_hosp > div:first-child {{ flex: 2 1 {rem(ANCHO_FICHA)}; }}\n'
               f'.st-key-fcol_hosp > div:last-child {{ flex: 1 1 {rem(ANCHO_MAPA_FICHA)}; }}\n'
               + ESTILO_MAPA_FICHA +
               f'.st-key-fpar_hosp_camas_kpi > div {{ flex-basis: {rem(ANCHO_KPI_CAMAS)}; }}\n'
               # «En cifras» bajo la ficha, en la columna izquierda: 3 tarjetas por línea (nunca 4: 4 × 30 % no cabe) y 2
               # cuando no caben con su mínimo; cifra algo menor que la de los KPI de las secciones, así «No aplica» y
               # «57.812» no se cortan
               f'.st-key-fpar_hosp_resumen > div {{ flex: 1 1 30%; min-width: {rem(ANCHO_CIFRA_RESUMEN)}; }}\n'
               '.st-key-hosp_resumen [data-testid="stMetricValue"] { font-size: 1.5rem; }\n'
               # el mapa de la ficha toma su alto de la tarjeta (no de la figura): más bajo cuando queda bajo la ficha;
               # con el zoom, la página fija `--alto-mapa` según la forma de la región
               f'.st-key-figura_g_hosp_mapa .stPlotlyChart {{ height: var(--alto-mapa, {ALTURA_MAPA_HOSPITAL}px); }}\n'
               f'@media (max-width: 768px) {{ .st-key-figura_g_hosp_mapa .stPlotlyChart '
               f'{{ height: min(var(--alto-mapa, {ALTURA_MAPA_HOSPITAL_CELULAR}px), {ALTURA_MAPA_HOSPITAL_CELULAR}px); }} }}\n'
               # el mapa de los hospitales de Inicio va a todo el ancho: 520 px de alto, 420 en celular
               f'.st-key-figura_g_mapa_hospitales .stPlotlyChart {{ height: {ALTURA_MAPA_HOSPITAL}px; }}\n'
               f'.st-key-figura_g_mapa_hospitales > .stElementContainer:has(.stPlotlyChart), .st-key-figura_g_mapa_hospitales > .stElementContainer:has(.stPlotlyChart) > div '
               f'{{ height: {ALTURA_MAPA_HOSPITAL}px !important; flex-basis: {ALTURA_MAPA_HOSPITAL}px !important; }}\n'
               f'@media (max-width: 768px) {{ .st-key-figura_g_mapa_hospitales .stPlotlyChart '
               f'{{ height: {ALTURA_MAPA_HOSPITAL_CELULAR}px; }}\n'
               f'.st-key-figura_g_mapa_hospitales > .stElementContainer:has(.stPlotlyChart), .st-key-figura_g_mapa_hospitales > .stElementContainer:has(.stPlotlyChart) > div '
               f'{{ height: {ALTURA_MAPA_HOSPITAL_CELULAR}px !important; flex-basis: {ALTURA_MAPA_HOSPITAL_CELULAR}px !important; }} }}\n'
               # en el celular, los datos de la ficha van de a dos por línea y no uno bajo otro
               f'@media (max-width: 640px) {{ [class*="st-key-fdato_"] > div {{ flex-basis: {rem(ANCHO_DATO_CELULAR)}; }} }}\n')
    # Textos que Streamlit corta con «…» y que aquí pasan a la línea siguiente: el rótulo de los KPI y los botones de
    # Descargas (columnas angostas a 1024 px o con el texto agrandado). Solo dentro de esos contenedores.
    reglas += ('[class*="st-key-fpar_"] [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"], '
               '.st-key-descargas_tablas [data-testid="stDownloadButton"] [data-testid="stMarkdownContainer"] '
               '{ white-space: normal; overflow: visible; text-overflow: clip; height: auto; }\n'
               '[class*="st-key-fpar_"] [data-testid="stMetricLabel"] p, '
               '.st-key-descargas_tablas [data-testid="stDownloadButton"] p { white-space: normal; }\n'
               # la lista del selector de hospital (fuera de la página, sin `key`: se reconoce por su rótulo) es de alto
               # fijo por opción; «114101 · Complejo Hospitalario Dr. Sótero del Río (Santiago, Puente Alto)» cabe en dos
               # líneas de letra algo menor en vez de cortarse con «…»
               '[role="listbox"][aria-label="Hospital"] [role="option"] > div '
               '{ white-space: normal; line-height: 1.15; font-size: .8125rem; }\n')
    # El pie de filtros usa el fondo de [theme.sidebar] de config.toml (#FFFFFF): Streamlit no expone una variable CSS.
    reglas += ('[class*="st-key-lectura_"] { border-left: 3px solid #D6197A; padding-left: .75rem; }\n'
               '[class*="st-key-figura_"] { position: relative; }\n'
               '[class*="st-key-ayuda_"] { position: absolute; top: .35rem; right: .3rem; width: auto; z-index: 2; }\n'
               '[class*="st-key-figura_"] .modebar-container { right: 1.8rem !important; }\n'
               '[data-testid="stLayoutWrapper"]:has(> .st-key-pie_filtros) { position: sticky; bottom: 0; z-index: 5; '
               'background: #FFFFFF; }\n'
               '.st-key-pie_filtros { padding: .5rem 0 .25rem; }\n'
               '.st-key-pie_filtros .st-key-aplicar button:not(:disabled) { background: #D6197A; border-color: #D6197A; }\n')
    tarjetas = [f'[class*="st-key-{prefijo}_"] > div' for prefijo in (*FILAS, "fcol")]
    reglas += ANIMACIONES.replace("TARJETAS", ", ".join(tarjetas))
    for i in range(2, 7):  # cada tarjeta de una fila entra un poco después de la anterior
        reglas += f'{", ".join(f"{t}:nth-child({i})" for t in tarjetas)} {{ animation-delay: {i * PASO_TARJETAS:.2f}s; }}\n'
    reglas += "".join(f'.stPlotlyChart .choroplethlocation:nth-child({i}) {{ animation-delay: {i * PASO_REGIONES:.2f}s; }}\n'
                      for i in range(1, 17))
    reglas += ESTILOS_BOTON
    return f"<style>\n{reglas}</style>"


def fila(prefijo: str, nombre: str, arriba: bool = False):
    """Fila horizontal que reparte su ancho entre sus elementos y estira cada uno al alto de su línea.

    Sin `height="stretch"` en los hijos: con varias líneas, «stretch» toma el alto de la fila entera, no el de la línea.
    Con `arriba=True` los elementos se alinean arriba y cada uno conserva su alto (la ficha y el mapa de Hospitales).
    """
    return st.container(horizontal=True, vertical_alignment="top" if arriba else "distribute", key=f"{prefijo}_{nombre}")


def ayuda_kpi(definicion: str | None, secciones: tuple[tuple[str, str], ...] = ()) -> str | None:
    """Texto del «?» de un KPI en Markdown: la definición y luego una sección por cada (título, texto)."""
    partes = ([definicion] if definicion else []) + [f"**{t}:** {s}" for t, s in secciones if s]
    return "\n\n".join(partes) or None


def mosaico(nombre: str):
    """Fila de tarjetas de gráfico: se reparten el ancho, pasan de línea y miden lo mismo de alto en cada línea."""
    return fila("fgraf", nombre)


def tarjeta_kpi(titulo: str, valor: str, var: Variacion, ayuda: str | None = None, icono: str | None = None,
                secciones: tuple[tuple[str, str], ...] = ()) -> None:
    """Muestra un KPI en una tarjeta con su variación coloreada; las secciones (por qué importa, referencia) van en el «?»."""
    texto = var.texto.strip()
    ayuda = ayuda_kpi(ayuda, secciones)
    with st.container(border=True):
        if var.mostrar and texto:
            st.metric(titulo, valor, delta=texto, delta_color=_COLOR[var.color],
                      delta_arrow="off", help=ayuda, icon=icono)  # el texto ya trae ↑ o ↓
        else:
            st.metric(titulo, valor, help=ayuda, icon=icono)
            if texto:
                st.caption(texto)


def fila_kpi(nombre: str) -> list:
    """Cuatro espacios para tarjetas de KPI, de a pares: 4 iguales en una fila si caben, 2×2 si no y una columna si es angosto.

    Los pares evitan quedar con 3 tarjetas arriba y 1 abajo; `nombre` distingue las filas de una misma página.
    """
    with fila("fkpi", nombre):
        pares = [fila("fpar", f"{nombre}_{i}") for i in range(2)]
    return [pares[0], pares[0], pares[1], pares[1]]


def lectura(texto: str, key: str) -> None:
    """Muestra la lectura de una línea como texto simple con un borde fucsia a la izquierda (sin caja); vacía, no dibuja."""
    if not texto or not texto.strip():
        return
    with st.container(key=f"lectura_{key}"):
        st.markdown(texto)


def aviso(titulo: str, texto: str) -> None:
    """Muestra una advertencia con título."""
    st.warning(f"**{titulo}** — {texto}", icon="⚠️")


def ayuda(clave: str) -> str:
    """Devuelve el texto del glosario para usar como `help=`."""
    return GLOSARIO[clave]
