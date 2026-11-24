"""NexoViewer: Observatorio GRD Chile: punto de entrada de la app Streamlit."""
from pathlib import Path

import streamlit as st

import componentes
import datos
import recorrido
import seleccion
from seleccion import leer_globales

st.set_page_config(page_title="NexoViewer: Observatorio GRD Chile", page_icon=":material/monitor_heart:", layout="wide")
st.logo(Path(__file__).parent / "recursos" / "logo.svg", size="large")
st.html(componentes.estilos())  # anchos mínimos de las filas que se reparten (Streamlit está fijado en requirements.txt)

problemas = datos.problemas()
if problemas:
    st.error("Los agregados no sirven para la app:" + "".join(f"\n- {p}" for p in problemas))
    st.stop()

datos.precalentar()  # lee los agregados una vez; las páginas ya los encuentran en caché

pagina = st.navigation([
    st.Page("paginas/inicio.py", title="Inicio", icon=":material/home:", default=True),
    st.Page("paginas/analisis.py", title="Análisis", icon=":material/analytics:"),
    st.Page("paginas/hospitales.py", title="Hospitales", icon=":material/local_hospital:"),
    st.Page("paginas/descargas.py", title="Descargas", icon=":material/download:"),
    st.Page("paginas/metodologia.py", title="Metodología", icon=":material/menu_book:"),
], position="top")
leer_globales(pagina.title)
_usa = seleccion.USO.get(seleccion.vista(pagina.title), (set(seleccion.FILTROS), None))[0]
_chips = seleccion.chips(seleccion.actual(), _usa)
if _chips or recorrido.RECORRIDOS.get(pagina.title):  # sin franja ni recorrido (Metodología) no se deja un hueco
    _izq, _der = st.columns([5, 1], vertical_alignment="center")
    with _izq:
        if _chips:  # lo aplicado, nunca el borrador
            with st.container(key="franja"):
                st.markdown(" ".join(f":blue-badge[{c.replace(']', ')')}]" for c in _chips))
    with _der:
        with st.container(horizontal=True, horizontal_alignment="right"):
            recorrido.boton_ver_recorrido(pagina.title)
pagina.run()

with st.container(border=True):
    st.caption("**NexoViewer: Observatorio GRD Chile** · Explorador de datos abiertos de egresos GRD. Fuente: FONASA, Datos Abiertos "
               "(https://datosabiertos.fonasa.cl), egresos GRD 2019–2025. Elaboración propia; cifras sujetas a validación.")
recorrido.montar(pagina.title)  # al final: sus anclas ya están dibujadas cuando corre el script
