"""Página Inicio: ficha de la base, KPIs y seis gráficos cuya forma depende del modo del período."""
from dataclasses import replace

import pandas as pd
import streamlit as st

import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import textos as tx
from paginas import comun as cm
from seleccion import Seleccion, actual

TIPOS_AGRUPABLES = ("MH", "PH", "MA", "PA")  # sin inagrupables ni GRD sin tipo
SEXOS = {"HOMBRE": "Hombre", "MUJER": "Mujer"}


@st.cache_data
def _ficha() -> str:
    """Ficha de la base: episodios, años, hospitales, regiones, GRD y variables."""
    p, g = datos.cargar("perfil", ("episodios", "COD_HOSPITAL", "REGION_HOSPITAL")), datos.cargar("grd")
    agrupables = g.loc[g["TIPO_GRD"].isin(TIPOS_AGRUPABLES), "COD_GRD"].nunique()
    anios, variables = datos.anios_disponibles(), datos.variables_base()
    ficha = (f"**Ficha de la base** · {tx.numero(p['episodios'].sum())} episodios · {anios[0]}–{anios[-1]} · "
             f"{p['COD_HOSPITAL'].nunique()} hospitales · {p['REGION_HOSPITAL'].nunique()} regiones · "
             f"{tx.numero(agrupables)} GRD" + (f" · {tx.numero(variables)} variables armonizadas" if variables else ""))
    return ficha


@st.cache_data(max_entries=64)
def _valores(clave: tuple, anio: int) -> dict:
    """KPIs de un año: egresos, casemix, mortalidad y mediana/p90 de estancia."""
    sel = cm.desde_clave(clave)
    k = ind.kpis(datos.filtrar(datos.cargar_para("perfil", datos.COLUMNAS_KPI["perfil"], sel), sel, [anio]))
    e = datos.filtrar(datos.cargar_para("estancia", datos.COLUMNAS_KPI["estancia"], sel), sel, [anio])
    return k | {"mediana": ind.percentil_estancia(e, 0.5), "p90": ind.percentil_estancia(e, 0.9)}


def _tabla_hospitales(sel: Seleccion, perf: pd.DataFrame, anios: list[int]) -> pd.DataFrame:
    """Egresos, casemix e IER por hospital y año (IER contra el promedio nacional del año)."""
    h = perf.groupby(["ANIO", "COD_HOSPITAL", "HOSPITAL"])[["episodios", "peso_total"]].sum().reset_index()
    if sel.tipo == "AMBULATORIO":
        return h
    h["casemix"] = h["peso_total"] / h["episodios"]
    grd = datos.cargar("grd")
    nacional = datos.filtrar(grd, Seleccion(anios=anios, tipo="HOSPITALIZACIÓN", panel=False))
    i = ind.ier(datos.filtrar(grd, sel, anios), nacional, ["ANIO", "COD_HOSPITAL"])[["ANIO", "COD_HOSPITAL", "ier"]]
    return h.merge(i, on=["ANIO", "COD_HOSPITAL"], how="left")


@st.cache_data(max_entries=32)
def _agregados(clave: tuple, anios: tuple) -> dict[str, pd.DataFrame]:
    """Tablas pequeñas que usan los gráficos: capítulos, regiones, sexo, edad y hospitales."""
    sel = cm.desde_clave(clave)
    perf = datos.filtrar(datos.cargar("perfil"), sel, list(anios))
    sexo, sin_sexo = [], 0
    for a in anios:
        d, excluidos = ind.distribucion_sexo(perf[perf["ANIO"] == a])
        sexo.append(d.assign(ANIO=a, SEXO=d["SEXO"].map(SEXOS)))
        sin_sexo += excluidos
    t = perf.groupby(["ANIO", "TRAMO_EDAD"])["episodios"].sum().reset_index()
    t["GRUPO_EDAD"] = t["TRAMO_EDAD"].astype(str).map(ind.grupo_edad)
    edad = cm.pct_por(t.dropna(subset=["GRUPO_EDAD"]), "GRUPO_EDAD")
    edad = edad.assign(_o=edad["GRUPO_EDAD"].map(datos.GRUPOS_EDAD.index)).sort_values(["ANIO", "_o"])
    regiones = perf.assign(REGION_PACIENTE=perf["REGION_PACIENTE"].astype(str).fillna("Sin región"))
    return {
        "capitulos": cm.pct_por(perf.assign(capitulo=perf["CAPITULO_CIE10"].astype(str).map(tx.etiqueta_capitulo)), "capitulo"),
        "territorio": regiones.groupby(["ANIO", "REGION_PACIENTE"])["episodios"].sum().reset_index(),
        "sexo": pd.concat(sexo, ignore_index=True), "sin_sexo": sin_sexo, "edad": edad,
        "hospitales": _tabla_hospitales(sel, perf, list(anios)),
    }


@st.cache_data(max_entries=32)
def _serie_df(clave: tuple) -> pd.DataFrame:
    """Egresos por mes de todos los hospitales y del panel, para todos los años."""
    sel = cm.desde_clave(clave)
    m = datos.filtrar(datos.cargar("mensual"), replace(sel, panel=False, anios=datos.anios_disponibles()))
    if sel.servicio:
        cat = cm.catalogo()
        m = m[m["COD_HOSPITAL"].isin(cat.loc[cat["SS_HOSPITAL"] == sel.servicio, "COD_HOSPITAL"])]
    m = m.assign(panel=m["episodios"].where(m["EN_PANEL_7_ANIOS"], 0))
    return m.groupby("mes")[["episodios", "panel"]].sum().rename(columns={"episodios": "todos"}).reset_index()


def _var(f: dict, b: dict | None, clave: str, tipo: str, favorable: str) -> ind.Variacion:
    """Variación de un KPI; sin variación si falta el valor de algún año."""
    if b is None or f[clave] is None or b[clave] is None:
        return ind.variacion(0, None, tipo, favorable, 0)
    return ind.variacion(f[clave], b[clave], tipo, favorable, b["n"])


POR_QUE = {
    "egresos": "Cuenta cuánta actividad tuvieron los hospitales.",
    "mediana": "Más días por egreso significa más días-cama ocupados.",
    "casemix": "Dice qué tan complejos son, en promedio, los casos atendidos.",
    "mortalidad": "Depende mucho de la gravedad de los egresos. Para comparar hospitales, mírala por severidad.",
}


def _kpis(f: dict, b: dict | None, base: int | None, nac: dict | None = None) -> None:
    """Dibuja las cuatro tarjetas de KPI con su variación; por qué importa, el p90 y la referencia nacional (si hay filtro
    geográfico) van en el «?» de cada tarjeta."""
    def secciones(clave: str, valor: str, *antes: tuple[str, str]) -> tuple[tuple[str, str], ...]:
        return (("Por qué importa", POR_QUE[clave]),) + antes + ((("Nacional", valor),) if nac else ())

    c = cp.fila_kpi("inicio")
    with c[0]:
        cp.tarjeta_kpi("Egresos", tx.numero(f["egresos"]), _var(f, b, "egresos", "conteo", "neutro"), cp.ayuda("egreso"),
                       ":material/bed:", secciones("egresos", tx.numero(nac["egresos"]) if nac else ""))
    with c[1]:
        p90 = tx.estancia(f["p90"]) + (f" (en {base}: {tx.estancia(b['p90'])})" if b else "")
        cp.tarjeta_kpi("Estancia mediana", tx.estancia(f["mediana"]), _var(f, b, "mediana", "indice", "baja"), cp.ayuda("mediana"),
                       ":material/schedule:", secciones("mediana", tx.estancia(nac["mediana"]) if nac else "", ("p90", p90)))
    with c[2]:
        cp.tarjeta_kpi("Índice casemix", tx.numero(f["casemix"], 2), _var(f, b, "casemix", "indice", "neutro"), cp.ayuda("casemix"),
                       ":material/bar_chart:", secciones("casemix", tx.numero(nac["casemix"], 2) if nac else ""))
    with c[3]:
        cp.tarjeta_kpi("Mortalidad", tx.numero(f["mortalidad"], 2) + " %", _var(f, b, "mortalidad", "porcentaje", "baja"),
                       cp.ayuda("mortalidad"), ":material/favorite:",
                       secciones("mortalidad", tx.numero(nac["mortalidad"], 2) + " %" if nac else ""))


def _serie(sel: Seleccion, p: ind.Periodo, destacados: list[int], f: dict, b: dict | None) -> None:
    """Serie mensual de egresos de todos los hospitales y del panel."""
    df = _serie_df(cm.clave(sel))
    if b:
        pct = (f["egresos"] - b["egresos"]) / b["egresos"] * 100
        texto = tx.lectura("serie", p, egresos=f["egresos"], pct=pct, pocos_casos=b["n"] < ind.MIN_CASOS)
    else:
        col = "panel" if sel.panel else "todos"
        anio = df[df["mes"].dt.year == p.foco]
        pico = anio.loc[anio[col].idxmax()]
        texto = tx.lectura("serie_anio", p, egresos=f["egresos"], mes=tx.MESES[pico["mes"].month - 1], maximo=float(pico[col]))
    rango = (min(destacados), max(destacados))
    titulo = f"Egresos por mes ({rango[0]}" + (f"–{rango[1]})" if rango[1] != rango[0] else ")")
    todos = datos.anios_disponibles()
    notas = (f"Doble clic en el gráfico para ver {todos[0]}–{todos[-1]}.",)
    if any(getattr(sel, c) for c in ("sexo", "grupo_edad", "capitulo", "grd")):
        notas += ("La serie no se filtra por sexo, edad, capítulo ni GRD.",)
    visibles = df[df["mes"].dt.year.between(*rango)]
    tabla = cm.tabla_humana(visibles.assign(mes=visibles["mes"].dt.strftime("%m/%Y")),
                            {"mes": "Mes", "todos": "Egresos · todos los hospitales", "panel": "Egresos · panel estable"})
    cm.grafico(titulo, gr.serie_mensual(df, destacados, rango), texto, "g_serie", cp.ayuda("serie_mensual"), notas,
               gr.ALTURA_MOSAICO, tabla=tabla)


def _territorio(r: pd.DataFrame, p: ind.Periodo, n: int, pocos: bool) -> None:
    """Mapa de Chile por región del paciente: egresos en un año, o su variación % al comparar."""
    foco = r[r["ANIO"] == p.foco]
    sin = int(foco.loc[foco["REGION_PACIENTE"] == "Sin región", "episodios"].sum())
    notas = (f"{tx.numero(sin)} egresos sin región conocida no se pintan.",) if sin else ()
    if gr.forma("mapa", p, n) == "egresos":
        fila = foco.loc[foco["episodios"].idxmax()]
        texto = tx.lectura("territorio", p, region=fila["REGION_PACIENTE"], pct=float(fila["episodios"] / foco["episodios"].sum() * 100))
        cm.grafico("Egresos por región del paciente", gr.mapa_regiones(foco, "episodios"), texto, "g_territorio",
                   cp.ayuda("mapa_regiones"), notas,
                   tabla=cm.tabla_humana(foco[["ANIO", "REGION_PACIENTE", "episodios"]].sort_values("episodios", ascending=False)))
    else:
        cambio = cm.cambio(r, "REGION_PACIENTE", p, "episodios", relativo=True)
        confiable = cm.cambio(r, "REGION_PACIENTE", p, "episodios", relativo=True, minimo=ind.MIN_CASOS)
        texto = cm.lectura_cambio("territorio", p, confiable.drop("Sin región", errors="ignore"), ("region", "pct"), pocos)
        fig = gr.mapa_regiones(cambio.rename("variacion").reset_index(), "variacion", divergente=True, dec=1)
        tabla = cm.tabla_humana(cambio.rename("variacion").reset_index(), {"variacion": f"Variación % {p.base}→{p.foco}"})
        cm.grafico(f"Variación % de egresos por región del paciente ({p.base}→{p.foco})", fig, texto, "g_territorio",
                   cp.ayuda("mapa_regiones"), notas, tabla=tabla)


def _sexo(r: pd.DataFrame, p: ind.Periodo, n: int, pocos: bool, sin_sexo: int = 0) -> None:
    """Sexo: donut en un año, barras 100 % por año al comparar."""
    foco = r[r["ANIO"] == p.foco]
    if foco.empty:
        return
    mujeres = foco.loc[foco["SEXO"] == "Mujer", "pct"]
    texto = tx.lectura("sexo", p, pct_mujeres=float(mujeres.iloc[0]) if len(mujeres) else 0.0,
                       pocos_casos=pocos and p.modo == "comparar")
    fig = gr.donut(foco, "SEXO", "episodios") if gr.forma("sexo", p, n) == "donut" else gr.barras_100(r, "ANIO", "SEXO", "episodios")
    notas = (f"{tx.numero(sin_sexo)} egresos sin sexo registrado no se muestran.",) if sin_sexo > 0 else ()
    mostrado = foco if gr.forma("sexo", p, n) == "donut" else r
    cm.grafico("Sexo", fig, texto, "g_sexo", notas=notas, altura=gr.ALTURA_MOSAICO,
               tabla=cm.tabla_humana(mostrado[["ANIO", "SEXO", "episodios", "pct"]]))


def _edad(r: pd.DataFrame, p: ind.Periodo, n: int, pocos: bool) -> None:
    """Edad: columnas, columnas agrupadas o mapa de calor según el número de años."""
    forma = gr.forma("edad", p, n)
    if forma == "columnas":
        foco = r[r["ANIO"] == p.foco]
        fila = foco.loc[foco["pct"].idxmax()]
        texto = tx.lectura("edad", p, grupo=fila["GRUPO_EDAD"], pct=float(fila["pct"]))
        fig = gr.columnas(foco, "GRUPO_EDAD", "pct")
    else:
        texto = cm.lectura_cambio("edad", p, cm.cambio(r, "GRUPO_EDAD", p), ("grupo", "pct"), pocos)
        fig = (gr.columnas(r, "GRUPO_EDAD", "pct", "ANIO") if forma == "agrupadas"
               else gr.mapa_calor(r.assign(ANIO=r["ANIO"].astype(str)), "ANIO", "GRUPO_EDAD", "pct"))
    mostrado = r[r["ANIO"] == p.foco] if forma == "columnas" else r
    cm.grafico("Edad (% de egresos)", fig, texto, "g_edad", cp.ayuda("mapa_calor") if forma == "mapa_calor" else None,
               altura=gr.ALTURA_MOSAICO, tabla=cm.tabla_humana(mostrado[["ANIO", "GRUPO_EDAD", "episodios", "pct"]]))


def _lectura_tabla_ier(vista: pd.DataFrame, p: ind.Periodo) -> str:
    """Lectura de la tabla de un año: cuántos de los hospitales mostrados tienen IER > 1 y cuál es el más alto."""
    con = vista.dropna(subset=["ier"])
    if con.empty:
        return tx.lectura("hospitales", p, pocos_casos=True)
    alto = con.loc[con["ier"].idxmax()]
    return tx.lectura("hospitales", p, n=int((con["ier"] > 1).sum()), total=len(con), hospital=alto["HOSPITAL"],
                      ier=float(alto["ier"]))


def _lectura_cometa(c: pd.DataFrame, p: ind.Periodo, pocos: bool) -> str:
    """Lectura del cometa: cuántos hospitales dibujados bajaron su IER y cuál mejoró más."""
    if c.empty or pocos:
        return tx.lectura("hospitales", p, pocos_casos=True)
    mejora = c["ier_base"] - c["ier_foco"]
    k = int((mejora > 0).sum())
    if k == 0:
        return tx.lectura("hospitales_sin_mejora", p, total=len(c))
    m = c.loc[mejora.idxmax()]
    return tx.lectura("hospitales", p, n=k, total=len(c), hospital=m["nombre"], ier_base=float(m["ier_base"]),
                      ier_foco=float(m["ier_foco"]))


def _hospitales(sel: Seleccion, h: pd.DataFrame, p: ind.Periodo, n: int, pocos: bool) -> None:
    """Hospitales: tabla con IER en un año, cometa casemix-IER al comparar; la lectura interpreta lo dibujado."""
    cometa = gr.forma("hospitales", p, n) == "cometa"
    if sel.tipo == "AMBULATORIO":
        st.markdown("**Hospitales**")
        st.markdown("No aplica en ambulatorio: el IER y el cometa solo se calculan en hospitalización.")
        return
    st.markdown("**Hospitales**", help=cp.ayuda("cometa" if cometa else "ier"))
    foco = h[h["ANIO"] == p.foco].sort_values("episodios", ascending=False)
    if not cometa:
        vista = foco.head(15)
        tabla = pd.DataFrame({"Hospital": vista["HOSPITAL"], "Egresos": vista["episodios"].map(tx.numero),
                              "Casemix": vista["casemix"].map(lambda v: tx.numero(v, 2)),
                              "IER": vista["ier"].map(lambda v: tx.numero(v, 2))})
        st.dataframe(tabla, hide_index=True, key="t_hospitales",
                     column_config={"IER": st.column_config.Column("IER", help=cp.ayuda("ier")),
                                    "Casemix": st.column_config.Column("Casemix", help=cp.ayuda("casemix"))})
        texto = _lectura_tabla_ier(vista, p)
    else:
        base, fc = h[h["ANIO"] == p.base], foco.head(cm.TOP)
        c = fc.merge(base, on="COD_HOSPITAL", suffixes=("_foco", "_base")).dropna(subset=["ier_foco", "ier_base"])
        c = c.rename(columns={"HOSPITAL_foco": "nombre"})
        st.plotly_chart(gr.cometa(c), key="g_hospitales")
        texto = _lectura_cometa(c, p, pocos)
    if any(getattr(sel, k) for k in ("sexo", "grupo_edad", "capitulo")):
        st.caption("El IER no se filtra por sexo, edad ni capítulo: la tabla `grd` no tiene esas columnas.")
    cp.lectura(texto, "hospitales")


@st.cache_data
def _establecimientos() -> pd.DataFrame:
    """Los 76 hospitales del catálogo del DEIS con su región (la de la base): lectura chica, sin filtros de período."""
    e = datos.cargar("establecimientos", ("COD_HOSPITAL", "NOMBRE_DEIS", "COMUNA", "NIVEL_COMPLEJIDAD", "LATITUD", "LONGITUD"))
    cat = cm.catalogo()[["COD_HOSPITAL", "REGION_HOSPITAL"]].assign(COD=lambda c: c["COD_HOSPITAL"].astype(str))
    e = e.assign(COD=e["COD_HOSPITAL"].astype(str)).merge(cat[["COD", "REGION_HOSPITAL"]], on="COD", how="left")
    return e.drop(columns="COD").assign(REGION_HOSPITAL=lambda c: c["REGION_HOSPITAL"].astype(object))


# Mapa ancho: la rueda acerca, arrastrar mueve y el doble clic vuelve a la vista inicial; la barra trae + y − (zoom), mano y restablecer.
CONFIG_MAPA_HOSPITALES = {"scrollZoom": True, "displaylogo": False, "modeBarButtonsToRemove": ["select2d", "lasso2d"]}


def _mapa_hospitales(sel: Seleccion) -> None:
    """Dónde están los hospitales, por nivel de complejidad del catálogo del DEIS. Solo respeta la región: el tipo de
    atención y los años no cambian dónde está un hospital."""
    e = _establecimientos()
    if sel.region:
        e = e[e["REGION_HOSPITAL"] == sel.region]
    if e.empty:
        return
    altas = int((e["NIVEL_COMPLEJIDAD"] == "Alta Complejidad").sum())
    donde = f"de la región {sel.region} " if sel.region else ""
    hospitales = "hospital" if len(e) == 1 else "hospitales"
    es = "es" if len(e) == 1 else "son"
    texto = f"{tx.numero(altas)} de {tx.numero(len(e))} {hospitales} {donde}{es} de alta complejidad, según el catálogo del DEIS."
    tabla = pd.DataFrame({"Hospital": e["NOMBRE_DEIS"], "Comuna": e["COMUNA"],
                          "Complejidad": e["NIVEL_COMPLEJIDAD"].str.capitalize(),
                          "Región": e["REGION_HOSPITAL"].astype(object).fillna("Sin región")}).sort_values(["Región", "Hospital"])
    with st.container(key="mapa_hospitales"):  # a todo el ancho y bajo la tabla: queda bajo el pliegue
        cm.grafico("Dónde están los hospitales", gr.mapa_hospitales(e, sel.region), texto, "g_mapa_hospitales",
                   cp.ayuda("nivel_complejidad"), ("La complejidad viene del catálogo de establecimientos del DEIS-MINSAL.",),
                   tabla=tabla, config=CONFIG_MAPA_HOSPITALES)


def main() -> None:
    """Arma Inicio: título, ficha en una línea, aviso de cobertura, KPI, mosaico y hospitales."""
    cm.encabezado("Inicio")
    st.caption(_ficha(), help=cp.ayuda("que_hay_en_los_datos"))
    sel = actual()
    clave = cm.clave(sel)
    p = ind.periodo(sel.anios, datos.anios_disponibles())
    f = _valores(clave, p.foco)
    if f["egresos"] == 0:
        st.info(f"No hay egresos con esta selección en {p.foco}.")
        return
    b = _valores(clave, p.base) if p.base is not None else None
    if b is not None and b["egresos"] == 0:
        st.info(f"Este hospital no informa en {p.base}" if sel.hospital else f"La selección no tiene egresos en {p.base}")
        p, b = ind.Periodo("un_anio", p.foco, None), None
    cm.cobertura(sel, p)
    geo = sel.region or sel.servicio or sel.hospital
    nac = _valores(cm.clave(replace(sel, region=None, servicio=None, hospital=None)), p.foco) if geo else None
    with st.container(key="kpis_inicio"):
        _kpis(f, b, p.base, nac)
    if sel.grd:
        st.caption("El filtro de GRD solo se aplica al IER de la tarjeta de hospitales: los demás agregados no tienen GRD.")
    anios = [p.foco] if p.modo == "un_anio" else sel.anios
    n, pocos = len(anios), b is not None and b["n"] < ind.MIN_CASOS
    a = _agregados(clave, tuple(anios))
    # Mosaico: a la izquierda, tarjetas que se reparten y pasan de línea; a la derecha, el mapa (baja si no cabe).
    with st.container(key="mosaico_inicio"):
        with cp.fila("fcol", "inicio"):
            graficos = st.container()
            _territorio(a["territorio"], p, n, pocos)
    with graficos, cp.mosaico("inicio"):
        _serie(sel, p, anios, f, b)
        cm.capitulos(a["capitulos"], p, n, pocos, altura=gr.ALTURA_MOSAICO)
        _sexo(a["sexo"], p, n, pocos, a["sin_sexo"])
        _edad(a["edad"], p, n, pocos)
    with st.container(border=True, key="tabla_hospitales"):  # a todo el ancho: la tabla y el cometa necesitan espacio
        _hospitales(sel, a["hospitales"], p, n, pocos)
    _mapa_hospitales(sel)


main()
