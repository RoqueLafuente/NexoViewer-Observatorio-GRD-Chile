"""Hospitales › actividad: KPIs, IER y severidad del hospital elegido frente a una referencia (el país o una región).

Un hospital nunca se pone junto a otro hospital: la referencia es el país, su región (todos sus hospitales, incluido el
propio) u otra región con más de un hospital. Los indicadores de una región salen de los egresos juntos de sus hospitales,
no de un promedio de promedios; sus egresos se muestran como promedio por hospital.
"""
from dataclasses import dataclass

import pandas as pd
import streamlit as st

import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import textos as tx
from paginas import comun as cm
from seleccion import Seleccion

HOSP, AMB = "HOSPITALIZACIÓN", "AMBULATORIO"
TIPOS_GRD = {HOSP: ["MH", "PH"], AMB: ["MA", "PA"]}
SEVERIDADES = {1: "1 menor", 2: "2 moderada", 3: "3 mayor"}
PAIS = "Promedio nacional"
UMBRAL_PESO_REGION = 50  # % de los egresos de su región: desde aquí se avisa que el hospital pesa mucho en «su región»
NOTA_MORTALIDAD_IER = ("Mortalidad bruta: sin ajuste por edad ni severidad. Ni la mortalidad ni el IER miden la calidad "
                       "de la atención.")
NOTA_MORTALIDAD = "Mortalidad bruta: sin ajuste por edad ni severidad; no mide la calidad de la atención."
NOTA_REFERENCIA = "En la referencia, cada cifra junta todos sus egresos; solo «Egresos» es un promedio por hospital."
SECCIONES_GRD = ("La evolución mensual, a quiénes atiende, qué casos atiende, la comorbilidad y la estancia salen de los "
                 "egresos GRD, así que no se muestran en ese año.")

# Columnas fijas por tabla (con hospital y región siempre): un solo juego en caché sirve al hospital, la región y el país,
# y la página no carga los agregados completos.
COLUMNAS = {
    "perfil": ("COD_HOSPITAL", "REGION_HOSPITAL", "episodios", "peso_total", "fallecidos"),
    "estancia": ("COD_HOSPITAL", "REGION_HOSPITAL", "DIAS", "episodios"),
    "grd": ("ANIO", "COD_HOSPITAL", "REGION_HOSPITAL", "SEVERIDAD", "COD_GRD", "TIPO_GRD", "episodios", "fallecidos",
            "dias_estada", "episodios_con_estancia"),
}


@dataclass(frozen=True)
class Referencia:
    tipo: str  # "pais" | "region" | "otra"
    region: str | None


def opciones_referencia(region_del_hospital: str, regiones: list[str]) -> dict[str, Referencia]:
    """Referencias que se ofrecen, con su nombre legible: el país, su región y cada otra región (nunca la propia)."""
    op = {PAIS: Referencia("pais", None), f"Su región ({region_del_hospital})": Referencia("region", region_del_hospital)}
    return op | {f"Otra región: {r}": Referencia("otra", r) for r in sorted(regiones) if r != region_del_hospital}


def _cargar(tabla: str, sel: Seleccion) -> pd.DataFrame:
    return datos.filtrar(datos.cargar_para(tabla, COLUMNAS[tabla], sel), sel)


@st.cache_data(max_entries=64)
def lado(anio: int, tipo: str, hospital: str | None, region: str | None) -> dict:
    """KPIs, estancia mediana, IER y severidad de un hospital (`hospital=cod`), una región (`region=nombre`) o el país."""
    sel = Seleccion([anio], tipo, False, region=region, hospital=hospital)
    perfil = _cargar("perfil", sel)
    k = ind.kpis(perfil)
    k["hospitales"] = int(perfil.loc[perfil["episodios"] > 0, "COD_HOSPITAL"].nunique())
    k["mediana"] = ind.percentil_estancia(_cargar("estancia", sel), 0.5)
    grd = _cargar("grd", sel)
    grd = grd[grd["TIPO_GRD"].isin(TIPOS_GRD[tipo])]
    k["severidad"] = ind.por_severidad(grd)
    k["ier"] = None
    if tipo == HOSP:
        nacional = _cargar("grd", Seleccion([anio], HOSP, False))
        por = "COD_HOSPITAL" if hospital else "REGION_HOSPITAL" if region else "ANIO"
        i = ind.ier(grd, nacional, [por])
        k["ier"] = float(i["ier"].iloc[0]) if len(i) and pd.notna(i["ier"].iloc[0]) else None
    return k


@st.cache_data
def anios_con_egresos(hospital: str, tipo: str) -> list[int]:
    """Años en que el hospital tiene egresos del tipo de atención (para decir desde cuándo informa)."""
    s = Seleccion(datos.anios_disponibles(), tipo, False, hospital=hospital)
    p = _cargar("perfil", s)
    return sorted(int(a) for a in p.loc[p["episodios"] > 0, "ANIO"].unique())


def _kpis(v: dict, nombre: str, referencia: bool) -> None:
    """Cuatro tarjetas de KPI; en una referencia, los egresos van como promedio por hospital (lo dice su «?»)."""
    sin = ind.variacion(0, None, "conteo", "neutro", 0)
    c = cp.fila_kpi(nombre)
    with c[0]:
        if referencia and v["hospitales"] > 0:
            cp.tarjeta_kpi("Egresos", tx.numero(v["egresos"] / v["hospitales"]), sin, cp.ayuda("promedio_por_hospital"),
                           ":material/bed:", (("Promedio por hospital", f"{tx.numero(v['egresos'])} en total entre "
                                                                         f"{tx.numero(v['hospitales'])} hospitales"),))
        else:
            cp.tarjeta_kpi("Egresos", tx.numero(v["egresos"]), sin, cp.ayuda("egreso"), ":material/bed:")
    with c[1]:
        cp.tarjeta_kpi("Estancia mediana", tx.estancia(v["mediana"]), sin, cp.ayuda("mediana"), ":material/schedule:")
    with c[2]:
        cp.tarjeta_kpi("Índice casemix", tx.numero(v["casemix"], 2), sin, cp.ayuda("casemix"), ":material/bar_chart:")
    with c[3]:
        cp.tarjeta_kpi("Mortalidad", tx.numero(v["mortalidad"], 2) + " %", sin, cp.ayuda("mortalidad"), ":material/favorite:")


def _severidad(s: pd.DataFrame, titulo: str = "**Por severidad**") -> None:
    if s.empty:
        st.caption("Sin episodios con severidad para esta selección.")
        return
    st.markdown(titulo, help=cp.ayuda("severidad"))
    st.dataframe(pd.DataFrame({"Severidad": s["SEVERIDAD"].map(SEVERIDADES), "Egresos": s["episodios"].map(tx.numero),
                               "Mortalidad (%)": s["mortalidad"].map(lambda x: tx.numero(x, 2)),
                               "Estancia media (días; sensible a extremos)": s["estancia_media"].map(lambda x: tx.numero(x, 1))}),
                 hide_index=True,
                 column_config={"Mortalidad (%)": st.column_config.Column("Mortalidad (%)", help=cp.ayuda("mortalidad"))})


def _ier(v: dict, tipo: str) -> None:
    if tipo == AMB:
        st.markdown("**IER:** No aplica en ambulatorio.", help=cp.ayuda("ier"))
    else:
        st.markdown(f"**IER:** {tx.numero(v['ier'], 2)}", help=cp.ayuda("ier"))


def _nombre_referencia(referencia: Referencia) -> str:
    return {"pais": PAIS, "region": f"Su región: {referencia.region}", "otra": f"Otra región: {referencia.region}"}[referencia.tipo]


def _sin_egresos(nombre: str, cod: str, sel: Seleccion, anio: int | str) -> str:
    """Mensaje neutro para un hospital sin egresos en el año (o los años) y tipo elegidos, con los años en que sí informa."""
    tipo = sel.tipo.lower()
    anios = anios_con_egresos(cod, sel.tipo)
    if not anios:
        return f"{nombre} no tiene egresos de {tipo} en ningún año de la base. Prueba con el otro tipo de atención."
    desde = (f" Tiene egresos de {tipo} desde {anios[0]}." if anios == list(range(anios[0], anios[-1] + 1))
             else f" Tiene egresos de {tipo} en {', '.join(str(a) for a in anios)}.")
    return f"{nombre} no tiene egresos de {tipo} en {anio}.{desde} {SECCIONES_GRD} Elige otro año en la barra lateral."


# Indicadores de los paneles año a año: (nombre del panel, clave en `lado`, decimales, sufijo del hover)
INDICADORES_ANIOS = (("Egresos", "egresos", 0, ""), ("Estancia mediana (días)", "mediana", 0, " días"),
                     ("Índice casemix", "casemix", 2, ""), ("Mortalidad bruta (%)", "mortalidad", 2, " %"),
                     ("IER", "ier", 2, ""))


def _sin_referencia(referencia: Referencia, r: dict) -> bool:
    """La referencia no se muestra si es otra región con un solo hospital ese año (sería otro hospital) o no tiene egresos."""
    return r["egresos"] == 0 or (referencia.tipo == "otra" and r["hospitales"] <= 1)


def actividad_por_anio(cod: str, referencia: Referencia, tipo: str, anios: tuple) -> pd.DataFrame:
    """Indicadores del hospital y de la referencia en cada año (`ANIO`, `indicador`, `lado`, `valor`, `texto`), con
    exactamente las cifras de las tarjetas de un año (`lado`, en caché por año). Un año sin egresos del hospital, o sin
    referencia que mostrar, queda en NaN: hueco, nunca 0. En la referencia, los egresos son el promedio por hospital."""
    filas = []
    for a in sorted(anios):
        h, r = lado(a, tipo, cod, None), lado(a, tipo, None, referencia.region)
        for nombre_lado, v, vacio in (("hospital", h, h["egresos"] == 0), ("referencia", r, _sin_referencia(referencia, r))):
            for nombre, clave, dec, sufijo in INDICADORES_ANIOS:
                if clave == "ier" and tipo == AMB:
                    continue
                x = v[clave]
                if clave == "egresos" and nombre_lado == "referencia" and v["hospitales"]:
                    x = v["egresos"] / v["hospitales"]
                x = None if vacio or x is None else float(x)
                filas.append({"ANIO": a, "indicador": nombre, "lado": nombre_lado, "valor": x,
                              "texto": tx.SIN_DATO if x is None else tx.numero(x, dec) + sufijo})
    return pd.DataFrame(filas)


def _lectura_anios(d: pd.DataFrame) -> str:
    """Neutra: cómo pasaron los egresos del hospital del primer al último año con datos."""
    e = d[(d["indicador"] == "Egresos") & (d["lado"] == "hospital")].dropna(subset=["valor"])
    if len(e) < 2:
        return "Con un solo año con egresos en el período, cada panel muestra un punto."
    a, b = e.iloc[0], e.iloc[-1]
    cambio = (b["valor"] - a["valor"]) / a["valor"] * 100 if a["valor"] >= ind.MIN_CASOS else None
    frase = f"Los egresos del hospital pasan de {tx.numero(a['valor'])} en {a['ANIO']} a {tx.numero(b['valor'])} en {b['ANIO']}"
    if cambio is not None:
        frase += f" ({'+' if cambio > 0 else ''}{tx.numero(cambio, 1)} %)"
    return frase + "; cada panel tiene su propia escala."


def _dibujar_anios(sel: Seleccion, cod: str, referencia: Referencia, nombre: str, p: ind.Periodo) -> None:
    """Varios años elegidos: un panel pequeño por indicador con la línea del hospital y la de la referencia, año a año."""
    anios = sorted(sel.anios)
    periodo = tx.rotulo_periodo(anios)
    st.subheader("Actividad frente a una referencia")
    st.caption(f"Años {periodo} · {sel.tipo.capitalize()}")
    d = actividad_por_anio(cod, referencia, sel.tipo, tuple(anios))
    h = d[d["lado"] == "hospital"]
    con = sorted({int(a) for a in h.dropna(subset=["valor"])["ANIO"]})
    if not con:
        st.info(_sin_egresos(nombre, cod, sel, periodo))
        return
    faltan = [a for a in anios if a not in con]
    if faltan:
        st.info(f"{nombre} no tiene egresos de {sel.tipo.lower()} en {tx.rotulo_periodo(faltan)}: esos años quedan en "
                "blanco en los paneles, no en cero.")
    r = d[d["lado"] == "referencia"]
    sin_r = sorted({int(a) for a in r[r["valor"].isna()]["ANIO"]})
    if sin_r and referencia.region:
        st.info(f"En {tx.rotulo_periodo(sin_r)}, {referencia.region} tiene un hospital o ninguno con egresos de "
                f"{sel.tipo.lower()}: la referencia queda en blanco esos años.")
    if referencia.tipo == "region":
        pesos = [lado(a, sel.tipo, cod, None)["egresos"] / lado(a, sel.tipo, None, referencia.region)["egresos"] * 100
                 for a in con if lado(a, sel.tipo, None, referencia.region)["egresos"]]
        if pesos and max(pesos) >= UMBRAL_PESO_REGION:
            st.info(f"Este hospital reúne hasta el {tx.numero(max(pesos), 0)} % de los egresos de {sel.tipo.lower()} de "
                    f"{referencia.region} en {periodo}: pesa mucho en esta referencia.")
    indicadores = list(dict.fromkeys(d["indicador"]))
    nombre_ref = _nombre_referencia(referencia)
    fig = gr.paneles_anios(d, indicadores, anios, "Este hospital", nombre_ref)
    tabla = d.pivot_table(index=["ANIO", "indicador"], columns="lado", values="valor", aggfunc="first", dropna=False,
                          sort=False).reset_index().rename(columns={"indicador": "Indicador", "hospital": "Este hospital",
                                                                    "referencia": nombre_ref})
    notas = ()
    if anios != list(range(anios[0], anios[-1] + 1)):
        notas += ("Solo se dibujan los años elegidos: la línea une años que no son seguidos.",)
    cm.grafico(tx.con_periodo("Actividad año a año", anios), fig, _lectura_anios(d), "g_hosp_actividad_anios",
               cp.ayuda("paneles_anios"), notas, tabla=cm.tabla_humana(tabla))
    if p.foco in con:
        _severidad(lado(p.foco, sel.tipo, cod, None)["severidad"], f"**{nombre}: por severidad · {p.foco}**")
    st.caption((NOTA_MORTALIDAD if sel.tipo == AMB else NOTA_MORTALIDAD_IER) + " " + NOTA_REFERENCIA)


def dibujar(sel: Seleccion, cod: str, referencia: Referencia) -> None:
    """KPIs del hospital y de la referencia lado a lado, IER, tabla por severidad del hospital y una nota sobre la
    mortalidad bruta y el IER (la tabla por severidad de la referencia no va: ponía dos mortalidades lado a lado). Con
    varios años elegidos, los mismos indicadores año a año en paneles pequeños."""
    p = ind.periodo(sel.anios, datos.anios_disponibles())
    anio = p.foco
    cat = cm.catalogo()
    nombre = str(cat.loc[cat["COD_HOSPITAL"].astype(str) == cod, "HOSPITAL"].iloc[0])
    if p.modo == "comparar":
        _dibujar_anios(sel, cod, referencia, nombre, p)
        return
    st.subheader("Actividad frente a una referencia")
    st.caption(f"Año {anio} · {sel.tipo.capitalize()}")
    h = lado(anio, sel.tipo, cod, None)
    if h["egresos"] == 0:
        st.info(_sin_egresos(nombre, cod, sel, anio))
        return
    r = lado(anio, sel.tipo, None, referencia.region)
    # dos mitades que pasan una bajo la otra cuando no caben con su tabla por severidad entera (1024 px con barra lateral)
    with cp.fila("fmitad", "hosp_actividad_lados"):
        ca, cb = st.container(), st.container()
    with ca:
        st.markdown(f"**{nombre}**")
        _kpis(h, "hosp_kpi_hospital", referencia=False)
        _ier(h, sel.tipo)
        _severidad(h["severidad"])
    with cb:
        st.markdown(f"**{_nombre_referencia(referencia)}**")
        sin_referencia = referencia.tipo == "otra" and r["hospitales"] <= 1  # sería otro hospital: no se muestra
        if sin_referencia:
            st.info(f"En {anio}, {referencia.region} tiene {r['hospitales'] or 'ningún'} hospital con egresos de "
                    f"{sel.tipo.lower()}: elige otra referencia.")
        elif referencia.tipo == "region" and r["hospitales"] == 1:
            st.info(f"La referencia es solo este hospital: es el único de {referencia.region} con egresos de "
                    f"{sel.tipo.lower()} en {anio}.")
        elif referencia.tipo == "region" and r["egresos"] and h["egresos"] / r["egresos"] * 100 >= UMBRAL_PESO_REGION:
            st.info(f"Este hospital reúne el {tx.numero(h['egresos'] / r['egresos'] * 100, 0)} % de los egresos de "
                    f"{sel.tipo.lower()} de {referencia.region} en {anio}: pesa mucho en esta referencia.")
        if not sin_referencia:
            _kpis(r, "hosp_kpi_referencia", referencia=True)
            _ier(r, sel.tipo)
    st.caption((NOTA_MORTALIDAD if sel.tipo == AMB else NOTA_MORTALIDAD_IER)
               + ("" if sin_referencia else " " + NOTA_REFERENCIA))
