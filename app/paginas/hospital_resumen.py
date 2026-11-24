"""Hospitales › «En cifras»: seis cifras del hospital en el año foco, bajo su ficha.

Solo el hospital, sin referencia ni comparación. Cada cifra sale del mismo cálculo (y la misma caché) que su sección:
egresos, estancia mediana y casemix de la actividad (`hospital_actividad.lado`), camas y ocupación del REM20
(`hospital_camas`) y severidad mayor de la complejidad (`hospital_perfil.complejidad_hospital`); no se lee ninguna tabla más.
Sin egresos GRD en el año quedan solo las cifras de camas; sin eso tampoco, no se dibuja.
"""
import streamlit as st

import componentes as cp
import indicadores as ind
import textos as tx
from paginas import hospital_actividad as ha
from paginas import hospital_camas as hc
from paginas import hospital_perfil as hp
from seleccion import Seleccion

SIN_VARIACION = ind.Variacion("", "neutro", False)


def cifras(sel: Seleccion, cod: str) -> list[tuple[str, str, str]]:
    """(título, valor, clave del glosario) de cada cifra del hospital en el año foco; vacía si no hay nada que mostrar."""
    p = hp._periodo(sel)
    salida = []
    h = ha.lado(p.foco, sel.tipo, cod, None)
    if h["egresos"] > 0:
        salida += [("Egresos", tx.numero(h["egresos"]), "egreso"),
                   ("Estancia mediana", tx.estancia(h["mediana"]), "mediana"),
                   ("Índice casemix", tx.numero(h["casemix"], 2), "casemix")]
    c = hc.camas_hospital(cod)
    foco = c[c["ANIO"] == p.foco]
    if not foco.empty:
        f = hc._valores(foco)
        salida += [("Camas disponibles (promedio)", tx.numero(f["camas"], 0), "camas_promedio"),
                   ("Índice ocupacional", hc._porcentaje(f["ocupacion"]), "indice_ocupacional")]
    if h["egresos"] > 0:
        if sel.tipo == ha.AMB:  # la severidad solo se registra en hospitalización
            valor = "No aplica"
        else:
            f = hp.complejidad_hospital(cod, sel.tipo, hp.anios_complejidad(sel, p))["complejidad"].get(p.foco)
            valor = hc.SIN_VALOR if f is None else f"{tx.numero(f['severidad_mayor'], 1)} %"
        salida.append(("Severidad mayor", valor, "severidad"))
    return salida


def resumen(sel: Seleccion, cod: str) -> None:
    """Tarjeta «En cifras · <año>» con las cifras del hospital en tarjetas compactas (3 por línea, 2 en pantallas angostas)."""
    lista = cifras(sel, cod)
    if not lista:
        return
    with st.container(border=True, key="hosp_resumen"):
        st.markdown(f"**{tx.con_periodo('En cifras', [hp._periodo(sel).foco])}**", help=cp.ayuda("en_cifras"))
        with cp.fila("fpar", "hosp_resumen"):  # las tarjetas de una línea miden lo mismo aunque un rótulo ocupe dos líneas
            for titulo, valor, clave in lista:
                cp.tarjeta_kpi(titulo, valor, SIN_VARIACION, cp.ayuda(clave))
