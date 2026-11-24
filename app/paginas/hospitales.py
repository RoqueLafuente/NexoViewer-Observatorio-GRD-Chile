"""Página Hospitales: se elige un hospital y se ve todo lo que sabemos de él, frente al país o a una región.

Nunca se pone un hospital junto a otro hospital ni se ordenan hospitales. Arriba, siempre visibles: selector,
ficha con «En cifras» y, al lado, el mapa. Debajo, una pestaña por tema (`PESTANAS`); cada una es una función `(sel, cod)` de
`SECCIONES` que dibuja su parte para el hospital `cod` con la selección global `sel` (años y tipo de atención), y solo se
llama la de la pestaña abierta.
"""
from collections.abc import Callable

import pandas as pd
import streamlit as st

import componentes as cp
import datos
import indicadores as ind
import textos as tx
from paginas import comun as cm
from paginas import hospital_actividad as ha
from paginas import hospital_camas as hc
from paginas import hospital_mapa as hm
from paginas import hospital_perfil as hp
from paginas import hospital_resumen as hr
from seleccion import PESTANAS_HOSPITALES, Seleccion, actual, etiqueta_hospital

# Valor del catálogo del DEIS → texto en tipo oración; lo que no esté aquí se muestra en tipo oración tal cual.
CERTIFICACION = {"Autogestionado en Red (EAR)": "Sí", "Invitados a ser EAR": "No (invitado a serlo)", "No Aplica": "No aplica"}
URGENCIA = {"Urgencia Hospitalaria (UEH)": "Sí", "Hospitalaria Especializada": "Sí, especializada"}
ANCHO_SELECTOR = 560  # px de los selectores de hospital y de referencia: cabe «114101 · Complejo Hospitalario Dr. Sótero…»
FUENTE_DEIS = "Fuente: catálogo de establecimientos de salud del DEIS-MINSAL (datos.gob.cl), versión del 18-11-2026."


def _oracion(texto) -> str:
    """«Alta Complejidad» → «Alta complejidad» (respeta siglas entre paréntesis)."""
    if texto is None or pd.isna(texto) or not str(texto).strip():
        return "Sin dato"
    t = str(texto).strip()
    return " ".join([t.split(" ")[0].capitalize()] + [p if p.isupper() or p.startswith("(") else p.lower()
                                                       for p in t.split(" ")[1:]])


@st.cache_data
def _mas_egresos() -> str:
    """Hospital con más egresos de hospitalización en el último año (valor inicial del selector)."""
    s = Seleccion(datos.anios_disponibles()[-1:], ha.HOSP, False)
    p = datos.filtrar(datos.cargar_para("perfil", ha.COLUMNAS["perfil"], s), s)
    return str(p.groupby("COD_HOSPITAL", observed=True)["episodios"].sum().idxmax())


def _sembrar_hospital(sel: Seleccion, codigos: list[str]) -> None:
    """Valor del selector antes de dibujarlo.

    Streamlit olvida el valor de un widget al cambiar de página, por eso la elección se guarda aparte (`hosp_elegido`) y
    se vuelve a sembrar. Un hospital aplicado como filtro global manda cuando cambia; si no, se respeta lo elegido aquí y,
    al abrir por primera vez, arranca el hospital con más egresos del último año.
    """
    ss = st.session_state
    filtro = str(sel.hospital) if sel.hospital is not None and str(sel.hospital) in codigos else None
    if filtro and filtro != ss.get("hosp_filtro_visto"):
        ss["hosp_sel"] = filtro
    elif ss.get("hosp_sel") not in codigos:
        ss["hosp_sel"] = ss["hosp_elegido"] if ss.get("hosp_elegido") in codigos else _mas_egresos()
    ss["hosp_filtro_visto"] = filtro


def _sembrar_referencia(opciones: dict[str, ha.Referencia]) -> None:
    """Igual que el hospital: la referencia se recuerda aparte; «su región» sigue al hospital y lo que ya no vale vuelve al país."""
    ss = st.session_state
    if ss.get("hosp_ref") in opciones:
        return
    previa = ss.get("hosp_ref_elegida")
    su_region = next(k for k, r in opciones.items() if r.tipo == "region")
    if previa is not None and previa.tipo == "region":
        ss["hosp_ref"] = su_region
    else:
        ss["hosp_ref"] = next((k for k, r in opciones.items() if r == previa), ha.PAIS)


def _selector(sel: Seleccion) -> str:
    """Selector del hospital (con buscador); devuelve el código elegido. La referencia se elige en la pestaña Actividad,
    que es donde se usa."""
    cat = cm.catalogo()
    nombres = {str(k): etiqueta_hospital(str(k), str(n)) for k, n in zip(cat["COD_HOSPITAL"], cat["HOSPITAL"])}
    _sembrar_hospital(sel, list(nombres))
    with st.container(key="hosp_selector"):
        st.selectbox("Hospital", list(nombres), key="hosp_sel", format_func=nombres.get, width=ANCHO_SELECTOR,
                     help="Escribe parte del nombre o el código para buscarlo.")
    cod = st.session_state["hosp_sel"]
    st.session_state["hosp_elegido"] = cod
    return cod


def selector_referencia(cod: str) -> ha.Referencia:
    """Selector «Comparar con» (país, su región u otra región con más de un hospital), arriba de la pestaña Actividad;
    devuelve la referencia elegida. Se recuerda aparte (`hosp_ref_elegida`): al volver a la pestaña sigue la misma."""
    cat = cm.catalogo()
    region = str(cat.loc[cat["COD_HOSPITAL"].astype(str) == cod, "REGION_HOSPITAL"].iloc[0])
    # Otra región solo si tiene más de un hospital: si no, la referencia sería otro hospital.
    n = cat.groupby("REGION_HOSPITAL", observed=True)["COD_HOSPITAL"].nunique()
    opciones = ha.opciones_referencia(region, [str(r) for r, k in n.items() if k > 1])
    _sembrar_referencia(opciones)
    with st.container(key="hosp_referencia"):
        st.selectbox("Comparar con", list(opciones), key="hosp_ref", help=cp.ayuda("referencia_hospital"),
                     width=ANCHO_SELECTOR)
    st.session_state["hosp_ref_elegida"] = opciones[st.session_state["hosp_ref"]]
    return st.session_state["hosp_ref_elegida"]


def ficha(sel: Seleccion, cod: str) -> None:
    """Ficha oficial del hospital (catálogo del DEIS) en una tarjeta con todos sus datos rotulados a la vista."""
    cat = cm.catalogo()
    c = cat[cat["COD_HOSPITAL"].astype(str) == cod].iloc[0]
    e = datos.cargar("establecimientos")
    e = e[e["COD_HOSPITAL"].astype(str) == cod]
    with st.container(border=True, key="hosp_ficha"):
        if e.empty:
            st.markdown(f"**{c['HOSPITAL']}**")
            st.info("Este hospital no está en el catálogo de establecimientos del DEIS.")
            return
        d = e.iloc[0]
        st.markdown(f"**{d['NOMBRE_DEIS']}**", help=cp.ayuda("ficha_hospital"))
        tiene = str(d["TIENE_URGENCIA"]).strip().upper() == "SI"
        datos_ficha = (("Comuna", str(d["COMUNA"])), ("Región", str(c["REGION_HOSPITAL"])),
                       ("Servicio de salud", str(c["SS_HOSPITAL"])),
                       ("Complejidad del establecimiento", _oracion(str(d["NIVEL_COMPLEJIDAD"]).replace(" Complejidad", ""))),
                       ("Nivel de atención", _oracion(d["NIVEL_ATENCION"])),
                       ("Tipo de establecimiento", _oracion(d["TIPO_ESTABLECIMIENTO"])),
                       ("Autogestionado en red", CERTIFICACION.get(d["CERTIFICACION"], _oracion(d["CERTIFICACION"]))),
                       ("Urgencia hospitalaria", URGENCIA.get(d["TIPO_URGENCIA"], "Sí") if tiene else "No"))
        with st.container(horizontal=True, key="fdato_hosp_ficha"):
            for etiqueta, valor in datos_ficha:
                with st.container(gap=None):
                    st.caption(etiqueta)
                    st.markdown(valor)
        st.caption(f"Código {cod} · {FUENTE_DEIS} Región y servicio de salud: base GRD.")


def cabecera(sel: Seleccion, cod: str) -> None:
    """Lo que se ve siempre, sobre las pestañas: la ficha completa y «En cifras» a la izquierda y el mapa (ubicación y
    origen) a la derecha. La columna de la ficha manda el alto: el mapa se estira o se encoge hasta medir lo mismo (CSS de
    `componentes.estilos`, «fcol_hosp»). «En cifras» va bajo la ficha y no a todo el ancho: así la columna izquierda es lo
    bastante alta para que el mapa se lea (con la ficha sola, el mapa quedaría de ~130 px)."""
    with cp.fila("fcol", "hosp"):
        with st.container(key="hosp_col_izq"):
            ficha(sel, cod)
            hr.resumen(sel, cod)
        hm.mapa(sel, cod)


def actividad(sel: Seleccion, cod: str) -> None:
    """Actividad del hospital frente a la referencia, que se elige aquí mismo (arriba de la pestaña)."""
    referencia = selector_referencia(cod)
    with st.container(key="hosp_actividad"):
        ha.dibujar(sel, cod, referencia)


def _sin_grd(sel: Seleccion, cod: str) -> str | None:
    """Aviso de una pestaña que sale de los egresos GRD cuando el hospital no los tiene en el año (None si los tiene): la
    pestaña no queda en blanco sin explicar por qué."""
    p = ind.periodo(sel.anios, datos.anios_disponibles())
    if hp._hay_egresos(sel, cod, p):
        return None
    anios = p.foco if p.modo == "un_anio" else tx.rotulo_periodo(sel.anios)
    return (f"Este hospital no tiene egresos GRD de {sel.tipo.lower()} en {anios}: esta pestaña sale de esos egresos. "
            "Elige otro año en la barra lateral.")


def _solo_con_grd(*secciones: Callable[[Seleccion, str], None]) -> Callable[[Seleccion, str], None]:
    def dibujar(sel: Seleccion, cod: str) -> None:
        aviso = _sin_grd(sel, cod)
        if aviso:
            st.info(aviso)
            return
        for s in secciones:
            s(sel, cod)
    return dibujar


def _actividad_y_serie(sel: Seleccion, cod: str) -> None:
    actividad(sel, cod)  # sin egresos ya avisa, y nombra lo que no se muestra
    hp.serie_mensual(sel, cod)


# Una función (sel, cod) por pestaña, en el orden de PESTANAS: solo se llama la de la pestaña abierta.
PESTANAS = PESTANAS_HOSPITALES
SECCIONES: dict[str, Callable[[Seleccion, str], None]] = {
    "Actividad": _actividad_y_serie,
    "Edad y origen": _solo_con_grd(hp.quienes),  # el mapa va arriba, junto a la ficha
    "Casos y estancia": _solo_con_grd(hp.casos, hp.estancia, hp.estancia_grupos),
    "Comorbilidad": _solo_con_grd(hp.comorbilidad),
    "Camas": hc.camas,  # REM20: no depende de los egresos GRD
}


def main() -> None:
    """Arma la página Hospitales: arriba, siempre visibles, el selector, la ficha con «En cifras» y el
    mapa; debajo, una pestaña por tema. Solo se calcula y dibuja la pestaña abierta, como en Análisis."""
    cm.encabezado("Hospitales")
    st.caption("Elige un hospital: arriba, su ficha, sus cifras y su mapa; abajo, una pestaña por tema.")
    sel = actual()
    cod = _selector(sel)  # cada título de gráfico dice su período: no hay una línea aparte con la regla de años
    cabecera(sel, cod)
    with st.container(key="pestanas_hospitales"):
        t = st.tabs(PESTANAS, key="h_pestana", on_change="rerun")  # la pestaña abierta se ve en el nombre de la vista
    for pestana, nombre in zip(t, PESTANAS):
        if pestana.open:
            with pestana, st.container(key="graficos_hospitales"):  # ancla del recorrido
                SECCIONES[nombre](sel, cod)


main()
