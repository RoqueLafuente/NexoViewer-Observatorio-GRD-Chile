"""Hospitales › perfil: serie mensual, a quiénes atiende, qué casos atiende (con la complejidad de los casos), comorbilidad
y estancia.

Todo es del hospital en vista: ningún gráfico trae otro hospital ni ordena hospitales. Cada sección es una función
`(sel, cod)`; si el hospital no tiene egresos en el año foco y el tipo de atención, ninguna dibuja (la sección de actividad
ya lo explica con un aviso). Los datos se leen con las columnas justas y se filtran por hospital antes de agregarlos.
"""
import pandas as pd
import streamlit as st

import carga
import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import textos as tx
from paginas import comun as cm
from paginas import hospital_actividad as ha
from paginas import hospital_mapa as hm
from seleccion import Seleccion

SEXOS = {"HOMBRE": "Hombre", "MUJER": "Mujer"}
SIN_REGION, SIN_PROVINCIA = hm.SIN_REGION, hm.SIN_PROVINCIA
UMBRAL_DOMINANTE, partir_origen = hm.UMBRAL_DOMINANTE, hm.partir_origen  # la regla del origen dominante es una sola (mapa y barras)
ALTURA = 360  # px: igual alto para las tarjetas de una misma fila
TOP_REGIONES, TOP_PROVINCIAS, TOP_GRD = 8, 10, 10
MIN_PCT_RESTO = 1.0  # % del resto del origen bajo el cual no se dibujan sus barras (queda la cifra y la frase)
NOMBRES_SEVERIDAD = {1: "1 menor", 2: "2 moderada", 3: "3 mayor"}
# un solo juego de columnas de `perfil` para la pirámide, los capítulos y la complejidad (una lectura en frío)
COLS_PERFIL = ("ANIO", "COD_HOSPITAL", "TIPO_EPISODIO", "TRAMO_EDAD", "SEXO", "CAPITULO_CIE10", "episodios", "severidad_mayor",
               "diag_secundarios")
COLS_COMORBILIDAD = ("ANIO", "TRAMO_EDAD", "SEVERIDAD", "COMBINACION", "episodios", "fallecidos")
# La tabla `estancia` trae los días uno a uno hasta 30 y luego en tramos (31 = 31–60, 61 = 61–90, …; `sql_dias_agrupados`):
# el histograma dibuja los días exactos y cuenta en una nota los egresos de más de 30 días.
TOPE_DIAS = 30
TRAMOS_DIAS = {31: "31–60", 61: "61–90", 91: "91–180", 181: "181–365", 366: "Más de 365"}
COLS_FLUJOS = ("ANIO", "COD_HOSPITAL", "TIPO_EPISODIO", "REGION_PACIENTE", "PROVINCIA_PACIENTE", "episodios")
COLS_GRD = ("ANIO", "COD_HOSPITAL", "TIPO_GRD", "SEVERIDAD", "COD_GRD", "DESCRIPCION_GRD", "episodios", "peso_total")


def _sel(cod: str, tipo: str, anios) -> Seleccion:
    return Seleccion(sorted(anios), tipo, False, hospital=cod)


@st.cache_data(max_entries=16, show_spinner=False)
def serie_hospital(cod: str, tipo: str) -> pd.DataFrame:
    """Egresos por mes del hospital en todos los años (`hospital`); los meses sin datos quedan vacíos, no en cero."""
    s = _sel(cod, tipo, datos.anios_disponibles())
    m = datos.filtrar(datos.cargar_para("mensual", ("mes", "COD_HOSPITAL", "TIPO_EPISODIO", "episodios"), s), s)
    por_mes = m.groupby("mes")["episodios"].sum()
    meses = pd.date_range(f"{s.anios[0]}-01-01", f"{s.anios[-1]}-12-01", freq="MS", name="mes")
    return por_mes.reindex(meses).rename("hospital").reset_index()


def _egresos_del_anio(cod: str, tipo: str, anio: int) -> int:
    s = serie_hospital(cod, tipo)
    return int(s.loc[s["mes"].dt.year == anio, "hospital"].sum())


@st.cache_data(max_entries=32, show_spinner=False)
def perfil_hospital(cod: str, tipo: str, anios: tuple) -> dict:
    """Pirámide, capítulos CIE-10 y egresos (`n`) del hospital por año."""
    s = _sel(cod, tipo, anios)
    perf = datos.filtrar(datos.cargar_para("perfil", COLS_PERFIL, s), s)
    perf = perf.assign(GRUPO_EDAD=perf["TRAMO_EDAD"].map(ind.grupo_edad).astype(object))  # se mapea por categoría
    pir = perf[perf["SEXO"].isin(SEXOS)].dropna(subset=["GRUPO_EDAD"])
    pir = pir.groupby(["ANIO", "GRUPO_EDAD", "SEXO"], observed=True)["episodios"].sum().reset_index()
    pir["pct"] = pir["episodios"] / pir.groupby("ANIO")["episodios"].transform("sum") * 100
    edad = cm.pct_por(perf.dropna(subset=["GRUPO_EDAD"]), "GRUPO_EDAD")
    caps = cm.pct_por(perf.assign(capitulo=perf["CAPITULO_CIE10"].astype(str).map(tx.etiqueta_capitulo)), "capitulo")
    n = perf.groupby("ANIO", observed=True)["episodios"].sum()
    return {"piramide": pir.assign(SEXO=pir["SEXO"].map(SEXOS)), "edad": edad, "capitulos": caps,
            "n": {int(a): int(v) for a, v in n.items() if v > 0}}


def _con_pct(df: pd.DataFrame, total: float) -> pd.DataFrame:
    return df.assign(pct=df["episodios"] / total * 100 if total > 0 else 0.0)


@st.cache_data(max_entries=32, show_spinner=False)
def origen_hospital(cod: str, anio: int, tipo: str) -> dict:
    """De dónde vienen los egresos: por región y por provincia del paciente, y el % que viene de otra región.

    `total` cuenta también los egresos sin región o sin provincia; el % de otra región es sobre ese total.
    """
    return _resumen_origen(_flujos(cod, tipo, [anio]), cod)


def _flujos(cod: str, tipo: str, anios) -> pd.DataFrame:
    s = _sel(cod, tipo, anios)
    return datos.filtrar(datos.cargar_para("flujos", COLS_FLUJOS, s), s)


PROPIA, OTRAS = "Propia región", "Otras regiones"


@st.cache_data(max_entries=32, show_spinner=False)
def origen_por_anio(cod: str, tipo: str, anios: tuple) -> dict:
    """De dónde vienen los egresos en cada año elegido, con el mismo cálculo que `origen_hospital` de un año (una sola
    lectura filtrada): `lineas` (`ANIO`, `origen` propia/otras regiones, `episodios`, `pct`, con el % en blanco en los años
    con menos de `MIN_CASOS` egresos), `regiones` (cada región de residencia por año, para la tabla) y `chicos`."""
    f = _flujos(cod, tipo, anios)
    lineas, regiones, chicos = [], [], []
    for a, x in f.groupby("ANIO", observed=True):
        o = _resumen_origen(x, cod)
        if o["total"] == 0:
            continue
        a = int(a)
        pocos = o["total"] < ind.MIN_CASOS
        if pocos:
            chicos.append(a)
        r = o["regiones"]
        propia = int(r.loc[r["REGION_PACIENTE"] == o["region_hospital"], "episodios"].sum())
        otras = int(r.loc[~r["REGION_PACIENTE"].isin([o["region_hospital"], SIN_REGION]), "episodios"].sum())
        for nombre, n, pct in ((PROPIA, propia, propia / o["total"] * 100), (OTRAS, otras, o["otra_region"])):
            lineas.append({"ANIO": a, "origen": nombre, "episodios": n, "pct": None if pocos else pct})
        regiones.append(r.assign(ANIO=a))
    vacio = pd.DataFrame(columns=["ANIO", "origen", "episodios", "pct"])
    return {"lineas": pd.DataFrame(lineas) if lineas else vacio, "chicos": chicos,
            "regiones": pd.concat(regiones, ignore_index=True) if regiones else pd.DataFrame(
                columns=["ANIO", "REGION_PACIENTE", "episodios", "pct"])}


def _resumen_origen(f: pd.DataFrame, cod: str) -> dict:
    """El origen de las filas de `flujos` ya filtradas (un hospital, un año, un tipo de atención)."""
    f = f.assign(REGION_PACIENTE=f["REGION_PACIENTE"].astype(object).where(f["REGION_PACIENTE"].notna(), SIN_REGION),
                 PROVINCIA_PACIENTE=f["PROVINCIA_PACIENTE"].astype(object).where(f["PROVINCIA_PACIENTE"].notna(),
                                                                                  SIN_PROVINCIA))
    total = int(f["episodios"].sum())
    regiones = f.groupby("REGION_PACIENTE", observed=True)["episodios"].sum().reset_index()
    regiones = _con_pct(regiones[regiones["episodios"] > 0], total).sort_values("episodios", ascending=False)
    provincias = f.groupby(["PROVINCIA_PACIENTE", "REGION_PACIENTE"], observed=True)["episodios"].sum().reset_index()
    provincias = _con_pct(provincias[provincias["episodios"] > 0], total).sort_values("episodios", ascending=False)
    cat = cm.catalogo()
    propia = str(cat.loc[cat["COD_HOSPITAL"].astype(str) == cod, "REGION_HOSPITAL"].iloc[0])
    de_otra = regiones.loc[~regiones["REGION_PACIENTE"].isin([propia, SIN_REGION]), "episodios"].sum()
    sin = int(regiones.loc[regiones["REGION_PACIENTE"] == SIN_REGION, "episodios"].sum())
    return {"regiones": regiones.reset_index(drop=True), "provincias": provincias.reset_index(drop=True), "total": total,
            "region_hospital": propia, "otra_region": float(de_otra / total * 100) if total else 0.0, "sin_region": sin}


def _grd_filas(cod: str, tipo: str, anios) -> pd.DataFrame:
    s = _sel(cod, tipo, anios)
    g = datos.filtrar(datos.cargar_para("grd", COLS_GRD, s), s)
    return g[g["TIPO_GRD"].isin(ha.TIPOS_GRD[tipo])]


@st.cache_data(max_entries=32, show_spinner=False)
def grd_hospital(cod: str, anio: int, tipo: str) -> dict:
    """GRD de más peso del hospital (`top`, con su % del peso total `peso_total`) y la distribución por severidad."""
    return _resumen_grd(_grd_filas(cod, tipo, [anio]))


@st.cache_data(max_entries=32, show_spinner=False)
def severidad_por_anio(cod: str, tipo: str, anios: tuple) -> pd.DataFrame:
    """Severidad de cada año (`ANIO`, `SEVERIDAD`, `episodios`, `pct`) con el mismo cálculo que `grd_hospital` de un año:
    una sola lectura filtrada y un resumen por año (los años sin egresos no traen filas)."""
    g = _grd_filas(cod, tipo, anios)
    partes = [_resumen_grd(x)["severidad"].assign(ANIO=int(a)) for a, x in g.groupby("ANIO", observed=True) if len(x)]
    return (pd.concat(partes, ignore_index=True) if partes
            else pd.DataFrame(columns=["ANIO", "SEVERIDAD", "episodios", "pct"]))


def _resumen_grd(g: pd.DataFrame) -> dict:
    """GRD de más peso y severidad de las filas `grd` ya filtradas (un hospital, un año, un tipo de atención)."""
    peso = float(g["peso_total"].sum())
    por = g.groupby(["COD_GRD", "DESCRIPCION_GRD"], observed=True)[["episodios", "peso_total"]].sum().reset_index()
    por = por[por["episodios"] > 0]
    por = por.assign(COD_GRD=por["COD_GRD"].astype(str), DESCRIPCION_GRD=por["DESCRIPCION_GRD"].astype(str),
                     pct_peso=por["peso_total"] / peso * 100 if peso > 0 else 0.0)
    top = por.nlargest(TOP_GRD, "peso_total").reset_index(drop=True)
    sev = g[g["SEVERIDAD"].isin(NOMBRES_SEVERIDAD)].groupby("SEVERIDAD", observed=True)["episodios"].sum().reset_index()
    sev = sev.assign(SEVERIDAD=sev["SEVERIDAD"].astype(int))
    sev = sev.assign(pct=sev["episodios"] / sev["episodios"].sum() * 100 if len(sev) else 0.0)
    return {"top": top, "peso_total": peso, "n_grd": len(por), "severidad": sev,
            "sin_severidad": int(g["episodios"].sum() - sev["episodios"].sum())}


def _periodo(sel: Seleccion) -> ind.Periodo:
    return ind.periodo(sel.anios, datos.anios_disponibles())


def _anios_vistos(sel: Seleccion, p: ind.Periodo) -> list[int]:
    """Años que se dibujan: el foco solo, o todos los elegidos al comparar (como Inicio)."""
    return [p.foco] if p.modo == "un_anio" else sorted(sel.anios)


def anios_con_egresos(sel: Seleccion, cod: str, p: ind.Periodo) -> list[int]:
    """Años vistos (el foco, o todos los elegidos al comparar) en que el hospital tiene egresos del tipo elegido."""
    return [a for a in _anios_vistos(sel, p) if _egresos_del_anio(cod, sel.tipo, a) > 0]


def _hay_egresos(sel: Seleccion, cod: str, p: ind.Periodo) -> bool:
    """Con un año, si lo tiene; con varios, si tiene egresos en alguno de ellos (los demás quedan en blanco)."""
    return bool(anios_con_egresos(sel, cod, p))


def aviso_huecos(sel: Seleccion, cod: str, p: ind.Periodo) -> None:
    """Con varios años, un aviso corto con los años elegidos en que el hospital no tiene egresos: quedan en blanco."""
    if p.modo != "comparar":
        return
    faltan = sorted(set(_anios_vistos(sel, p)) - set(anios_con_egresos(sel, cod, p)))
    if faltan:
        st.caption(f"Sin egresos GRD de {sel.tipo.lower()} en {tx.rotulo_periodo(faltan)}: esos años quedan en blanco en "
                   "los gráficos año a año, no en cero.")


def _sin_foco(sel: Seleccion, cod: str, p: ind.Periodo) -> bool:
    """Con varios años, el último puede no tener egresos (el hospital dejó de informar): los gráficos de un año no van."""
    if _egresos_del_anio(cod, sel.tipo, p.foco) > 0:
        return False
    st.caption(f"Sin egresos GRD de {sel.tipo.lower()} en {p.foco}: los gráficos del último año no se muestran.")
    return True


def _aviso_pocos(n: int, anio: int) -> None:
    """Dice cuántos egresos hay cuando son tan pocos que un porcentaje engaña (no se esconde nada)."""
    if n < ind.MIN_CASOS:
        st.caption(f"En {anio} el hospital tuvo solo {tx.numero(n)} egresos de este tipo: los porcentajes describen muy "
                   "pocos casos y conviene mirar los conteos de «Ver en tabla».")


def serie_mensual(sel: Seleccion, cod: str) -> None:
    """Egresos por mes del hospital en los meses de los años elegidos, y solo esos (con un año, sus 12 meses); la franja de
    la pandemia va si cae en lo que se ve."""
    p = _periodo(sel)
    if not _hay_egresos(sel, cod, p):
        return
    df = serie_hospital(cod, sel.tipo)
    anios = _anios_vistos(sel, p)
    egresos = _egresos_del_anio(cod, sel.tipo, p.foco)
    base = _egresos_del_anio(cod, sel.tipo, p.base) if p.base is not None else 0
    if egresos == 0:  # varios años y el último sin egresos: no hay mes más alto que contar
        texto = f"El hospital no tiene egresos de este tipo en {p.foco}; la línea muestra los meses en que sí informa."
    elif base >= ind.MIN_CASOS:
        texto = tx.lectura("serie", p, egresos=egresos, pct=(egresos - base) / base * 100)
    else:  # sin año base con casos suficientes no se compara: se dice cuándo hubo más egresos
        anio = df[df["mes"].dt.year == p.foco]
        pico = anio.loc[anio["hospital"].idxmax()]
        texto = tx.lectura("serie_anio", p, egresos=egresos, mes=tx.MESES[pico["mes"].month - 1], maximo=float(pico["hospital"]))
    # la regla de años de la página: solo los meses de los años elegidos
    titulo = tx.con_periodo("Egresos por mes", anios)
    df = df[df["mes"].dt.year.isin(anios)]
    tabla = cm.tabla_humana(df.assign(mes=df["mes"].dt.strftime("%m/%Y")), {"mes": "Mes", "hospital": "Egresos"})
    notas = ()
    if df["hospital"].isna().any():
        notas += ("Los meses sin línea son meses en que el hospital no informa egresos de este tipo.",)
    with st.container(key="hosp_serie"):
        st.subheader("Evolución mensual")
        cm.grafico(titulo, gr.serie_meses(df, "hospital", anios, "Este hospital", gr._C["primary"]), texto, "g_hosp_serie", cp.ayuda("serie_hospital"), notas,
                   tabla=tabla)


def _otra_region(pct: float) -> str:
    """«El 12 %» o «Menos del 1 %»: un 0,04 % no se lee como «0 %»."""
    return "Menos del 1 %" if 0 < pct < 1 else f"El {hm.pct_texto(pct)} %"


_pct_cifra = hm.pct_cifra  # misma redondeo que la lectura del mapa (un decimal, nunca 99,95 a 100)


def frase_dominante(dom: pd.Series, region_hospital: str, anio: int, columna: str) -> str:
    """«El 99,3 % de los egresos de 2025 viene de la propia región»; si no es la región del hospital, dice cuál es."""
    origen = str(dom[columna])
    if columna == "PROVINCIA_PACIENTE":
        donde = f"la provincia {origen.title()}"
    else:
        donde = "la propia región" if origen == region_hospital else f"la región {origen}"
    return f"El {_pct_cifra(float(dom['pct']))} % de los egresos de {anio} viene de {donde}."


def _lectura_resto(resto: pd.DataFrame, unidad: str, plural: str) -> str:
    """«El 0,7 % de los egresos, 273, viene de otras 14 regiones» (sin «restante»: «Sin región» también queda fuera)."""
    pct, n = float(resto["pct"].sum()), len(resto)
    cifra = "Menos del 0,1 %" if pct < 0.05 else f"El {tx.numero(pct, 1)} %"
    otras = f"otra {unidad}" if n == 1 else f"otras {n} {plural}"
    return f"{cifra} de los egresos, {tx.numero(int(resto['episodios'].sum()))}, viene de {otras}."


def _con_dominante(frase: str, dom: pd.Series, resto: pd.DataFrame, etiqueta: str, unidad: tuple[str, str], key: str,
                   notas: tuple[str, ...], tabla: pd.DataFrame, top_n: int, anio: int) -> None:
    """Cifra grande del origen dominante y, debajo, un gráfico que siempre aparece:

    - si el resto suma `MIN_PCT_RESTO` % o más, barras solo del resto con su propia escala (el eje sigue al máximo del resto);
    - si suma menos (Sótero: 99,9 % de la propia región), barras del dominante y del resto en la escala de 0 a 100 %: se ve
      que casi todo viene de un lugar sin dibujar barras de 0,003 % con escala propia (ruido que parecía un error). Antes
      ese caso quedaba sin gráfico, solo con la cifra, y la persona no encontraba el origen por región.
    """
    visibles = resto.nlargest(top_n, "episodios")
    lectura = _lectura_resto(resto, *unidad) if len(resto) else ""
    if len(resto) > len(visibles):
        notas += (f"Se muestran las otras {unidad[1]} con más egresos (hasta {top_n}); «Ver en tabla» trae todas.",)
    if visibles.empty or float(resto["pct"].sum()) < MIN_PCT_RESTO:
        barras = pd.concat([dom.to_frame().T, visibles.head(top_n - 1)], ignore_index=True)
        barras = barras.assign(pct=barras["pct"].astype(float), episodios=barras["episodios"].astype(float))
        textos = [gr.etiqueta_pct(float(v)) + " %" for v in barras["pct"]]
        fig = gr.barras_h(barras, etiqueta, "pct", textos=textos)
        fig.update_xaxes(range=[0, 118], ticksuffix=" %")  # escala absoluta; el rótulo de 100 % no se corta
        cm.grafico(tx.con_periodo(f"{unidad[1].capitalize()} de residencia (% de egresos del hospital)", [anio]), fig, lectura,
                   key, cp.ayuda("origen_hospital"), notas, altura=ALTURA, tabla=tabla, cifra=frase)
        return
    textos = [gr.etiqueta_pct(float(v)) + " %" for v in visibles["pct"]]  # cada barra con sus decimales: nunca «0,0»
    fig = gr.barras_h(visibles, etiqueta, "pct", textos=textos)
    fig.update_xaxes(ticksuffix=" %")
    cm.grafico(tx.con_periodo(f"Las otras {unidad[1]} (% de egresos del hospital)", [anio]), fig, lectura, key,
               cp.ayuda("origen_hospital"), notas, altura=ALTURA, tabla=tabla, cifra=frase)


def _origen_regiones(o: dict, anio: int, pocos: bool) -> None:
    r = o["regiones"][o["regiones"]["REGION_PACIENTE"] != SIN_REGION]
    if r.empty:
        return
    notas_sin = ((f"{tx.numero(o['sin_region'])} egresos sin región conocida no se grafican, pero cuentan en el total.",)
                 if o["sin_region"] else ())
    tabla = cm.tabla_humana(o["regiones"].assign(ANIO=anio)[["ANIO", "REGION_PACIENTE", "episodios", "pct"]])
    dom, resto = (None, None) if pocos else partir_origen(o["regiones"])
    if dom is not None:
        frase = frase_dominante(dom, o["region_hospital"], anio, "REGION_PACIENTE")
        _con_dominante(frase, dom, resto, "REGION_PACIENTE", ("región", "regiones"), "g_hosp_origen_region", notas_sin,
                       tabla, TOP_REGIONES, anio)
        return
    top = r.nlargest(TOP_REGIONES, "episodios")
    if not pocos:  # una región que redondea a 0,0 % solo ensucia el gráfico; sigue en la tabla
        top = top[top["pct"] >= 0.05]
    valor = "episodios" if pocos else "pct"
    texto = (f"Solo hay {tx.numero(o['total'])} egresos en {anio}: el gráfico muestra conteos, no porcentajes." if pocos else
             f"{_otra_region(o['otra_region'])} de los egresos de {anio} viene de otra región que la del hospital "
             f"({o['region_hospital']}).")
    notas = ((f"Se muestran las regiones con más egresos (hasta {TOP_REGIONES}); «Ver en tabla» trae todas.",)
             if len(r) > len(top) else ()) + notas_sin
    cm.grafico(tx.con_periodo("Región de residencia" + (" (egresos)" if pocos else " (% de egresos)"), [anio]), gr.barras_h(top, "REGION_PACIENTE", valor, 0 if pocos else 1),
               texto, "g_hosp_origen_region", cp.ayuda("origen_hospital"), notas, altura=ALTURA, tabla=tabla)


def _titulo_provincia(x) -> str:
    return x if x == SIN_PROVINCIA else str(x).title()


def _origen_provincias(o: dict, anio: int, pocos: bool) -> None:
    p = o["provincias"]
    if p.empty:
        return
    tabla = cm.tabla_humana(p.assign(ANIO=anio)[["ANIO", "PROVINCIA_PACIENTE", "REGION_PACIENTE", "episodios", "pct"]],
                            {"PROVINCIA_PACIENTE": "Provincia del paciente"})
    dom, resto = (None, None) if pocos else partir_origen(p)
    if dom is not None:
        sin = int(p.loc[p["PROVINCIA_PACIENTE"] == SIN_PROVINCIA, "episodios"].sum())
        notas = ((f"{tx.numero(sin)} egresos sin provincia conocida no se grafican, pero cuentan en el total.",) if sin else ())
        frase = frase_dominante(dom, o["region_hospital"], anio, "PROVINCIA_PACIENTE")
        _con_dominante(frase, pd.concat([dom, pd.Series({"etiqueta": _titulo_provincia(dom["PROVINCIA_PACIENTE"])})]),
                       resto.assign(etiqueta=resto["PROVINCIA_PACIENTE"].map(_titulo_provincia)), "etiqueta",
                       ("provincia", "provincias"), "g_hosp_origen_provincia", notas, tabla, TOP_PROVINCIAS, anio)
        return
    conocidas = p[p["PROVINCIA_PACIENTE"] != SIN_PROVINCIA]  # «Sin provincia» no es una provincia: queda en el total y en la tabla
    if conocidas.empty:
        return
    sin = int(p.loc[p["PROVINCIA_PACIENTE"] == SIN_PROVINCIA, "episodios"].sum())
    top = conocidas.nlargest(TOP_PROVINCIAS, "episodios")
    top = top.assign(etiqueta=top["PROVINCIA_PACIENTE"].map(_titulo_provincia))
    fila = top.iloc[0]
    texto = (f"{fila['etiqueta']} es la provincia de residencia de más egresos de {anio}: {tx.numero(fila['episodios'])} "
             f"de {tx.numero(o['total'])}" + ("." if pocos else f" ({tx.numero(fila['pct'], 0)} %)."))
    notas = ((f"Se muestran las {TOP_PROVINCIAS} provincias con más egresos de {len(conocidas)}; «Ver en tabla» trae todas.",)
             if len(conocidas) > TOP_PROVINCIAS else ())
    if sin:
        notas += (f"{tx.numero(sin)} egresos sin provincia conocida no se grafican, pero cuentan en el total.",)
    cm.grafico(tx.con_periodo("Provincias de residencia (egresos)", [anio]), gr.barras_h(top, "etiqueta", "episodios", 0), texto,
               "g_hosp_origen_provincia", cp.ayuda("origen_hospital"), notas, altura=ALTURA, tabla=tabla)


def quienes(sel: Seleccion, cod: str) -> None:
    """Pirámide por edad y sexo, y de qué regiones y provincias vienen los egresos del hospital."""
    p = _periodo(sel)
    if not _hay_egresos(sel, cod, p):
        return
    d = perfil_hospital(cod, sel.tipo, tuple(_anios_vistos(sel, p)))
    o = origen_hospital(cod, p.foco, sel.tipo)
    pocos = o["total"] < ind.MIN_CASOS
    with st.container(key="hosp_quienes"):
        st.subheader("A quiénes atiende")
        aviso_huecos(sel, cod, p)
        _aviso_pocos(o["total"], p.foco)
        mosaico = cp.mosaico("hosp_quienes")
        with mosaico:
            _piramide(d, p, pocos, _anios_vistos(sel, p))
        if p.modo == "comparar":
            with mosaico:
                _origen_anios(cod, sel.tipo, _anios_vistos(sel, p))
        with mosaico:
            _origen_regiones(o, p.foco, pocos)
        with mosaico:
            _origen_provincias(o, p.foco, pocos)


def _piramide(d: dict, p: ind.Periodo, pocos: bool, vistos: list[int] | None = None) -> None:
    anios = [p.foco] if p.modo == "un_anio" else [p.base, p.foco]
    pir = d["piramide"][d["piramide"]["ANIO"].isin(anios)]
    edad = d["edad"][d["edad"]["ANIO"] == p.foco]
    if pir[pir["ANIO"] == p.foco].empty or edad.empty:
        return
    fila = edad.loc[edad["pct"].idxmax()]
    texto = tx.lectura("edad", ind.Periodo("un_anio", p.foco, p.base), grupo=fila["GRUPO_EDAD"], pct=float(fila["pct"]),
                       pocos_casos=False)
    con_contorno = p.modo == "comparar" and p.base in set(pir["ANIO"])
    titulo = tx.con_periodo("Pirámide por edad y sexo (% de egresos)", [p.foco]) + (f", contorno {p.base}" if con_contorno else "")
    notas = ()
    if p.modo == "comparar":  # la pirámide superpone dos años: se dice cuáles quedan fuera y si falta el contorno
        if not con_contorno:
            notas += (f"En {p.base} el hospital no tiene egresos de este tipo: la pirámide va sin contorno.",)
        medio = [a for a in (vistos or []) if a not in (p.base, p.foco)]
        if medio:
            notas += (f"La pirámide superpone el primer y el último año elegidos; {tx.rotulo_periodo(medio)} no se "
                      "dibuja{} (está en «Ver en tabla»).".format("n" if len(medio) > 1 else ""),)
            pir_tabla = d["piramide"][d["piramide"]["ANIO"].isin(vistos)]
        else:
            pir_tabla = pir
    else:
        pir_tabla = pir
    cm.grafico(titulo, gr.piramide(pir), texto, "g_hosp_piramide", cp.ayuda("piramide"), notas, altura=ALTURA,
               tabla=cm.tabla_humana(pir_tabla[["ANIO", "GRUPO_EDAD", "SEXO", "episodios", "pct"]]))


def _origen_anios(cod: str, tipo: str, anios: list[int]) -> None:
    """Origen año a año: % de los egresos de cada año que viene de la propia región y de otras regiones (no un 100 %
    apilado: con 99,9 % de la propia región sería una barra de un solo color). Todas las regiones, año por año, en la tabla."""
    o = origen_por_anio(cod, tipo, tuple(anios))
    df = o["lineas"]
    if df.empty:
        return
    otras = df[df["origen"] == OTRAS].dropna(subset=["pct"]).sort_values("ANIO")
    if len(otras) >= 2:
        a, b = otras.iloc[0], otras.iloc[-1]
        texto = (f"El % de egresos de personas que viven en otra región pasa de {gr.etiqueta_pct(a['pct'])} % en "
                 f"{int(a['ANIO'])} a {gr.etiqueta_pct(b['pct'])} % en {int(b['ANIO'])}.")
    else:
        texto = "Con un solo año con egresos suficientes en el período, cada línea es un punto."
    notas = _notas_anios(anios, o["chicos"]) + ("Los egresos sin región conocida cuentan en el total, pero no en estas dos líneas.",)
    regiones = o["regiones"]
    tabla = cm.tabla_humana(regiones.sort_values(["ANIO", "episodios"], ascending=[True, False])[
        ["ANIO", "REGION_PACIENTE", "episodios", "pct"]])
    cm.grafico(tx.con_periodo("Origen de los egresos (% de cada año)", anios),
               gr.lineas_anios(df, "origen", "pct", anios, sufijo=" %"), texto, "g_hosp_origen_anios",
               cp.ayuda("origen_hospital"), notas, altura=ALTURA, tabla=tabla)


LARGO_LINEA_GRD = 30  # caracteres por línea del rótulo de un GRD; va en dos líneas como máximo
ALTO_BARRA_GRD = 40  # px por barra del gráfico de GRD (rótulos de dos líneas)


def _etiqueta_grd(fila: pd.Series, largo: int = LARGO_LINEA_GRD) -> str:
    """«Otros procedimientos sobre<br>sistema musculoesquelético…»: la descripción sin el prefijo MH/PH, en tipo oración y
    partida en dos líneas (antes se cortaba a 28 caracteres y dos GRD distintos quedaban iguales). Lo que no cabe en dos
    líneas termina en «…»; la descripción completa está en «Ver en tabla»."""
    import textwrap
    d = str(fila["DESCRIPCION_GRD"]).split(" ", 1)[-1].capitalize()
    lineas = textwrap.wrap(d, largo, break_on_hyphens=False) or [d]
    if len(lineas) > 2:
        lineas = [lineas[0], lineas[1][:largo - 1].rstrip() + "…"]
    return "<br>".join(lineas)


def _grd(g: dict, anio: int, ultimo: bool = False) -> None:
    """GRD de más peso de un año; con `ultimo` (varios años elegidos) el título dice que es el último año del período."""
    top = g["top"]
    if top.empty:
        return
    etiquetas = top.apply(_etiqueta_grd, axis=1)
    top = top.assign(etiqueta=[e if (etiquetas == e).sum() == 1 else f"{e} ({c})" for e, c in zip(etiquetas, top["COD_GRD"])])
    suma = float(top["pct_peso"].sum())
    texto = f"Los {len(top)} GRD de más peso suman el {hm.pct_texto(suma)} % del peso GRD del hospital en {anio}."
    notas = (f"El hospital atendió {tx.numero(g['n_grd'])} GRD distintos en {anio}.",)
    tabla = cm.tabla_humana(top.assign(ANIO=anio)[["ANIO", "COD_GRD", "DESCRIPCION_GRD", "episodios", "peso_total", "pct_peso"]],
                            {"COD_GRD": "Código GRD", "DESCRIPCION_GRD": "Descripción", "peso_total": "Peso GRD (suma)",
                             "pct_peso": "% del peso GRD del hospital"})
    fig = gr.barras_h(top, "etiqueta", "pct_peso", 1)
    fig.update_yaxes(automargin=True, tickfont=dict(size=11))  # una etiqueta larga encoge el área en vez de cortarse
    fig.update_layout(bargap=0.35)
    # rótulos de dos líneas: 40 px por barra para que no se monten (la tarjeta vecina se estira a este alto)
    titulo = "GRD de más peso del último año elegido (% del peso GRD)" if ultimo else \
        "GRD de más peso (% del peso GRD del hospital)"
    cm.grafico(tx.con_periodo(titulo, [anio]), fig, texto,
               "g_hosp_grd", cp.ayuda("grd_hospital"), notas, altura=max(ALTURA, ALTO_BARRA_GRD * len(top) + 60), tabla=tabla)


def _severidad(g: dict, anio: int, tipo: str, diag: float | None = None) -> None:
    if tipo == ha.AMB:
        st.caption("La severidad solo se registra en hospitalización: un egreso ambulatorio no tiene severidad.")
        return
    sev = g["severidad"]
    if sev.empty:
        st.caption(f"Ningún egreso de {anio} tiene severidad registrada.")
        return
    sev = sev.assign(nivel=sev["SEVERIDAD"].map(NOMBRES_SEVERIDAD))
    mayor = float(sev.loc[sev["SEVERIDAD"] == 3, "pct"].sum())
    notas = ((f"{tx.numero(g['sin_severidad'])} egresos sin severidad registrada no se grafican.",) if g["sin_severidad"] else ())
    if diag is not None:  # la otra cifra de la complejidad de los casos (antes, su propia sección)
        notas += (f"En {anio}, cada egreso tiene en promedio {tx.numero(diag, 2)} diagnósticos secundarios registrados.",)
    # un decimal, como «En cifras» (antes la lectura decía «33 %» y la tarjeta «32,8 %»)
    cm.grafico(tx.con_periodo("Severidad (% de egresos)", [anio]), gr.columnas(sev, "nivel", "pct"),
               f"El {tx.numero(mayor, 1)} % de los egresos de {anio} es de severidad mayor.", "g_hosp_severidad",
               cp.ayuda("severidad"), notas, altura=ALTURA,
               tabla=cm.tabla_humana(sev.assign(ANIO=anio)[["ANIO", "nivel", "episodios", "pct"]], {"nivel": "Severidad"}))


TOP_CAPITULOS_ANIOS = 5  # capítulos con línea propia al comparar años; el resto suma «Otros capítulos»
OTROS_CAPITULOS = "Otros capítulos"


def _ocultar_anios_chicos(df: pd.DataFrame, n: dict[int, int], valor: str = "pct") -> tuple[pd.DataFrame, list[int]]:
    """Deja en blanco (NaN) los años con menos de `MIN_CASOS` egresos: un porcentaje de tan pocos casos no es estable."""
    chicos = sorted(a for a, k in n.items() if 0 < k < ind.MIN_CASOS)
    return df.assign(**{valor: df[valor].where(~df["ANIO"].isin(chicos))}), chicos


def _notas_anios(anios: list[int], chicos: list[int]) -> tuple[str, ...]:
    notas = ()
    if chicos:
        notas += (f"{tx.rotulo_periodo(chicos).capitalize()} queda en blanco: menos de {ind.MIN_CASOS} egresos.",)
    if anios != list(range(anios[0], anios[-1] + 1)):
        notas += ("Solo se dibujan los años elegidos: la línea une años que no son seguidos.",)
    return notas


def _tabla_anios(df: pd.DataFrame, columnas: list[str], renombres: dict | None = None) -> pd.DataFrame:
    return cm.tabla_humana(df.sort_values(["ANIO"], kind="stable")[columnas], renombres)


def _de_a(serie: pd.DataFrame, dec: int = 1, sufijo: str = " %") -> str | None:
    """«de 30,1 % en 2021 a 32,8 % en 2025» con el primer y el último año con dato (None si hay menos de dos)."""
    s = serie.dropna(subset=["valor"]).sort_values("ANIO")
    if len(s) < 2:
        return None
    a, b = s.iloc[0], s.iloc[-1]
    return (f"de {tx.numero(a['valor'], dec)}{sufijo} en {int(a['ANIO'])} a {tx.numero(b['valor'], dec)}{sufijo} "
            f"en {int(b['ANIO'])}")


def _capitulos_anios(d: dict, anios: list[int]) -> None:
    """Capítulos CIE-10 año a año: una línea por cada uno de los más frecuentes del período y «Otros capítulos»."""
    caps = d["capitulos"][d["capitulos"]["ANIO"].isin(anios)]
    caps = caps.assign(capitulo=caps["capitulo"].astype(str))
    top = list(caps.groupby("capitulo")["episodios"].sum().nlargest(TOP_CAPITULOS_ANIOS).index)
    resto = caps[~caps["capitulo"].isin(top)].groupby("ANIO", as_index=False)[["episodios", "pct"]].sum()
    partes = [caps[caps["capitulo"] == c] for c in top]
    if len(resto):
        partes.append(resto.assign(capitulo=OTROS_CAPITULOS))
    df = pd.concat(partes, ignore_index=True)[["ANIO", "capitulo", "episodios", "pct"]]
    df, chicos = _ocultar_anios_chicos(df, d["n"])
    fila = df[df["capitulo"] == top[0]].rename(columns={"pct": "valor"})
    de_a = _de_a(fila)
    texto = (f"{top[0]} es el capítulo con más egresos del período" + (f": pasa {de_a}." if de_a else "."))
    notas = ((f"Van los {len(top)} capítulos con más egresos del período; los demás suman «{OTROS_CAPITULOS}».",)
             + _notas_anios(anios, chicos))
    fig = gr.lineas_anios(df, "capitulo", "pct", anios, sufijo=" %", alto=440)
    cm.grafico(tx.con_periodo("Capítulos CIE-10 (% de egresos)", anios), fig,
               texto, "g_hosp_capitulos", cp.ayuda("lineas_anios"), notas, tabla=_tabla_anios(df, ["ANIO", "capitulo", "episodios", "pct"]))


def _severidad_anios(cod: str, tipo: str, anios: list[int], n: dict[int, int]) -> None:
    """Severidad año a año: una línea por nivel (% de los egresos con severidad registrada de cada año)."""
    if tipo == ha.AMB:
        st.caption("La severidad solo se registra en hospitalización: un egreso ambulatorio no tiene severidad.")
        return
    sev = severidad_por_anio(cod, tipo, tuple(anios))
    if sev.empty:
        st.caption(f"Ningún egreso de {tx.rotulo_periodo(anios)} tiene severidad registrada.")
        return
    sev = sev.sort_values(["SEVERIDAD", "ANIO"]).assign(nivel=lambda x: x["SEVERIDAD"].map(NOMBRES_SEVERIDAD))
    sev, chicos = _ocultar_anios_chicos(sev, n)
    de_a = _de_a(sev[sev["SEVERIDAD"] == 3].rename(columns={"pct": "valor"}))
    texto = (f"El % de egresos de severidad mayor pasa {de_a}." if de_a
             else "Con un solo año con egresos en el período, cada línea es un punto.")
    cm.grafico(tx.con_periodo("Severidad (% de egresos)", anios), gr.lineas_anios(sev, "nivel", "pct", anios, sufijo=" %"),
               texto, "g_hosp_severidad", cp.ayuda("severidad"), _notas_anios(anios, chicos),
               tabla=_tabla_anios(sev, ["ANIO", "nivel", "episodios", "pct"], {"nivel": "Severidad"}))


def casos(sel: Seleccion, cod: str) -> None:
    """Capítulos CIE-10, GRD de más peso y severidad de los egresos del hospital, con los diagnósticos secundarios por
    egreso en la nota de la severidad (la severidad mayor ya está en «En cifras»). Con varios años, capítulos y severidad
    van año a año y los GRD de más peso son los del último año (lo dice su título)."""
    p = _periodo(sel)
    if not _hay_egresos(sel, cod, p):
        return
    anios = _anios_vistos(sel, p)
    if p.modo == "comparar":
        d = perfil_hospital(cod, sel.tipo, tuple(anios))
        with st.container(key="hosp_casos"):
            st.subheader("Qué casos atiende")
            aviso_huecos(sel, cod, p)
            _capitulos_anios(d, anios)  # a todo el ancho: siete líneas con su nombre al final necesitan sitio
            with cp.mosaico("hosp_casos"):
                _severidad_anios(cod, sel.tipo, anios, d["n"])
                if not _sin_foco(sel, cod, p):
                    _grd(grd_hospital(cod, p.foco, sel.tipo), p.foco, ultimo=True)
        return
    d = perfil_hospital(cod, sel.tipo, tuple(anios))
    g = grd_hospital(cod, p.foco, sel.tipo)
    n_foco = d["n"].get(p.foco, 0)
    pocos = p.base is not None and d["n"].get(p.base, 0) < ind.MIN_CASOS
    with st.container(key="hosp_casos"):
        st.subheader("Qué casos atiende")
        _aviso_pocos(n_foco, p.foco)
        mosaico = cp.mosaico("hosp_casos")
        with mosaico:
            cm.capitulos(d["capitulos"][d["capitulos"]["ANIO"].isin(anios)], p, len(anios), pocos, key="g_hosp_capitulos",
                         altura=ALTURA, periodo=tx.rotulo_periodo(set(anios) & set(d["n"])))  # solo años con egresos
        with mosaico:
            _grd(g, p.foco)
        with mosaico:
            c = complejidad_hospital(cod, sel.tipo, anios_complejidad(sel, p))["complejidad"].get(p.foco)
            _severidad(g, p.foco, sel.tipo, None if c is None else c["diag_secundarios"])


# ---------- complejidad de los casos, comorbilidad y estancia ----------

def _estancia_por_anio(cod: str, tipo: str, anios) -> pd.DataFrame:
    """Filas de `estancia` del hospital con el mismo juego de columnas que la actividad (una sola lectura en caché)."""
    s = _sel(cod, tipo, anios)
    return datos.filtrar(datos.cargar_para("estancia", ha.COLUMNAS["estancia"], s), s)


@st.cache_data(max_entries=32, show_spinner=False)
def complejidad_hospital(cod: str, tipo: str, anios: tuple) -> dict:
    """Por año: severidad mayor (% de egresos con severidad 3), diagnósticos secundarios por egreso y estancia mediana
    (`complejidad`), y los egresos (`n`). Mismo cálculo que el Perfil, solo con el hospital."""
    s = _sel(cod, tipo, anios)
    perf = datos.filtrar(datos.cargar_para("perfil", COLS_PERFIL, s), s)
    suma = perf.groupby("ANIO", observed=True)[["episodios", "severidad_mayor", "diag_secundarios"]].sum()
    est = _estancia_por_anio(cod, tipo, anios)
    mediana = {int(a): ind.percentil_estancia(g, 0.5) for a, g in est.groupby("ANIO", observed=True)}
    complejidad = {int(a): {"severidad_mayor": float(f["severidad_mayor"] / f["episodios"] * 100),
                            "diag_secundarios": float(f["diag_secundarios"] / f["episodios"]),
                            "estancia": mediana.get(int(a))} for a, f in suma.iterrows() if f["episodios"] > 0}
    return {"complejidad": complejidad, "n": {int(k): int(v) for k, v in suma["episodios"].items()}}


def anios_complejidad(sel: Seleccion, p: ind.Periodo) -> tuple:
    """Años con que se pide `complejidad_hospital` (los vistos y la base): una sola clave de caché para la sección y el resumen."""
    return tuple(sorted(set(_anios_vistos(sel, p)) | ({p.base} if p.base else set())))


@st.cache_data(max_entries=32, show_spinner=False)  # la carga la muestra `carga.calculando`
def comorbilidad_hospital(cod: str, foco: int, base: int | None, elegidas: tuple[str, ...]) -> dict:
    """Comorbilidad del hospital con las enfermedades `elegidas` (solo hospitalizaciones), con el cálculo del Perfil."""
    s = Seleccion(sorted(a for a in (foco, base) if a), ha.HOSP, False, hospital=cod)
    todas = datos.filtrar(datos.cargar_para("comorbilidad_hospital", COLS_COMORBILIDAD, s), s)
    return cm.calcular_comorbilidad(todas, foco, elegidas)


AL_MENOS_UNA = "Al menos una"


@st.cache_data(max_entries=32, show_spinner=False)
def cronicas_por_anio(cod: str, anios: tuple, elegidas: tuple[str, ...]) -> pd.DataFrame:
    """% de hospitalizaciones de cada año con cada enfermedad elegida y con al menos una (`ANIO`, `enfermedad`,
    `episodios` del año, `pct`, `oculta`), con la misma tabla y columnas que el bloque de un año (ninguna lectura nueva).
    Un año con menos de `MIN_CASOS` hospitalizaciones queda oculto (en blanco)."""
    s = Seleccion(sorted(anios), ha.HOSP, False, hospital=cod)
    todas = datos.filtrar(datos.cargar_para("comorbilidad_hospital", COLS_COMORBILIDAD, s), s)
    if todas.empty:
        return pd.DataFrame(columns=["ANIO", "enfermedad", "episodios", "pct", "oculta"])
    c = ind.contar_seleccionadas(todas, elegidas)
    total = c.groupby("ANIO", observed=True)["episodios"].sum()
    con = c[c["N_ELEGIDAS"] > 0].groupby("ANIO", observed=True)["episodios"].sum().reindex(total.index, fill_value=0)
    alguna = pd.DataFrame({"ANIO": total.index, "enfermedad": AL_MENOS_UNA, "episodios": total.values,
                           "pct": (con / total.where(total > 0) * 100).values})
    cada = ind.pct_por_cronica(todas, elegidas, "ANIO").assign(enfermedad=lambda x: x["cronica"].map(tx.NOMBRES_CRONICAS))
    r = pd.concat([alguna, cada[["ANIO", "enfermedad", "episodios", "pct"]]], ignore_index=True)
    r = r.assign(ANIO=r["ANIO"].astype(int).astype(str), episodios=r["episodios"].astype(int))  # el año no se oculta
    return ind.enmascarar(r[r["episodios"] > 0].reset_index(drop=True)).assign(ANIO=lambda x: x["ANIO"].astype(int))


def _cronicas_anios(cod: str, anios: list[int], elegidas: tuple[str, ...]) -> None:
    """Comorbilidad año a año: una línea con el % de hospitalizaciones con al menos una de las enfermedades elegidas y una
    por cada enfermedad."""
    df = cronicas_por_anio(cod, tuple(anios), elegidas)
    if df.empty:
        return
    alguna = df[df["enfermedad"] == AL_MENOS_UNA].dropna(subset=["pct"]).sort_values("ANIO")
    if len(alguna) >= 2:
        a, b = alguna.iloc[0], alguna.iloc[-1]
        texto = (f"El % de hospitalizaciones con al menos una de las enfermedades elegidas pasa de {tx.numero(a['pct'], 1)} % "
                 f"en {int(a['ANIO'])} a {tx.numero(b['pct'], 1)} % en {int(b['ANIO'])}; parte del aumento puede ser "
                 "codificación (desde 2020 se registran más diagnósticos secundarios).")
    else:
        texto = "Con un solo año con hospitalizaciones en el período, cada línea es un punto."
    chicos = sorted({int(a) for a in df.loc[df["oculta"], "ANIO"]})
    notas = _notas_anios(anios, []) + ((cm.AVISO_CELDAS + f" ({tx.rotulo_periodo(chicos)})",) if chicos else ())
    cm.grafico(tx.con_periodo("Hospitalizaciones con cada enfermedad (%)", anios),
               gr.lineas_anios(df.drop(columns="oculta"), "enfermedad", "pct", anios, sufijo=" %"), texto, "g_hosp_cr_anios",
               cp.ayuda("lineas_anios"), notas,
               tabla=cm.tabla_humana(df[["ANIO", "enfermedad", "episodios", "pct", "oculta"]],
                                     {"enfermedad": "Enfermedad", "episodios": "Hospitalizaciones",
                                      "pct": "% de hospitalizaciones"}))


def comorbilidad(sel: Seleccion, cod: str) -> None:
    """Bloque de comorbilidad del Perfil aplicado al hospital: la persona elige qué enfermedades cuentan (por defecto, las
    cuatro de siempre) y la elección se comparte con el Perfil. Siempre son hospitalizaciones."""
    p = _periodo(sel)
    if not _hay_egresos(sel, cod, p):
        return
    with st.container(key="hosp_comorbilidad"):
        st.subheader("Comorbilidad", help=cp.ayuda("comorbilidad"))  # la definición va en el «?», no en 4 líneas de texto
        if sel.tipo == ha.AMB:
            st.caption("La comorbilidad cuenta solo hospitalizaciones, aunque en la barra lateral esté elegido «Ambulatorio».")
        elegidas = cm.elegir_cronicas("hosp_cr_elegidas")
        st.caption("La elección se comparte con Análisis › Perfil.")
        resumen = st.container()  # la frase sale del cálculo, que se hace al dibujar los gráficos
        args = (cod, p.foco, p.base if p.modo == "comparar" else None, elegidas)

        def calcular() -> dict:
            with carga.calculando(("comorbilidad_hospital",) + args, "Calculando la comorbilidad del hospital…"):
                return comorbilidad_hospital(*args)
        if p.modo == "comparar" and elegidas:
            aviso_huecos(sel, cod, p)
            _cronicas_anios(cod, _anios_vistos(sel, p), elegidas)
            st.markdown(f"**Detalle del último año elegido, {p.foco}**")
        texto = cm.bloque_comorbilidad(p, elegidas, calcular, cm.CLAVES_CR_HOSPITAL, periodo=tx.rotulo_periodo([p.foco]))
        with resumen:
            cp.lectura(texto or "", key="hosp_resumen_comorbilidad")


@st.cache_data(max_entries=32, show_spinner=False)
def estancia_hospital(cod: str, anio: int, tipo: str) -> dict:
    """Distribución de días de estancia del hospital en el año: `todos` (cada día o tramo con egresos), `dias` (los días
    exactos hasta `tope`, lo que dibuja el histograma), `fuera` (egresos de más de `tope` días), mediana y percentil 90."""
    return _resumen_estancia(_estancia_por_anio(cod, tipo, [anio]))


@st.cache_data(max_entries=32, show_spinner=False)
def estancia_por_anio(cod: str, tipo: str, anios: tuple) -> dict[int, dict]:
    """`estancia_hospital` de cada año con una sola lectura filtrada (mismo resumen: misma mediana y percentil 90)."""
    est = _estancia_por_anio(cod, tipo, anios)
    return {int(a): _resumen_estancia(x) for a, x in est.groupby("ANIO", observed=True) if x["episodios"].sum() > 0}


def _resumen_estancia(est: pd.DataFrame) -> dict:
    por = est.groupby("DIAS", observed=True)["episodios"].sum()
    por = por[por > 0].rename_axis("DIAS").reset_index().astype({"DIAS": int, "episodios": int})
    dias = por[por["DIAS"] <= TOPE_DIAS]
    return {"todos": por, "dias": dias, "fuera": int(por["episodios"].sum() - dias["episodios"].sum()), "tope": TOPE_DIAS,
            "total": int(por["episodios"].sum()), "mediana": ind.percentil_estancia(est, 0.5),
            "p90": ind.percentil_estancia(est, 0.9)}


def _estancia_anios(cod: str, tipo: str, anios: list[int]) -> None:
    """Mediana y percentil 90 de la estancia en cada año elegido (los mismos del histograma de ese año). Sobre 30 días la
    tabla trae tramos, no días: ese punto no se dibuja y una nota lo dice."""
    por = estancia_por_anio(cod, tipo, tuple(anios))
    filas, sobre = [], set()
    for a, e in por.items():
        for nombre, clave in (("Percentil 90", "p90"), ("Mediana", "mediana")):
            v = e[clave]
            if v is not None and v > TOPE_DIAS:
                sobre.add(a)
            filas.append({"ANIO": a, "medida": nombre, "episodios": e["total"],
                          "dias": None if v is None or v > TOPE_DIAS else float(v)})
    if not filas:
        return
    df = pd.DataFrame(filas).sort_values(["medida", "ANIO"], ascending=[False, True], kind="stable")
    df, chicos = _ocultar_anios_chicos(df, {a: e["total"] for a, e in por.items()}, "dias")
    de_a = _de_a(df[df["medida"] == "Mediana"].rename(columns={"dias": "valor"}), 0, " días")
    texto = f"La estancia mediana pasa {de_a}." if de_a else "Con un solo año con egresos en el período, cada línea es un punto."
    notas = _notas_anios(anios, chicos)
    if sobre:
        notas += (f"En {tx.rotulo_periodo(sobre)} algún punto pasa de {TOPE_DIAS} días y no se dibuja: sobre 30 días la "
                  "base agrupa la estancia en tramos.",)
    fig = gr.lineas_anios(df, "medida", "dias", anios, dec=0, sufijo=" días",
                          colores={"Mediana": gr.COLORES["enfasis"], "Percentil 90": gr.COLORES["muted"]})
    cm.grafico(tx.con_periodo("Estancia mediana y percentil 90 (días)", anios), fig, texto, "g_hosp_estancia_anios",
               cp.ayuda("lineas_anios"), notas,
               tabla=_tabla_anios(df, ["ANIO", "medida", "episodios", "dias"], {"medida": "Medida", "dias": "Días"}))


def _dias(n: int) -> str:
    return "1 día" if n == 1 else f"{tx.numero(n)} días"


def _lectura_estancia(e: dict, anio: int) -> str:
    """«La mitad … dura 2 días o menos, y el 90 %, 14 días o menos»; sobre 30 días la tabla trae tramos, no días exactos."""
    if e["mediana"] > TOPE_DIAS:
        return f"Más de la mitad de los egresos de {anio} dura más de {TOPE_DIAS} días."
    texto = f"La mitad de los egresos de {anio} dura {_dias(e['mediana'])} o menos"
    if e["p90"] > TOPE_DIAS:
        return texto + f", y más del 10 % dura más de {TOPE_DIAS} días."
    return texto + f", y el 90 %, {_dias(e['p90'])} o menos."


def estancia(sel: Seleccion, cod: str) -> None:
    """Histograma de los días de estancia del hospital en el año foco, con la mediana y el percentil 90."""
    p = _periodo(sel)
    if not _hay_egresos(sel, cod, p):
        return
    e = estancia_hospital(cod, p.foco, sel.tipo)
    if e["total"] == 0 and p.modo == "un_anio":
        return
    with st.container(key="hosp_estancia"):
        st.subheader("Estancia")
        if p.modo == "comparar":
            _estancia_anios(cod, sel.tipo, _anios_vistos(sel, p))
            if e["total"] == 0:
                return
            st.caption(f"El histograma es del último año elegido, {p.foco} · {sel.tipo.capitalize()}")
        else:
            st.caption(f"Año {p.foco} · {sel.tipo.capitalize()}")  # la mediana y el percentil 90 van rotulados en el histograma
        notas = ()
        if e["fuera"]:
            pct = e["fuera"] / e["total"] * 100
            notas = (f"{tx.numero(e['fuera'])} egresos ({'menos del 1' if pct < 1 else tx.numero(pct, 0)} %) duran más de "
                     f"{TOPE_DIAS} días y no se grafican; «Ver en tabla» los trae por tramos (31–60, 61–90, 91–180, 181–365 "
                     "y más de 365 días).",)
        todos = e["todos"].assign(ANIO=p.foco, DIAS=e["todos"]["DIAS"].map(lambda d: TRAMOS_DIAS.get(d, str(d))))
        tabla = cm.tabla_humana(todos[["ANIO", "DIAS", "episodios"]], {"DIAS": "Días de estancia"})
        visibles = [v if v is not None and v <= TOPE_DIAS else None for v in (e["mediana"], e["p90"])]
        cm.grafico(tx.con_periodo("Días de estancia (egresos)", [p.foco]), gr.histograma_estancia(e["dias"], *visibles), _lectura_estancia(e, p.foco),
                   "g_hosp_estancia", cp.ayuda("histograma_estancia"), notas, tabla=tabla)


# ---------- estancia por severidad y por grupo de edad (Casos y estancia) ----------
# Salen de tablas que ya existen: `estancia_severidad` (solo hospitalización) y `estancia` (con TRAMO_EDAD). Describen
# cuánto duran los egresos de cada grupo dentro del mismo hospital; no comparan hospitales.
COLS_ESTANCIA_SEV = ("ANIO", "COD_HOSPITAL", "SEVERIDAD", "DIAS", "episodios")
COLS_ESTANCIA_EDAD = ("ANIO", "COD_HOSPITAL", "TIPO_EPISODIO", "TRAMO_EDAD", "DIAS", "episodios")


def _texto_dias(v: int | None) -> str:
    """«4 días», o el tramo cuando pasa de 30 («31–60 días»): sobre 30 días la base agrupa la estancia en tramos."""
    if v is None:
        return tx.SIN_DATO
    return f"{TRAMOS_DIAS.get(v, str(v))} días" if v > TOPE_DIAS else _dias(v)


@st.cache_data(max_entries=32, show_spinner=False)
def estancia_por_grupo(cod: str, tipo: str, anios: tuple, por: str) -> pd.DataFrame:
    """Mediana y percentil 90 de la estancia por año y grupo (`por` = «severidad» o «edad»): `ANIO`, `grupo`, `episodios`,
    `mediana`, `p90` (días; sobre 30, el inicio del tramo) y sus textos. Un grupo con menos de `MIN_CASOS` egresos en el
    año queda oculto (`oculta`, sin cifras). La severidad es solo de hospitalización."""
    s = _sel(cod, tipo, anios)
    if por == "severidad":
        e = datos.filtrar(datos.cargar_para("estancia_severidad", COLS_ESTANCIA_SEV, s), s)
        e = e[e["SEVERIDAD"].isin(NOMBRES_SEVERIDAD)]
        e = e.assign(grupo=e["SEVERIDAD"].astype(int).map(NOMBRES_SEVERIDAD).map(lambda n: f"Severidad {n}"))
        orden = [f"Severidad {n}" for n in NOMBRES_SEVERIDAD.values()]
    else:
        e = datos.filtrar(datos.cargar_para("estancia", COLS_ESTANCIA_EDAD, s), s)
        e = e.assign(grupo=e["TRAMO_EDAD"].map(ind.grupo_edad).astype(object)).dropna(subset=["grupo"])
        e = e.assign(grupo=e["grupo"].map(lambda g: f"{g} años"))
        orden = [f"{g} años" for g in ind.GRUPOS_EDAD]
    filas = []
    for (a, g), x in e.groupby(["ANIO", "grupo"], observed=True):
        n = int(x["episodios"].sum())
        if n == 0:
            continue
        oculta = n < ind.MIN_CASOS
        med = None if oculta else ind.percentil_estancia(x, 0.5)
        p90 = None if oculta else ind.percentil_estancia(x, 0.9)
        filas.append({"ANIO": int(a), "grupo": g, "episodios": n, "mediana": med, "p90": p90, "oculta": oculta,
                      "texto_mediana": _texto_dias(med), "texto_p90": _texto_dias(p90)})
    df = pd.DataFrame(filas, columns=["ANIO", "grupo", "episodios", "mediana", "p90", "oculta", "texto_mediana", "texto_p90"])
    df = df.assign(_o=df["grupo"].map({g: i for i, g in enumerate(orden)}))
    return df.sort_values(["ANIO", "_o"]).drop(columns="_o").reset_index(drop=True)


TITULOS_GRUPO = {"severidad": ("Estancia por severidad (días)", "g_hosp_estancia_severidad"),
                 "edad": ("Estancia por grupo de edad (días)", "g_hosp_estancia_edad")}
NOTA_TRAMOS = "Sobre 30 días la base agrupa la estancia en tramos: el punto va al inicio del tramo y el texto lo dice."
NOTA_GRUPOS = ("Cuánto duran los egresos de cada grupo en este hospital: depende de qué casos llegan (severidad, edad, "
               "diagnóstico), no compara hospitales.")


def _lectura_grupo(d: pd.DataFrame, por: str, anio: int) -> str:
    v = d.dropna(subset=["mediana"])
    if v.empty:
        return ""
    if por == "severidad" and {"Severidad 1 menor", "Severidad 3 mayor"} <= set(v["grupo"]):
        m = dict(zip(v["grupo"], v["texto_mediana"]))
        return (f"En {anio}, la mitad de los egresos de severidad mayor dura {m['Severidad 3 mayor']} o menos; en severidad "
                f"menor, {m['Severidad 1 menor']} o menos.")
    alto = v.loc[v["mediana"].idxmax()]
    return f"En {anio}, la estancia mediana más larga es la de {alto['grupo']}: {alto['texto_mediana']}."


def _estancia_grupo(cod: str, tipo: str, anios: list[int], por: str) -> None:
    """Mediana y percentil 90 por grupo (segmentos): con un año, una fila por grupo; con varios, una fila por grupo y año."""
    titulo, key = TITULOS_GRUPO[por]
    d = estancia_por_grupo(cod, tipo, tuple(anios), por)
    if d.empty:
        return
    ocultos = d[d["oculta"]]
    notas = (NOTA_GRUPOS,)
    if len(ocultos):
        notas += (f"{cm.AVISO_CELDAS} ({', '.join(f'{g} en {a}' for a, g in zip(ocultos['ANIO'], ocultos['grupo']))}).",)
    tabla = cm.tabla_humana(d[["ANIO", "grupo", "episodios", "texto_mediana", "texto_p90"]],
                            {"grupo": "Grupo", "texto_mediana": "Mediana", "texto_p90": "Percentil 90"})
    if len(anios) == 1:
        if ((d["p90"].fillna(0) > TOPE_DIAS) | (d["mediana"].fillna(0) > TOPE_DIAS)).any():
            notas += (NOTA_TRAMOS,)
        cm.grafico(tx.con_periodo(titulo, anios), gr.rango_estancia(d, "grupo"), _lectura_grupo(d, por, anios[0]), key,
                   cp.ayuda("estancia_grupos"), notas, altura=ALTURA, tabla=tabla)
        return
    # varios años: una fila por grupo y año (los años de un grupo, juntos), con la misma forma que con un año
    filas = d.dropna(subset=["mediana"]).assign(fila=lambda x: x["grupo"] + " · " + x["ANIO"].astype(str))
    orden = {g: i for i, g in enumerate(dict.fromkeys(d.sort_values("ANIO", kind="stable")["grupo"]))}
    filas = filas.assign(_g=filas["grupo"].map(orden)).sort_values(["_g", "ANIO"]).drop(columns="_g")
    if ((d["p90"].fillna(0) > TOPE_DIAS) | (d["mediana"].fillna(0) > TOPE_DIAS)).any():
        notas += (NOTA_TRAMOS,)
    a0, a1 = min(anios), max(anios)
    texto = ""
    if por == "severidad":
        m = filas[filas["grupo"] == "Severidad 3 mayor"].set_index("ANIO")["texto_mediana"]
        if a0 in m and a1 in m:
            texto = f"La estancia mediana de los egresos de severidad mayor es de {m[a0]} en {a0} y de {m[a1]} en {a1}."
    else:
        texto = _lectura_grupo(d[d["ANIO"] == a1], por, a1)
    cm.grafico(tx.con_periodo(titulo, anios), gr.rango_estancia(filas, "fila", alto_fila=24), texto, key,
               cp.ayuda("estancia_grupos"), notas, tabla=tabla)


def estancia_grupos(sel: Seleccion, cod: str) -> None:
    """Estancia por severidad (solo hospitalización) y por grupo de edad, lado a lado, con la regla de años de la página."""
    p = _periodo(sel)
    if not _hay_egresos(sel, cod, p):
        return
    anios = _anios_vistos(sel, p)
    with st.container(key="hosp_estancia_grupos"):
        # con un año, lado a lado; con varios (una fila por grupo y año), uno bajo otro a todo el ancho
        with cp.mosaico("hosp_estancia_grupos") if len(anios) == 1 else st.container():
            if sel.tipo == ha.HOSP:
                _estancia_grupo(cod, sel.tipo, anios, "severidad")
            _estancia_grupo(cod, sel.tipo, anios, "edad")
