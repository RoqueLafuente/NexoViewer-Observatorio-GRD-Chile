"""Hospitales › mapa (cabecera, al lado de la ficha y con su mismo alto): dónde está el hospital y de qué regiones vienen sus egresos.

Un solo mapa: las regiones se pintan por el % de los egresos del hospital que viene de cada región del paciente, el hospital
lleva una estrella y los otros hospitales de su región son puntos grises iguales, con solo su nombre, sin cifras ni tamaños (nunca una comparación).
Como en el mapa de Inicio, «Sin región» no se pinta, pero cuenta en el 100 %.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import textos as tx
from paginas import comun as cm
from seleccion import Seleccion

SIN_REGION, SIN_PROVINCIA = "Sin región", "Sin provincia"
UMBRAL_DOMINANTE: float = 80.0  # % desde el cual un origen es «el dominante»: se dice con una cifra y el gráfico muestra el resto
NOTA_PUNTOS = "Los puntos grises son los otros hospitales de la región."
ALTURA_MAPA_GRANDE = gr.ALTURA_MAPA_GRANDE
ANCHO_COLUMNA_MAPA = 300  # px: ancho de la columna del mapa en una pantalla de escritorio
# Mapa pequeño: sin rueda (no recorta ni se lleva el desplazamiento de la página) y sin barra de herramientas.
CONFIG_MAPA_PEQUENO = {"scrollZoom": False, "displayModeBar": False}
CONFIG_MAPA_GRANDE = {"scrollZoom": True, "displaylogo": False, "modeBarButtonsToRemove": ["select2d", "lasso2d"]}


def partir_origen(origen: pd.DataFrame, umbral: float = UMBRAL_DOMINANTE) -> tuple[pd.Series | None, pd.DataFrame]:
    """Separa el origen dominante del resto: la fila con más egresos si pesa `umbral` % o más (si no, `None`) y las demás.

    `origen` trae la categoría (región o provincia), `episodios` y `pct` (del total del hospital: «Sin región» y «Sin
    provincia» cuentan en el 100 %, pero no son origen ni barra). El resto sale ordenado de mayor a menor; sin dominante,
    es todo el origen conocido.
    """
    columna = "PROVINCIA_PACIENTE" if "PROVINCIA_PACIENTE" in origen.columns else "REGION_PACIENTE"
    if origen.empty:
        return None, origen
    conocido = origen[~origen[columna].isin([SIN_REGION, SIN_PROVINCIA]) & (origen["episodios"] > 0)]
    conocido = conocido.sort_values("episodios", ascending=False)
    if conocido.empty or float(conocido["pct"].iloc[0]) < umbral:
        return None, conocido.reset_index(drop=True)
    return conocido.iloc[0], conocido.iloc[1:].reset_index(drop=True)


@st.cache_data
def origen(cod: str, anio: int, tipo: str) -> pd.DataFrame:
    """Egresos y % del hospital en el año y tipo de atención por región del paciente (vacío si no informa egresos)."""
    p = datos.cargar("perfil", ("ANIO", "COD_HOSPITAL", "REGION_PACIENTE", "TIPO_EPISODIO", "episodios"))
    p = p[(p["COD_HOSPITAL"].astype(str) == cod) & (p["ANIO"] == anio) & (p["TIPO_EPISODIO"] == tipo)]
    p = p.assign(REGION_PACIENTE=p["REGION_PACIENTE"].astype(object).where(p["REGION_PACIENTE"].notna(), SIN_REGION))
    r = p.groupby("REGION_PACIENTE", observed=True)["episodios"].sum().reset_index()
    total = r["episodios"].sum()
    if total <= 0:
        return pd.DataFrame({"REGION_PACIENTE": [], "episodios": [], "pct": []})
    return r.assign(pct=r["episodios"] / total * 100).sort_values("episodios", ascending=False).reset_index(drop=True)


@st.cache_data
def _ubicacion(cod: str) -> tuple[dict | None, str, pd.DataFrame]:
    """Datos del hospital en `establecimientos` (nombre y coordenadas), su región y los demás hospitales de esa región."""
    cat = cm.catalogo()
    region = str(cat.loc[cat["COD_HOSPITAL"].astype(str) == cod, "REGION_HOSPITAL"].iloc[0])
    de_la_region = set(cat.loc[cat["REGION_HOSPITAL"].astype(str) == region, "COD_HOSPITAL"].astype(str)) - {cod}
    e = datos.cargar("establecimientos", ("COD_HOSPITAL", "NOMBRE_DEIS", "LATITUD", "LONGITUD"))
    cods = e["COD_HOSPITAL"].astype(str)
    propio = e[cods == cod]
    return (propio.iloc[0].to_dict() if len(propio) else None), region, e[cods.isin(de_la_region)][["LATITUD", "LONGITUD", "NOMBRE_DEIS"]]


def figura(cod: str, anio: int, tipo: str, zoom: bool):
    """Figura del mapa, tabla de origen, región del hospital y sus otros hospitales; sin coordenadas, la figura es `None`."""
    o = origen(cod, anio, tipo)
    propio, region, otros = _ubicacion(cod)
    if propio is None:
        return None, o, region, otros
    fig = gr.mapa_hospital(o, (float(propio["LATITUD"]), float(propio["LONGITUD"]), str(propio["NOMBRE_DEIS"])), otros,
                           gr.encuadre_region(region) if zoom else None)
    return fig, o, region, otros


MARGEN_SUPERIOR_GRANDE = 30  # px sobre el mapa del diálogo: deja la barra de herramientas de Plotly sin tapar nada


def ampliada(fig):
    """Copia de la figura para el diálogo: las mismas capas y el mismo encuadre, a 700 px de alto, con arrastre y con la
    escala de colores del origen (el mapa pequeño la oculta: solo muestra la ubicación)."""
    grande = go.Figure(fig)
    grande.layout.title = None
    grande.update_traces(showscale=True, selector=dict(name="origen"))
    grande.update_layout(height=ALTURA_MAPA_GRANDE, autosize=True, dragmode="pan", margin=dict(t=MARGEN_SUPERIOR_GRANDE))
    return grande


def pequena(fig):
    """Copia para la tarjeta de la cabecera: sin título (va fuera, como etiqueta) ni escala de colores; solo la ubicación
    con las regiones pintadas por el origen."""
    chica = go.Figure(fig)
    chica.layout.title = None
    chica.update_traces(showscale=False, selector=dict(name="origen"))
    chica.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    return chica


def _cambiar_zoom() -> None:
    st.session_state["hosp_mapa_zoom"] = st.session_state["hosp_mapa_zoom_dialogo"]


def _dialogo_mapa(cod: str, anio: int, tipo: str, nombre: str) -> None:
    """Abre el mapa grande con su propio título, la lectura del origen, sus notas, la escala y la tabla. Es un fragmento:
    mover o acercar el mapa, o cambiar el zoom, no recarga la página."""
    @st.dialog(f"Mapa de {nombre}", width="large")
    def _abrir():
        zoom = bool(st.session_state.get("hosp_mapa_zoom", True))
        fig, o, region, otros = figura(cod, anio, tipo, zoom)
        texto, notas = lectura_origen(o, region, otros, anio, tipo)
        st.markdown(f"**{tx.con_periodo('Origen de los egresos', [anio])}**", help=cp.ayuda("mapa_hospital"))
        st.toggle("Acercar a su región", value=zoom, key="hosp_mapa_zoom_dialogo", on_change=_cambiar_zoom)
        st.plotly_chart(ampliada(fig), key="g_hosp_mapa_grande", config=CONFIG_MAPA_GRANDE)
        cp.lectura(texto, "hosp_mapa_grande")
        for nota in notas + ["Rueda del mouse para acercar y arrastre para mover el mapa."]:
            st.caption(nota)
        if not o.empty:
            with st.expander("Ver en tabla"):
                t = cm.tabla_humana(o.assign(ANIO=anio)[["ANIO", "REGION_PACIENTE", "episodios", "pct"]])
                st.dataframe(t, hide_index=True, column_config=cm.config_columnas(t))
    _abrir()


def lectura_origen(o: pd.DataFrame, region: str, otros: pd.DataFrame, anio: int, tipo: str) -> tuple[str, list[str]]:
    """Lectura de una línea y notas del mapa (van en el diálogo ampliado, no en la tarjeta pequeña)."""
    notas = [NOTA_PUNTOS] if len(otros) else []
    if o.empty:
        notas.insert(0, f"El hospital no informa egresos de {tipo.lower()} en {anio}: se muestra solo su ubicación.")
        return "", notas
    propia = float(o.loc[o["REGION_PACIENTE"] == region, "pct"].sum())
    sin = int(o.loc[o["REGION_PACIENTE"] == SIN_REGION, "episodios"].sum())
    if sin:
        notas.insert(0, f"{tx.numero(sin)} egresos sin región conocida no se pintan, pero cuentan en el 100 %.")
    return f"El {pct_cifra(propia)} % de los egresos de {anio} viene de la propia región.", notas


def pct_texto(v: float) -> str:
    """Porcentaje para la lectura: entero, salvo que redondear lo deje en 100 sin llegar a 100 (99,6 no es «100»)."""
    if v < 100 and round(v) >= 100:
        return tx.numero(int(v * 10) / 10, 1)
    return tx.numero(v, 0)


def pct_cifra(v: float) -> str:
    """Porcentaje con un decimal; 99,97 no se redondea a «100» y 100 va sin decimales."""
    if v >= 100:
        return "100"
    return tx.numero(int(v * 10) / 10 if round(v, 1) >= 100 else v, 1)


def mapa(sel: Seleccion, cod: str) -> None:
    """Tarjeta pequeña de la cabecera: una etiqueta corta («Ubicación y origen · 2025») con el botón de ampliar en la
    esquina y, debajo, solo el mapa (acercado a su región por omisión, con el hospital marcado). La lectura, las notas, la
    escala y la tabla van en el diálogo ampliado."""
    anio = ind.periodo(sel.anios, datos.anios_disponibles()).foco
    with st.container(key="hosp_mapa"):
        zoom = bool(st.session_state.setdefault("hosp_mapa_zoom", True))  # no es un widget: sobrevive al cerrar el diálogo
        fig, o, region, otros = figura(cod, anio, sel.tipo, zoom)
        if fig is None:
            st.info("Este hospital no tiene coordenadas en el catálogo del DEIS: no se puede ubicar en el mapa.")
            return
        if zoom:  # bajo la ficha (ventana angosta) el recuadro sigue la forma de la región; al lado, manda el alto de la ficha
            alto = gr.altura_mapa_region(region, ANCHO_COLUMNA_MAPA)
            st.markdown(f"<style>.st-key-figura_g_hosp_mapa {{ --alto-mapa: {alto}px; }}</style>", unsafe_allow_html=True)
        with st.container(border=True, key="hosp_mapa_tarjeta"):
            with st.container(horizontal=True, vertical_alignment="center", key="hosp_mapa_cabeza"):
                st.caption(tx.con_periodo("Ubicación y origen", [anio]), help=cp.ayuda("mapa_hospital"))
                if st.button("", key="hosp_mapa_ampliar", icon=":material/open_in_full:", type="tertiary",
                             help="Ampliar mapa: con la escala de colores, la lectura del origen y la tabla"):
                    _dialogo_mapa(cod, anio, sel.tipo, str(_ubicacion(cod)[0]["NOMBRE_DEIS"]))
            with st.container(key="figura_g_hosp_mapa"):
                st.plotly_chart(pequena(fig), key="g_hosp_mapa", config=CONFIG_MAPA_PEQUENO)
