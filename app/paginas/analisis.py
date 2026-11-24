"""Página Análisis: cuatro preguntas con respuesta corta calculada, gráficos con lectura, advertencia y cálculo."""
import pandas as pd
import streamlit as st

import carga
import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import textos as tx
from paginas import comun as cm
from seleccion import PESTANAS_ANALISIS as PESTANAS, Seleccion, actual

HOSP, AMB = "HOSPITALIZACIÓN", "AMBULATORIO"
SEXOS = {"HOMBRE": "Hombre", "MUJER": "Mujer"}
SIN_REGION = "Sin región"
TIPOS_GRD = {HOSP: ["MH", "PH"], AMB: ["MA", "PA"]}
BARRAS_PARETO = 150


SUBPESTANAS_PERFIL = ["Perfil general", "Comorbilidad"]
METODO = "Cómo se calcula y advertencias"


def _encabezado(pregunta: str):
    """Título de la pregunta; devuelve el espacio de la respuesta corta (una línea con `cp.lectura`), que se llena al
    final, o con un `info` neutro si no hay datos."""
    st.markdown(f"### {pregunta}")
    return st.container()


def _region_paciente(key: str) -> str | None:
    """Filtro propio de la pregunta Territorio: región de origen del paciente (no es la región del hospital de la barra lateral)."""
    regiones = sorted(str(r) for r in cm.catalogo()["REGION_HOSPITAL"].dropna().unique())
    cm.selector(st.columns(4)[0], "Región de origen del paciente", key, regiones, todos="Todas")
    return st.session_state.get(key)


def _cierre(titulo: str, aviso: str, calculo: str, tablas: str) -> None:
    """Un solo desplegable al final de la pregunta con su advertencia y el cálculo (la advertencia ya no va suelta)."""
    with st.container(key="metodo_analisis"):  # ancla del recorrido guiado
        with st.expander(METODO):
            st.markdown(f"**{titulo}** — {aviso}\n\n{calculo}\n\nFuente: {tablas}.")


def _sel(sel: Seleccion, **cambios) -> Seleccion:
    """Selección con solo los filtros globales (años, tipo, panel) más los filtros propios dados."""
    return Seleccion(sel.anios, cambios.pop("tipo", sel.tipo), cambios.pop("panel", sel.panel), **cambios)


# ---------- 1 · Actividad ----------

@st.cache_data(max_entries=32)
def _actividad(region: str | None) -> dict:
    """Índice 2019 = 100 por año: hospitalización del panel y de todos, y ambulatorio del panel."""
    anios = datos.anios_disponibles()
    m = {t: datos.filtrar(datos.cargar("mensual"), Seleccion(anios, t, False, region=region)) for t in (HOSP, AMB)}
    panel = {t: d[d["EN_PANEL_7_ANIOS"] == True] for t, d in m.items()}  # noqa: E712
    series = {"Hospitalización · panel": panel[HOSP], "Hospitalización · todos": m[HOSP], "Ambulatorio · panel": panel[AMB]}
    r = pd.concat([ind.indice_actividad(d).assign(TIPO_EPISODIO=k) for k, d in series.items() if not d.empty], ignore_index=True)
    ultimo = m[HOSP][m[HOSP]["mes"].dt.year == anios[-1]]
    calendario = panel[HOSP].groupby("mes")["episodios"].sum().reset_index()
    return {"serie": r, "calendario": calendario, "n_panel": panel[HOSP]["COD_HOSPITAL"].nunique(), "n_ultimo": ultimo["COD_HOSPITAL"].nunique(),
            "n_2019": m[HOSP][m[HOSP]["mes"].dt.year == anios[0]]["COD_HOSPITAL"].nunique(), "ultimo": anios[-1]}


def pregunta_1(sel: Seleccion) -> None:
    """P1: evolución de las hospitalizaciones desde 2019 (siempre 7 años y panel), descrita sin interpretarla."""
    caja = _encabezado("Evolución de las hospitalizaciones")
    a = _actividad(sel.region)
    s, u = a["serie"], a["ultimo"]
    if s.empty or "Hospitalización · panel" not in set(s["TIPO_EPISODIO"]):
        caja.info("No hay hospitales del panel con esta selección.")
        return
    st.caption(f"Aquí se miran siempre los 7 años (2019–{u}) y los {a['n_panel']} hospitales que informan todos los años, "
               "aunque en la barra lateral haya otra selección.")
    v = s.set_index(["TIPO_EPISODIO", "ANIO"])["indice"]
    hp, ht = v["Hospitalización · panel"], v["Hospitalización · todos"]
    amb = v.get("Ambulatorio · panel")
    texto = (f"Con el panel de {a['n_panel']} hospitales, el índice de hospitalización de {u} es {tx.numero(hp[u], 1)} "
             f"(2019 = 100), {_respecto_de_2019(hp[u])}.")
    if amb is not None and u in amb:
        texto += f" La atención ambulatoria tiene un índice de {tx.numero(amb[u], 1)}, {_respecto_de_2019(amb[u])}."
    with caja:  # el año más bajo de la serie lo rotula el gráfico; el índice con todos los hospitales, el desplegable
        cp.lectura(texto, key="resumen_actividad")
    cm.grafico("Índice de actividad (2019 = 100)", gr.linea_indice(s),
               tx.lectura("actividad", ind.Periodo("comparar", u, 2019), indice=float(hp[u])), "a_p1_indice",
               cp.ayuda("linea_indice"),
               tabla=cm.tabla_humana(s[["TIPO_EPISODIO", "ANIO", "episodios", "indice"]],
                                     {"TIPO_EPISODIO": "Serie", "indice": "Índice (2019 = 100)"}))
    cal = a["calendario"]
    por_dia = cal["episodios"] / cal["mes"].dt.days_in_month
    bajo, alto = cal.loc[por_dia.idxmin(), "mes"], cal.loc[por_dia.idxmax(), "mes"]
    cm.grafico(f"Calendario de hospitalizaciones · egresos por día de cada mes (panel, 2019–{u})", gr.calendario(cal),
               tx.lectura("calendario", ind.Periodo("un_anio", u, None), mes_bajo=_mes(bajo), bajo=float(por_dia.min()),
                          mes_alto=_mes(alto), alto=float(por_dia.max())), "a_p1_calendario", cp.ayuda("calendario"),
               tabla=cm.tabla_humana(cal.assign(mes=cal["mes"].dt.strftime("%m/%Y"), por_dia=por_dia),
                                     {"mes": "Mes", "por_dia": "Egresos por día"}))
    _cierre("Total vs panel", f"Con todos los hospitales, el índice de hospitalización de {u} es {tx.numero(ht[u], 1)}, no "
            f"{tx.numero(hp[u], 1)}: en {u} informan {a['n_ultimo']} hospitales y en 2019 {a['n_2019']}. La diferencia es "
            "cobertura, no actividad; por eso la respuesta usa el panel.",
            "Índice de actividad = egresos del año ÷ egresos de 2019 × 100, por separado para hospitalización y ambulatorio. "
            "El panel son los hospitales que informan los 7 años (`EN_PANEL_7_ANIOS`).", "tabla `mensual`")


def _respecto_de_2019(indice: float) -> str:
    """Descripción neutra del índice frente a la base: «10 % por debajo de 2019»."""
    d = round(abs(indice - 100))
    return "igual a 2019" if d == 0 else f"{tx.numero(d)} % {'por debajo' if indice < 100 else 'por encima'} de 2019"


def _mes(fecha: pd.Timestamp) -> str:
    """Mes y año en palabras: «abril de 2020»."""
    return f"{tx.MESES[fecha.month - 1]} de {fecha.year}"


# ---------- 2 · Perfil ----------

MAX_COMBINACIONES = cm.MAX_COMBINACIONES  # filas del mapa de mortalidad: las combinaciones con más hospitalizaciones
COLS_PERFIL = ("ANIO", "TIPO_EPISODIO", "TRAMO_EDAD", "SEXO", "CAPITULO_CIE10", "REGION_PACIENTE", "episodios",
               "severidad_mayor", "diag_secundarios")


@st.cache_data(max_entries=32, show_spinner=False)  # la carga la muestra `carga.calculando`
def _perfil(clave: tuple, anios: tuple) -> dict:
    """Quiénes (edad, sexo, región del paciente), por qué ingresan (capítulos) y cuán complejos son, por año."""
    s = cm.desde_clave(clave)
    perf = datos.filtrar(datos.cargar_para("perfil", COLS_PERFIL, s), s, list(anios))
    perf = perf.assign(GRUPO_EDAD=perf["TRAMO_EDAD"].map(ind.grupo_edad).astype(object))  # se mapea por categoría
    pir = perf[perf["SEXO"].isin(SEXOS)].dropna(subset=["GRUPO_EDAD"])
    pir = pir.groupby(["ANIO", "GRUPO_EDAD", "SEXO"], observed=True)["episodios"].sum().reset_index()
    pir["pct"] = pir["episodios"] / pir.groupby("ANIO")["episodios"].transform("sum") * 100
    edad = cm.pct_por(perf.dropna(subset=["GRUPO_EDAD"]), "GRUPO_EDAD")
    caps = cm.pct_por(perf.assign(capitulo=perf["CAPITULO_CIE10"].astype(str).map(tx.etiqueta_capitulo)), "capitulo")
    regiones = cm.pct_por(perf.assign(region=perf["REGION_PACIENTE"].astype(object).fillna(SIN_REGION)), "region")
    suma = perf.groupby("ANIO", observed=True)[["episodios", "severidad_mayor", "diag_secundarios"]].sum()
    est = datos.filtrar(datos.cargar_para("estancia", ("DIAS", "episodios"), s), s, list(anios))
    mediana = {int(a): ind.percentil_estancia(g, 0.5) for a, g in est.groupby("ANIO", observed=True)}
    complejidad = {int(a): {"severidad_mayor": float(f["severidad_mayor"] / f["episodios"] * 100),
                            "diag_secundarios": float(f["diag_secundarios"] / f["episodios"]),
                            "estancia": mediana.get(int(a))} for a, f in suma.iterrows() if f["episodios"] > 0}
    return {"piramide": pir.assign(SEXO=pir["SEXO"].map(SEXOS)), "edad": edad, "capitulos": caps, "regiones": regiones,
            "complejidad": complejidad, "n": {int(k): int(v) for k, v in suma["episodios"].items()}}


@st.cache_data(max_entries=32, show_spinner=False)  # la carga la muestra `carga.calculando`
def _comorbilidad(clave: tuple, foco: int, base: int | None, elegidas: tuple[str, ...]) -> dict:
    """Comorbilidad con las enfermedades `elegidas`: cuántas por hospitalización, cada una por edad, pares y mortalidad."""
    s = cm.desde_clave(clave)
    todas = datos.filtrar(datos.cargar_para("comorbilidad", ("ANIO", "TRAMO_EDAD", "SEVERIDAD", "COMBINACION", "episodios",
                                                             "fallecidos"), s), s, [a for a in (foco, base) if a])
    return cm.calcular_comorbilidad(todas, foco, elegidas)  # el cálculo se comparte con Hospitales


def _bloque(titulo: str) -> None:
    st.markdown(f"#### {titulo}")


def _por_anio(r: pd.DataFrame, col: str, p: ind.Periodo, n: int, pocos: bool, titulo: str, clave: str, key: str,
              campos: tuple[str, str], nombre: str) -> None:
    """Barras por categoría como en los capítulos: un año, base → foco o minigráficos según los años elegidos."""
    top = r[r["ANIO"] == p.foco].nlargest(cm.TOP, "pct")
    forma = gr.forma("capitulos", p, n)
    if forma == "barras":
        fila = top.iloc[0]
        cm.grafico(titulo, gr.barras_h(top, col, "pct"), tx.lectura(clave, p, **dict(zip(campos, (fila[col], float(fila["pct"]))))),
                   key, tabla=cm.tabla_humana(top[["ANIO", col, "episodios", "pct"]], {col: nombre}))
        return
    d = r[r[col].isin(top[col])]
    texto = cm.lectura_cambio(clave, p, cm.cambio(d, col, p), campos, pocos)
    fig = gr.barras_base_foco(d, col, "pct", "ANIO", p.base, p.foco) if forma == "base_foco" else gr.minigraficos(d, col, "pct", "ANIO")
    cm.grafico(titulo, fig, texto, key, tx.GLOSARIO["barras_base_foco" if forma == "base_foco" else "minigraficos"],
               tabla=cm.tabla_humana(d[["ANIO", col, "episodios", "pct"]].sort_values(["ANIO", "pct"], ascending=[True, False]),
                                     {col: nombre}))


def _complejidad(d: dict, p: ind.Periodo) -> None:
    """Tarjetas de severidad mayor, diagnósticos secundarios promedio y estancia mediana (compartidas con Hospitales)."""
    cm.tarjetas_complejidad(d["complejidad"], d["n"], p, clave="perfil_complejidad_kpi")


def _elegir_cronicas() -> tuple[str, ...]:
    """Selector de las enfermedades que cuentan como comorbilidad (compartido con Hospitales en `comun`)."""
    return cm.elegir_cronicas("cr_elegidas")


def _bloque_comorbilidad(sel: Seleccion, p: ind.Periodo, elegidas: tuple[str, ...]) -> str | None:
    """Dibuja el bloque Comorbilidad; devuelve la frase para la respuesta corta (None si no hay datos o elegidas)."""
    s = _sel(sel, tipo=HOSP, region=sel.region, sexo=sel.sexo)
    args = (cm.clave(s), p.foco, p.base if p.modo == "comparar" else None, elegidas)

    def calcular() -> dict:
        with carga.calculando(("comorbilidad",) + args, "Calculando la comorbilidad con tu selección…"):
            return _comorbilidad(*args)
    return cm.bloque_comorbilidad(p, elegidas, calcular, cm.CLAVES_CR_PERFIL)


def pregunta_perfil(sel: Seleccion, p: ind.Periodo) -> None:
    """Perfil de los egresos en dos sub-pestañas: Perfil general (quiénes, por qué ingresan, cuán complejos) y
    Comorbilidad (definida por la persona). El resumen habla solo del perfil; la comorbilidad tiene su propia lectura."""
    caja = _encabezado("¿Cómo es el perfil de los egresos y cómo cambió?")
    s = _sel(sel, region=sel.region, sexo=sel.sexo)
    anios = sorted(set(s.anios) | {p.foco} | ({p.base} if p.base else set()))
    with carga.calculando(("perfil", cm.clave(s), tuple(anios)), "Calculando el perfil con tu selección…"):
        d = _perfil(cm.clave(s), tuple(anios))
    if d["n"].get(p.foco, 0) == 0:
        caja.info(f"No hay egresos con esta selección en {p.foco}.")
        return
    if p.base is not None and d["n"].get(p.base, 0) == 0:
        p = ind.Periodo("un_anio", p.foco, None)
    edad, caps, pir = d["edad"], d["capitulos"], d["piramide"]
    mayores = edad[edad["GRUPO_EDAD"].isin(["60–74", "75+"])].groupby("ANIO")["pct"].sum()
    mujeres = pir[pir["SEXO"] == "Mujer"].groupby("ANIO")["pct"].sum()
    pocos = p.base is not None and d["n"].get(p.base, 0) < ind.MIN_CASOS
    if p.base is None or pocos:
        top = caps[caps["ANIO"] == p.foco].nlargest(1, "pct").iloc[0]
        respuesta = (f"En {p.foco}, el {tx.numero(mayores.get(p.foco, 0), 1)} % de los egresos es de 60 años o más "
                     f"y el {tx.numero(mujeres.get(p.foco, 0), 1)} % es de mujeres. La causa más frecuente es "
                     f"{tx.capitulo_corto(top['capitulo'])} ({tx.numero(top['pct'], 1)} %).")
    else:
        cap, dif = cm.mayor_cambio(cm.cambio(caps, "capitulo", p)) or ("—", 0.0)
        m0, m1 = mayores.get(p.base, 0), mayores.get(p.foco, 0)
        f0, f1 = mujeres.get(p.base, 0), mujeres.get(p.foco, 0)
        respuesta = (f"Entre {p.base} y {p.foco}, los egresos de 60 años o más pasaron del {tx.numero(m0, 1)} % al "
                     f"{tx.numero(m1, 1)} % del total, y los de mujeres, del {tx.numero(f0, 1)} % al {tx.numero(f1, 1)} %. "
                     f"La causa que más cambió fue {tx.capitulo_corto(cap)}, con {tx.numero(abs(dif), 1)} puntos "
                     f"{'más' if dif >= 0 else 'menos'}.")
    with caja:
        cp.lectura(respuesta, key="resumen_perfil")
    if s.tipo == AMB:
        st.caption("Con «Ambulatorio» en la barra lateral, «Perfil general» es de las atenciones ambulatorias; "
                   "la comorbilidad mira siempre hospitalizaciones.")
    cobertura = cm.cobertura(s, p)  # cambia cómo se leen las cifras: queda a la vista, sobre las sub-pestañas
    general, comorbilidad = st.tabs(SUBPESTANAS_PERFIL, key="a_perfil_sub", on_change="rerun")
    # Como las pestañas de la página: solo se calcula y dibuja la sub-pestaña abierta (la comorbilidad es lo más lento).
    if general.open:
        with general:
            _perfil_general(d, s, p, pocos)
    if comorbilidad.open:
        with comorbilidad:
            _pestana_comorbilidad(sel, p)
    _cierre("Codificación y edad", "Desde 2020 se registran más diagnósticos secundarios por episodio (3,75 → 5,70): parte del "
            "aumento de la comorbilidad y de la severidad es codificación. Cifras crudas, sin ajuste por edad."
            + ("" if cobertura else f" {tx.GLOSARIO['cobertura']}"),
            "% de egresos = episodios del grupo ÷ episodios del año × 100; la pirámide usa solo los episodios con sexo hombre o "
            "mujer y edad conocida. Severidad mayor = egresos con severidad 3 ÷ egresos × 100; diagnósticos secundarios por "
            "egreso = suma de diagnósticos secundarios ÷ egresos; estancia mediana = días del egreso que deja la mitad por "
            "debajo. Comorbilidad (solo hospitalización): cada hospitalización se cuenta con las enfermedades elegidas que "
            "aparecen entre sus diagnósticos secundarios; % con una enfermedad = hospitalizaciones con ella ÷ hospitalizaciones "
            "del grupo de edad × 100; pares = hospitalizaciones con las dos ÷ hospitalizaciones del año × 100; mortalidad = "
            "fallecidos ÷ hospitalizaciones × 100 por combinación de las elegidas y severidad (1 menor, 2 moderada, 3 mayor). "
            f"Celdas con menos de {ind.MIN_CASOS} episodios no se muestran.",
            "tablas `perfil` (quiénes, por qué, severidad y diagnósticos), `estancia` (mediana) y `comorbilidad`")


def _perfil_general(d: dict, s: Seleccion, p: ind.Periodo, pocos: bool) -> None:
    """Sub-pestaña Perfil general: quiénes, por qué ingresan y cuán complejos."""
    edad, caps, pir = d["edad"], d["capitulos"], d["piramide"]
    vistos = [p.foco] if p.modo == "un_anio" else s.anios
    n = len(vistos)

    _bloque("Quiénes")
    mosaico = cp.mosaico("perfil_quienes")
    with mosaico:
        anios_pir = [p.foco] if p.modo == "un_anio" else [p.base, p.foco]
        if p.modo == "un_anio":
            fila = edad[edad["ANIO"] == p.foco].nlargest(1, "pct").iloc[0]
            texto = tx.lectura("edad", p, grupo=fila["GRUPO_EDAD"], pct=float(fila["pct"]))
        else:
            texto = cm.lectura_cambio("edad", p, cm.cambio(edad, "GRUPO_EDAD", p), ("grupo", "pct"), pocos)
        titulo = "Pirámide por edad y sexo (% de egresos)" + ("" if p.modo == "un_anio" else f" · {p.base} en contorno")
        mostrada = pir[pir["ANIO"].isin(anios_pir)]
        cm.grafico(titulo, gr.piramide(mostrada), texto, "a_perfil_piramide", cp.ayuda("piramide"),
                   tabla=cm.tabla_humana(mostrada[["ANIO", "GRUPO_EDAD", "SEXO", "episodios", "pct"]]))
    with mosaico:
        r = d["regiones"]
        _por_anio(r[r["ANIO"].isin(vistos)], "region", p, n, pocos, "Región de residencia (% de egresos)", "region_paciente",
                  "a_perfil_region", ("region", "pct"), "Región de residencia")

    _bloque("Por qué ingresan")
    cm.capitulos(caps[caps["ANIO"].isin(vistos)], p, n, pocos, key="a_perfil_capitulos")

    _bloque("Cuán complejos")
    _complejidad(d, p)


def _pestana_comorbilidad(sel: Seleccion, p: ind.Periodo) -> None:
    """Sub-pestaña Comorbilidad: el selector de enfermedades, su propia línea de lectura y los gráficos."""
    st.caption(tx.GLOSARIO["comorbilidad"])
    elegidas = _elegir_cronicas()
    resumen = st.container()  # la frase sale del cálculo, que se hace al dibujar los gráficos
    texto = _bloque_comorbilidad(sel, p, elegidas)
    with resumen:
        cp.lectura(texto or "", key="resumen_comorbilidad")


# ---------- 3 · Peso GRD ----------

@st.cache_data(max_entries=32)
def _peso(clave: tuple, anios: tuple) -> dict:
    """Pareto de GRD y cuadrante por capítulo de cada año pedido, y los GRD del 50 % con los 7 años y todos los tipos."""
    s = cm.desde_clave(clave)
    todos = datos.anios_disponibles()
    grd = datos.filtrar(datos.cargar("grd"), s, todos)
    del_tipo = grd[grd["TIPO_GRD"].isin(TIPOS_GRD.get(s.tipo, []))]
    perf = datos.filtrar(datos.cargar("perfil"), s, list(anios))
    perf = perf.assign(CAPITULO_CIE10=perf["CAPITULO_CIE10"].astype(str).map(tx.etiqueta_capitulo))
    return {"pareto": {a: ind.pareto(del_tipo[del_tipo["ANIO"] == a]) for a in anios},
            "cuadrante": {a: ind.cuadrante(perf[perf["ANIO"] == a]) for a in anios},
            "n_eda": ind.n_grd_para(ind.pareto(grd), 0.5), "rango": (todos[0], todos[-1])}


def _brecha(cu: pd.DataFrame) -> pd.Series:
    """Diferencia % del peso − % de episodios por capítulo."""
    c = cu.set_index("CAPITULO_CIE10")
    return c["pct_peso"] - c["pct_episodios"]


def pregunta_peso(sel: Seleccion, p: ind.Periodo) -> None:
    """Peso GRD: cómo se reparte el peso GRD entre GRD y capítulos, en el período elegido."""
    caja = _encabezado("¿Cómo se reparte el peso GRD?")
    s = _sel(sel, region=sel.region)
    anios = (p.foco,) if p.modo == "un_anio" else (p.base, p.foco)
    d = _peso(cm.clave(s), anios)
    par, cu = d["pareto"][p.foco], d["cuadrante"][p.foco]
    if par["peso_total"].sum() <= 0 or cu.empty:
        caja.info(f"No hay peso GRD con esta selección en {p.foco}.")
        return
    comparar = p.modo == "comparar" and d["pareto"][p.base]["peso_total"].sum() > 0
    q = p if comparar else ind.Periodo("un_anio", p.foco, p.base)
    n, total, tipo = ind.n_grd_para(par, 0.5), int((par["peso_total"] > 0).sum()), s.tipo.lower()
    n_base = ind.n_grd_para(d["pareto"][p.base], 0.5) if comparar else None
    top = cu.loc[_brecha(cu).reset_index(drop=True).idxmax()]
    cap = tx.capitulo_corto(str(top["CAPITULO_CIE10"]))
    capitulo = (f"{cap[0].upper() + cap[1:]} es el capítulo con mayor diferencia entre peso GRD y egresos: {tx.numero(top['pct_peso'], 1)} % "
                f"del peso GRD con {tx.numero(top['pct_episodios'], 1)} % de los egresos.")
    if comparar:
        resumen = (f"Para sumar la mitad del peso GRD de {tipo} hacían falta {tx.numero(n_base)} GRD en "
                   f"{p.base} y {tx.numero(n)} GRD en {p.foco}, de {tx.numero(total)} con peso. " + capitulo)
    else:
        resumen = (f"La mitad del peso GRD de {tipo} de {p.foco} está en {tx.numero(n)} GRD, de "
                   f"{tx.numero(total)} con peso. " + capitulo)
    with caja:
        cp.lectura(resumen, key="resumen_peso")
    mosaico = cp.mosaico("p4")
    with mosaico:
        cm.grafico(f"Pareto de GRD ({p.foco})", gr.pareto_fig(par, BARRAS_PARETO),
                   tx.lectura("pareto", q, n_grd=n, pct=50.0, n_base=n_base), "a_p4_pareto", cp.ayuda("pareto"),
                   (f"Se muestran los {tx.numero(min(BARRAS_PARETO, len(par)))} GRD con más peso GRD total (eje izquierdo); "
                    "la curva acumulada usa todos (eje derecho).",),
                   tabla=cm.tabla_humana(par.head(BARRAS_PARETO).assign(COD_GRD=lambda x: x["COD_GRD"].astype(str))[["COD_GRD", "DESCRIPCION_GRD", "peso_total", "pct", "pct_acum"]],
                                         {"COD_GRD": "Código GRD", "DESCRIPCION_GRD": "GRD", "peso_total": "Peso GRD total",
                                          "pct": "% del peso GRD", "pct_acum": "% acumulado"}))
    with mosaico:
        dif = _brecha(cu)
        if comparar:
            antes = _brecha(d["cuadrante"][p.base])
            dif = (dif - antes).dropna()
        cap, v = cm.mayor_cambio(dif) or ("—", 0.0)
        if comparar and cap in antes.index:  # «se amplió» o «se redujo»: cambio del tamaño de la brecha
            v = abs(float(_brecha(cu)[cap])) - abs(float(antes[cap]))
        corto = cu.assign(CAPITULO_CIE10=cu["CAPITULO_CIE10"].str.split(".").str[0])
        cm.grafico(f"Cuadrante volumen vs peso GRD por capítulo ({p.foco})", gr.cuadrante_fig(corto),
                   tx.lectura("cuadrante", q, capitulo=cap, dif=v), "a_p4_cuadrante", cp.ayuda("cuadrante"),
                   tabla=cm.tabla_humana(cu, {"CAPITULO_CIE10": "Capítulo CIE-10", "pct_episodios": "% de los egresos",
                                              "pct_peso": "% del peso GRD"}))
    a0, a1 = d["rango"]
    _cierre("Peso GRD", "El peso GRD es un peso relativo (1 = episodio promedio de referencia); no son pesos chilenos ni un monto de dinero.",
            "Pareto: GRD del tipo de atención elegido (hospitalización MH/PH, ambulatorio MA/PA) ordenados de mayor a menor "
            "Σ peso GRD, con su % acumulado; la respuesta cuenta cuántos GRD hacen falta para llegar al 50 %. Cuadrante: para "
            "cada capítulo, % de los episodios vs % del peso GRD; sobre la diagonal, el capítulo tiene más % del peso GRD que % de los episodios."
            f"\n\nNota del EDA: con los 7 años juntos ({a0}–{a1}) y todos los tipos de atención, "
            f"{tx.numero(d['n_eda'])} GRD explican el 50 % del peso GRD (con la región y el panel elegidos).",
            "tablas `grd` (Pareto) y `perfil` (cuadrante)")


# ---------- 4 · Territorio ----------

@st.cache_data(max_entries=32)
def _territorio(tipo: str, foco: int, origen: str | None) -> dict:
    """% atendido fuera de la región del paciente (egresos y peso) y principales flujos entre regiones."""
    f = datos.filtrar(datos.cargar("flujos"), Seleccion([foco], tipo, False)).astype({"REGION_PACIENTE": str, "REGION_HOSPITAL": str})
    r = ind.fuera_de_region(f)
    peso = f.assign(REGION_PACIENTE=f["REGION_PACIENTE"].fillna(SIN_REGION)).groupby("REGION_PACIENTE")["peso_total"].sum()
    r = r.assign(peso_total=r["REGION_PACIENTE"].map(peso))
    fuera = f[f["REGION_PACIENTE"].notna() & f["REGION_HOSPITAL"].notna() & (f["REGION_PACIENTE"] != f["REGION_HOSPITAL"])]
    if origen:
        fuera = fuera[fuera["REGION_PACIENTE"] == origen]
    flujos = fuera.groupby(["REGION_PACIENTE", "REGION_HOSPITAL"])["episodios"].sum().nlargest(10).reset_index()
    return {"regiones": r, "flujos": flujos.assign(flujo=flujos["REGION_PACIENTE"] + " → " + flujos["REGION_HOSPITAL"])}


def _pct_fuera(r: pd.DataFrame) -> tuple[float, float]:
    """% de egresos y de peso atendidos fuera de la región sobre el total de las filas (incluye «Sin región»)."""
    ep = (r["pct_fuera_episodios"].fillna(0) * r["episodios"]).sum() / r["episodios"].sum()
    peso = (r["pct_fuera_peso"].fillna(0) * r["peso_total"]).sum() / r["peso_total"].sum()
    return float(ep), float(peso)


def pregunta_territorio(sel: Seleccion, p: ind.Periodo) -> None:
    """Territorio: egresos de cada región de origen atendidos fuera de su región, en egresos y en peso GRD."""
    caja = _encabezado("¿Qué regiones tienen más egresos atendidos fuera de su región?")
    origen = _region_paciente("p5_region")
    d = _territorio(sel.tipo, p.foco, origen)
    b = _territorio(sel.tipo, p.base, origen)["regiones"] if p.modo == "comparar" else None
    r = d["regiones"]
    if r.empty or r["episodios"].sum() == 0:
        caja.info(f"No hay egresos con esta selección en {p.foco}.")
        return
    enmascarada = ind.enmascarar(r[r["REGION_PACIENTE"] != SIN_REGION])
    rank = enmascarada[~enmascarada["oculta"]].sort_values("pct_fuera_episodios")
    ocultas = bool(enmascarada["oculta"].any())
    if origen:
        o = r[r["REGION_PACIENTE"] == origen]
        ep, peso = _pct_fuera(o) if not o.empty else (0.0, 0.0)
        destino = f". El destino principal es {d['flujos'].iloc[0]['REGION_HOSPITAL']}" if len(d["flujos"]) else ""
        ob = b[b["REGION_PACIENTE"] == origen] if b is not None else pd.DataFrame()
        antes = f" ({tx.numero(_pct_fuera(ob)[0], 1)} % en {p.base})" if not ob.empty and ob["episodios"].sum() > 0 else ""
        resumen = (f"El {tx.numero(ep, 1)} % de los egresos de residentes de {origen} fue en un hospital de otra región en "
                   f"{p.foco}{antes}, y ese grupo suma el {tx.numero(peso, 1)} % de su peso GRD{destino}.")
    else:
        ep, peso = _pct_fuera(r)
        tops = [f"{x.REGION_PACIENTE} ({tx.numero(x.pct_fuera_episodios, 1)} %)" for x in rank.tail(3)[::-1].itertuples()]
        tops = tops[0] if len(tops) == 1 else ", ".join(tops[:-1]) + " y " + tops[-1]
        antes = f" ({tx.numero(_pct_fuera(b)[0], 1)} % en {p.base})" if b is not None and b["episodios"].sum() > 0 else ""
        resumen = (f"El {tx.numero(ep, 1)} % de los egresos de {p.foco} fue en un hospital de otra región que la del "
                   f"paciente{antes} y suma el {tx.numero(peso, 1)} % del peso GRD. Las regiones de origen con mayor % "
                   f"fuera de su región son {tops}.")
    with caja:
        cp.lectura(resumen, key="resumen_territorio")
    st.caption(f"Año {p.foco} · {sel.tipo.capitalize()}. Los egresos sin región conocida cuentan en los totales, no en el "
               "ranking. El interruptor del panel no se aplica aquí: la tabla `flujos` no distingue el panel.")
    u = ind.Periodo("un_anio", p.foco, None)
    mosaico = cp.mosaico("p5")
    with mosaico:
        largo = rank.melt(id_vars="REGION_PACIENTE", value_vars=["pct_fuera_episodios", "pct_fuera_peso"], var_name="medida",
                          value_name="pct")
        largo["medida"] = largo["medida"].map({"pct_fuera_episodios": "% de egresos", "pct_fuera_peso": "% del peso GRD"})
        # un solo año, dos medidas: % de egresos como base (gris) y % del peso GRD como foco (énfasis), con la diferencia
        fig = gr.barras_base_foco(largo, "REGION_PACIENTE", "pct", "medida", "% de egresos", "% del peso GRD")
        fig.update_yaxes(categoryorder="array", categoryarray=list(rank["REGION_PACIENTE"]))
        cm.grafico("Atendido fuera de la región del paciente (%)", fig, tx.lectura("fuera_region", u, pct=_pct_fuera(r)[0]),
                   "a_p5_fuera", cp.ayuda("barras_base_foco"), (cm.AVISO_CELDAS,) if ocultas else (),
                   tabla=cm.tabla_humana(enmascarada.sort_values("pct_fuera_episodios", ascending=False),
                                         {"episodios": "Egresos", "pct_fuera_episodios": "% de egresos fuera de su región",
                                          "pct_fuera_peso": "% del peso GRD fuera de su región"}))
    with mosaico:
        fl = d["flujos"]
        if fl.empty:
            st.markdown("No hay flujos hacia otras regiones con esta selección.")
        else:
            top = fl.iloc[0]
            cm.grafico("Principales flujos entre regiones (egresos)", gr.sankey(fl, "REGION_PACIENTE", "REGION_HOSPITAL", "episodios"),
                       tx.lectura("flujos", u, origen=top["REGION_PACIENTE"], destino=top["REGION_HOSPITAL"],
                                  valor=float(top["episodios"])), "a_p5_flujos", cp.ayuda("principales_flujos"),
                       tabla=cm.tabla_humana(fl[["REGION_PACIENTE", "REGION_HOSPITAL", "episodios"]],
                                             {"REGION_HOSPITAL": "Región del hospital"}))
    _cierre("Cobertura", "Solo hospitales públicos que informan GRD; las atenciones del sector privado no aparecen.",
            "% fuera de la región = egresos atendidos en un hospital de otra región ÷ egresos de las personas que viven en "
            "esa región × 100; lo mismo con el peso GRD. Si el % del peso supera al % de egresos, esos egresos tienen un peso GRD medio mayor que el promedio. "
            "Flujos: egresos por par región del paciente → región del hospital, sin contar los de la misma región.",
            "tabla `flujos`")


def main() -> None:
    """Arma la página Análisis con una pestaña por pregunta."""
    cm.encabezado("Análisis")
    sel = actual()
    p = ind.periodo(sel.anios, datos.anios_disponibles())
    with st.container(key="pestanas_analisis"):
        t = st.tabs(PESTANAS, key="a_pestana", on_change="rerun")  # la pestaña abierta decide qué filtros se apagan
    # Solo se calcula y dibuja la pestaña abierta: con las cuatro a la vez cada ejecución tardaba segundos en un equipo lento.
    for pestana, dibujar in zip(t, (lambda: pregunta_1(sel), lambda: pregunta_perfil(sel, p),
                                    lambda: pregunta_peso(sel, p), lambda: pregunta_territorio(sel, p))):
        if pestana.open:
            with pestana, st.container(key="graficos_analisis"):  # ancla del recorrido: resalta su primera tarjeta de gráfico
                dibujar()

main()
