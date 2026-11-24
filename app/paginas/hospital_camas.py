"""Hospitales › camas y ocupación del REM20 (DEIS-MINSAL): tarjetas, curva mensual y camas de lo general a lo específico
(por familia y, con una familia elegida, sus unidades) del hospital en vista.

El REM20 es otra fuente que los egresos GRD y cubre 2019–2025 aunque el hospital no informe GRD en un año; por eso la sección
sigue al hospital y al año foco y no depende de que haya egresos GRD. Las camas son de hospitalización: con «Ambulatorio»
elegido la sección se dibuja igual y lo dice. La ocupación es siempre Σ días-cama ocupados ÷ Σ disponibles (`indicadores.ocupacion`);
las filas del REM20 se usan como vienen, sin cortar las ocupaciones sobre 100 %. Un hospital cambia de áreas funcionales entre años:
nunca se asume una lista fija.
"""
import re

import pandas as pd
import streamlit as st

import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import textos as tx
from paginas import comun as cm
from paginas import hospital_actividad as ha
from paginas import hospital_perfil as hp
from seleccion import Seleccion

COLS_CAMAS = ("ANIO", "MES", "COD_HOSPITAL", "AREA_FUNCIONAL", "dias_cama_disponibles", "dias_cama_ocupados", "dias_estada",
              "egresos", "egresos_fallecidos", "traslados", "camas_promedio")
SIN_VALOR = "—"
NOTA_REM20 = "Camas y ocupación vienen del REM20 (DEIS-MINSAL)."
# Egresos REM20 ÷ egresos GRD de hospitalización del mismo hospital y año: desde 2020 la mediana es 1,000 y casi todos
# quedan a menos de 1 % (en 2025, los 76); en 2019 y en unos pocos hospitales de 2020–2023 difieren más.
TOLERANCIA_EGRESOS = 0.01
NOTA_RECONVERSION = ("En 2020 y 2021 muchos hospitales reconvirtieron camas por la pandemia; un cambio entre años también "
                     "puede ser un área que el REM20 registra con otro nombre.")
AYUDA_UNIDAD = "Área funcional del REM20, con su nombre completo; doble clic en la celda para leerlo entero en una pantalla angosta."
AVISO_SOBRE_100 = "Hay meses con más días-cama ocupados que disponibles; el REM20 lo registra así."


@st.cache_data(max_entries=32, show_spinner=False)
def camas_hospital(cod: str) -> pd.DataFrame:
    """Filas del REM20 del hospital (todos los años y áreas), con solo las columnas que usa la página."""
    c = datos.cargar("camas", COLS_CAMAS)
    c = c[c["COD_HOSPITAL"] == int(cod)]
    return c.assign(AREA_FUNCIONAL=c["AREA_FUNCIONAL"].astype(str)).reset_index(drop=True)


def _ocupacion_mensual(c: pd.DataFrame) -> pd.Series:
    """Ocupación (%) de cada (año, mes): suma de ocupados ÷ suma de disponibles de todas las áreas; vacío si no hay disponibles."""
    g = c.groupby(["ANIO", "MES"])[["dias_cama_disponibles", "dias_cama_ocupados"]].sum()
    return (g["dias_cama_ocupados"] / g["dias_cama_disponibles"].where(g["dias_cama_disponibles"] > 0) * 100).rename("ocupacion")


@st.cache_data(max_entries=32, show_spinner=False)
def serie_ocupacion(cod: str) -> pd.DataFrame:
    """Ocupación por mes de todos los años (`mes`, `ocupacion`); los meses sin filas o sin días-cama disponibles quedan vacíos."""
    anios = datos.anios_disponibles()
    por_mes = _ocupacion_mensual(camas_hospital(cod))
    por_mes.index = pd.DatetimeIndex(pd.to_datetime([f"{a}-{m:02d}-01" for a, m in por_mes.index]), name="mes")
    meses = pd.date_range(f"{anios[0]}-01-01", f"{anios[-1]}-12-01", freq="MS", name="mes")
    return por_mes.reindex(meses).reset_index()


def _nombre_unidad(area: str) -> str:
    """«Área Cuidados Intensivos Adultos» → «Cuidados Intensivos Adultos»: solo se quita el «Área» inicial."""
    s = re.sub(r"^Área (de )?", "", area.strip())
    return s[:1].upper() + s[1:]


# Familias de unidades: el nombre del área trae el servicio (o la población) y el nivel de cuidado. Las reglas se prueban en
# orden; la primera que calza decide. Psiquiatría va primero (sus unidades de cuidados intensivos son de psiquiatría) y
# cada nivel de cuidado crítico agrupa a adultos, pediátricos y neonatales: «Cuidados intensivos» son las UCI y «Cuidados
# intermedios», las UTI (el MINSAL llama camas críticas o UPC a las dos juntas); Neonatología conserva solo sus cuidados básicos. Lo que no calza (Pensionado,
# Sociosanitaria o un área nueva) va a «Otras».
FAMILIAS = ("Médico-quirúrgico", "Médica adulto", "Pediátrica", "Obstetricia", "Neonatología", "Cuidados intermedios",
            "Cuidados intensivos", "Psiquiatría", "Otras")
_REGLAS_FAMILIA = (("psiquiatr", "Psiquiatría"), ("cuidados intensivos", "Cuidados intensivos"),
                   ("cuidados intermedios", "Cuidados intermedios"), ("neonatolog", "Neonatología"), ("pediátric", "Pediátrica"),
                   ("médico-quirúrgic", "Médico-quirúrgico"), ("médica adulto", "Médica adulto"), ("obstetricia", "Obstetricia"))
# Lo que se quita del nombre corto de una unidad cuando va bajo el rótulo de su familia (se lee junto a él).
_PREFIJO_FAMILIA = {"Pediátrica": r"\bpediátric[ao]s?\b", "Cuidados intensivos": r"^cuidados intensivos\b",
                    "Cuidados intermedios": r"^cuidados intermedios\b"}
OTRAS_UNIDADES = "Otras unidades"
MAX_LINEAS_UNIDAD = 8  # más unidades que esto: las más chicas se juntan en «Otras unidades» (solo en la ocupación mensual)
# Selector del nivel específico: la vista general (sin familia elegida) muestra solo los gráficos por familia
TODAS_FAMILIAS = "Todas las familias"
CLAVE_FAMILIA = "hosp_camas_familia"
# Un color propio por familia, el mismo en todos los gráficos de Camas (barras y líneas); nunca el fucsia del hospital.
COLOR_FAMILIA = dict(zip(FAMILIAS, gr.PALETA_CAMAS))


def familia_unidad(area: str) -> str:
    """Familia de un área funcional del REM20 («Área Neonatología Cuidados Básicos» → «Neonatología»); «Otras» si no calza."""
    s = area.lower()
    return next((familia for patron, familia in _REGLAS_FAMILIA if patron in s), "Otras")


def nombre_corto_unidad(area: str) -> str:
    """Nombre corto de una unidad, en minúscula salvo la inicial, sin «Área» ni «de Hospitalización de».

    «Área de Hospitalización de Cuidados Intensivos en Psiquiatría Adulto» → «Psiquiatría adulto cuidados intensivos». Solo
    se acorta lo que no distingue una unidad de otra; el nombre completo queda en el hover y en la tabla.
    """
    s = re.sub(r"^Hospitalización de ", "", _nombre_unidad(area))
    s = re.sub(r"^Cuidados Intensivos en (Psiquiatría) (.+)$", r"\1 \2 cuidados intensivos", s)
    s = re.sub(r"Infanto[ -]adolescente", "infanto-adolescente", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+evaluación e inicio tto\.?$", " evaluación e inicio", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s[:1].upper() + s[1:]


def _etiqueta_en_familia(corto: str, familia: str) -> str:
    """Rótulo de una unidad bajo el de su familia: sin repetir la familia («Médico-quirúrgico cuidados medios» → «Cuidados medios»)."""
    patron = _PREFIJO_FAMILIA.get(familia, "^" + re.escape(familia.lower()) + r"\b")
    s = re.sub(r"\s+", " ", re.sub(patron, "", corto.lower())).strip()
    return s[:1].upper() + s[1:] if s else corto


def unidades_de(c: pd.DataFrame) -> pd.DataFrame:
    """Una fila por unidad (área funcional) de las filas `c` de un hospital y un año.

    Columnas: `area` (nombre sin «Área»), `familia`, `corto`, `camas`, `ocupacion`, `egresos`, `estancia` y los días-cama.
    Las camas de cada unidad son la suma de sus camas mensuales ÷ los meses informados por el hospital, así las unidades suman las
    camas promedio del hospital aunque una unidad falte algunos meses. La ocupación queda vacía si la unidad no tiene días-cama
    disponibles y la estancia (días de estada ÷ egresos) si no tiene egresos. Ordenada por camas (de más a menos).
    """
    meses = c[["ANIO", "MES"]].drop_duplicates().shape[0]
    u = c.assign(area=c["AREA_FUNCIONAL"].astype(str).map(_nombre_unidad)).groupby("area")[
        ["camas_promedio", "dias_cama_disponibles", "dias_cama_ocupados", "egresos", "dias_estada"]].sum()
    u = u.assign(camas=u["camas_promedio"] / max(meses, 1),
                 ocupacion=u["dias_cama_ocupados"] / u["dias_cama_disponibles"].where(u["dias_cama_disponibles"] > 0) * 100,
                 estancia=u["dias_estada"] / u["egresos"].where(u["egresos"] > 0))
    u = u.reset_index().sort_values(["camas", "area"], ascending=[False, True])
    u = u.assign(familia=u["area"].map(familia_unidad), corto=u["area"].map(nombre_corto_unidad))
    return u[["area", "familia", "corto", "camas", "ocupacion", "egresos", "estancia", "dias_cama_disponibles",
              "dias_cama_ocupados", "dias_estada"]].reset_index(drop=True)


def familias_de(u: pd.DataFrame) -> pd.DataFrame:
    """Una fila por familia de las unidades `u` (de `unidades_de`): `familia`, `unidades`, `camas`, `ocupacion`, `egresos`,
    `estancia` y los días-cama.

    Suma las unidades de cada familia: las familias suman las camas promedio del hospital. La ocupación es Σ ocupados ÷
    Σ disponibles de sus unidades (vacía sin disponibles). Solo las familias con camas en el año (una familia cuyas filas
    traen 0 camas no se muestra ni se ofrece en el selector); de más a menos camas.
    """
    f = u.groupby("familia").agg(unidades=("area", "size"), camas=("camas", "sum"), egresos=("egresos", "sum"),
                                 dias_estada=("dias_estada", "sum"), dias_cama_disponibles=("dias_cama_disponibles", "sum"),
                                 dias_cama_ocupados=("dias_cama_ocupados", "sum"))
    f = f.assign(ocupacion=f["dias_cama_ocupados"] / f["dias_cama_disponibles"].where(f["dias_cama_disponibles"] > 0) * 100,
                 estancia=f["dias_estada"] / f["egresos"].where(f["egresos"] > 0))
    f = f[f["camas"] > 0].reset_index().sort_values(["camas", "familia"], ascending=[False, True])
    return f[["familia", "unidades", "camas", "ocupacion", "egresos", "estancia", "dias_cama_disponibles",
              "dias_cama_ocupados"]].reset_index(drop=True)


def familias(cod: str, anio: int) -> pd.DataFrame:
    """Familias del hospital en un año (ver `familias_de`)."""
    return familias_de(unidades(cod, anio))


def unidades_de_familia(u: pd.DataFrame, familia: str) -> pd.DataFrame:
    """Las unidades `u` de una familia, en el mismo orden (de más a menos camas)."""
    return u[u["familia"] == familia].reset_index(drop=True)


def opciones_familia(f: pd.DataFrame) -> list[str]:
    """Opciones del selector: la vista general y luego las familias con camas en el año, de más a menos camas."""
    return [TODAS_FAMILIAS, *f["familia"]]


def _hover_familia(r) -> str:
    estancia = SIN_VALOR if pd.isna(r["estancia"]) else f"{tx.numero(r['estancia'], 1)} días"
    return (f"<b>{r['familia']}</b><br>Unidades: {int(r['unidades'])}<br>Camas disponibles (promedio): {tx.numero(r['camas'], 1)}<br>"
            f"Ocupación: {_porcentaje(r['ocupacion'])}<br>Egresos: {tx.numero(int(r['egresos']), 0)}<br>Estancia media: {estancia}")


def filas_familias(f: pd.DataFrame) -> pd.DataFrame:
    """Filas del gráfico por familia (mismo formato que `filas_unidades`): una barra por familia en su color, sin rótulos
    de grupo."""
    filas = pd.DataFrame({"clave": f["familia"], "etiqueta": f["familia"], "familia": False, "camas": f["camas"].astype(float),
                          "color": f["familia"].map(COLOR_FAMILIA),
                          "ocupacion": pd.to_numeric(f["ocupacion"], errors="coerce"),
                          "hover": [_hover_familia(r) for _, r in f.iterrows()]})
    return filas.assign(familia=filas["familia"].astype(bool)).reset_index(drop=True)


def tabla_familias(f: pd.DataFrame) -> pd.DataFrame:
    """Tabla del gráfico por familia: familia, número de unidades, camas, ocupación en texto («—» sin días-cama) y egresos."""
    return pd.DataFrame({"Familia": f["familia"], "Unidades": f["unidades"].astype(int), "Camas disponibles": f["camas"].astype(float),
                         "Ocupación": [_porcentaje(v) for v in f["ocupacion"]], "Egresos": f["egresos"].astype(int)})


def _por_familia(u: pd.DataFrame) -> pd.DataFrame:
    """Las unidades en el orden de `FAMILIAS` y, dentro de cada familia, de más a menos camas."""
    return (u.assign(_f=u["familia"].map(FAMILIAS.index)).sort_values(["_f", "camas", "area"], ascending=[True, False, True])
            .drop(columns="_f").reset_index(drop=True))


def _hover_unidad(r) -> str:
    estancia = SIN_VALOR if pd.isna(r["estancia"]) else f"{tx.numero(r['estancia'], 1)} días"
    return (f"<b>{r['area']}</b><br>{r['familia']}<br>Camas disponibles (promedio): {tx.numero(r['camas'], 1)}<br>"
            f"Ocupación: {_porcentaje(r['ocupacion'])}<br>Egresos: {tx.numero(int(r['egresos']), 0)}<br>Estancia media: {estancia}")


def filas_unidades(u: pd.DataFrame, rotulos: bool = True) -> pd.DataFrame:
    """Filas del gráfico de unidades, de arriba abajo: el rótulo de cada familia con más de una unidad y luego sus unidades.

    Bajo el rótulo de su familia, una unidad no repite la familia; una familia de una sola unidad no lleva rótulo propio.
    Con `rotulos=False` (las unidades de una sola familia, que ya va en el título) no hay filas de rótulo, y las unidades
    igual se nombran sin repetir la familia.
    """
    filas = []
    for familia, g in _por_familia(u).groupby("familia", sort=False):
        varias = len(g) > 1
        if varias and rotulos:
            filas.append({"clave": f"§{familia}", "etiqueta": familia, "familia": True, "camas": 0.0, "ocupacion": None,
                          "hover": ""})
        for _, r in g.iterrows():
            filas.append({"clave": r["area"], "etiqueta": _etiqueta_en_familia(r["corto"], familia) if varias else r["corto"],
                          "familia": False, "camas": float(r["camas"]), "ocupacion": r["ocupacion"], "hover": _hover_unidad(r)})
    f = pd.DataFrame(filas, columns=["clave", "etiqueta", "familia", "camas", "ocupacion", "hover"])
    return f.assign(ocupacion=pd.to_numeric(f["ocupacion"], errors="coerce"), familia=f["familia"].astype(bool))


@st.cache_data(max_entries=32, show_spinner=False)
def evolucion_familias(cod: str) -> pd.DataFrame:
    """Camas promedio por familia y año (`ANIO`, `familia`, `camas`) en todos los años de los datos.

    Cada año suma sus unidades (que cambian entre años); una familia sin filas en un año cuenta 0, y un año sin filas del
    REM20 también. Solo las familias que el hospital tuvo algún año, en el orden de `FAMILIAS`.
    """
    c = camas_hospital(cod)
    anios = datos.anios_disponibles()
    por_anio = {a: unidades_de(g).groupby("familia")["camas"].sum() for a, g in c.groupby("ANIO")}
    t = pd.DataFrame(por_anio).T if por_anio else pd.DataFrame()
    t = t.reindex(index=anios, columns=[f for f in FAMILIAS if f in t.columns]).fillna(0.0)
    return t.rename_axis(index="ANIO", columns="familia").stack().rename("camas").reset_index()


def _etiquetas_en_familia(u: pd.DataFrame, familia: str) -> dict[str, str]:
    """Área → rótulo de la unidad sin repetir su familia; si dos rótulos chocaran, el nombre corto completo de todas."""
    et = {a: _etiqueta_en_familia(c, familia) for a, c in zip(u["area"], u["corto"])}
    return et if len(set(et.values())) == len(et) else dict(zip(u["area"], u["corto"]))


@st.cache_data(max_entries=64, show_spinner=False)
def evolucion_unidades(cod: str, familia: str) -> pd.DataFrame:
    """Camas promedio de las unidades de una familia por año (`ANIO`, `unidad`, `camas`) en todos los años de los datos.

    Como `evolucion_familias`, pero dentro de una familia: cada unidad que la familia tuvo algún año, con 0 en los años
    sin ella (o sin REM20). `unidad` es el rótulo sin repetir la familia; de más a menos camas en todo el período.
    """
    c = camas_hospital(cod)
    anios = datos.anios_disponibles()
    u = pd.concat([unidades_de(g).assign(ANIO=a) for a, g in c.groupby("ANIO")]) if not c.empty else pd.DataFrame(
        columns=["ANIO", "area", "corto", "familia", "camas"])
    u = u[u["familia"] == familia]
    nombres = _etiquetas_en_familia(u.drop_duplicates("area"), familia)
    orden = list(u.groupby("area")["camas"].sum().sort_values(ascending=False, kind="stable").index)
    t = u.pivot_table(index="ANIO", columns="area", values="camas", aggfunc="sum").reindex(index=anios, columns=orden)
    t = t.fillna(0.0).rename(columns=nombres)
    return t.rename_axis(index="ANIO", columns="unidad").stack().rename("camas").reset_index()


def _unidades_por_anio(cod: str, familia: str) -> pd.DataFrame:
    c = camas_hospital(cod)
    c = c[c["AREA_FUNCIONAL"].map(familia_unidad) == familia]
    if c.empty:
        return pd.DataFrame(columns=["ANIO", "area", "corto", "familia", "camas"])
    return pd.concat([unidades_de(g).assign(ANIO=a) for a, g in c.groupby("ANIO")], ignore_index=True)


@st.cache_data(max_entries=64, show_spinner=False)
def colores_unidades(cod: str, familia: str) -> tuple[dict[str, str], dict[str, str]]:
    """Un color propio por unidad de la familia (de `PALETA_CAMAS`, de más a menos camas en todo el período), el mismo en
    sus barras, su evolución y su ocupación mensual: (área → color, rótulo → color). El rótulo cubre los nombres que usan
    los gráficos de líneas en cualquier año; «Otras unidades» toma el color siguiente."""
    u = _unidades_por_anio(cod, familia)
    orden = list(u.groupby("area")["camas"].sum().sort_values(ascending=False, kind="stable").index) if len(u) else []
    por_area = {a: gr.PALETA_CAMAS[i % len(gr.PALETA_CAMAS)] for i, a in enumerate(orden)}
    por_rotulo = {}
    grupos = ([u.drop_duplicates("area")] + [g for _, g in u.groupby("ANIO")]) if len(u) else []
    for g in grupos:
        for area, rotulo in _etiquetas_en_familia(g, familia).items():
            por_rotulo.setdefault(rotulo, por_area[area])
    por_rotulo[OTRAS_UNIDADES] = gr.PALETA_CAMAS[len(orden) % len(gr.PALETA_CAMAS)]
    return por_area, por_rotulo


def lectura_evolucion(e: pd.DataFrame, columna: str = "familia") -> str:
    """«Entre 2019 y 2025, la familia que más cambió fue Cuidados intensivos: de 43 a 68 camas.» (solo cifras).

    `columna` es «familia» (camas por familia) o «unidad» (las unidades de una familia).
    """
    con = e.groupby("ANIO")["camas"].sum()
    con = con[con > 0]
    if len(con) < 2:
        return ("El REM20 trae camas de este hospital en un solo año." if columna == "familia"
                else "El REM20 trae camas de esta familia en un solo año.")
    a0, a1 = int(con.index.min()), int(con.index.max())
    t = e.pivot_table(index=columna, columns="ANIO", values="camas", aggfunc="sum")
    cambio = (t[a1] - t[a0]).abs()
    if cambio.max() < 0.5:
        return f"Entre {a0} y {a1}, las camas de cada {columna} quedan en cifras parecidas."
    f = cambio.idxmax()
    return (f"Entre {a0} y {a1}, la {columna} que más cambió fue {f}: de {tx.numero(t.loc[f, a0], 0)} a "
            f"{tx.numero(t.loc[f, a1], 0)} camas.")


def ocupacion_unidad_mes(cod: str, anio: int, familia: str | None = None) -> pd.DataFrame:
    """Ocupación por unidad y mes del año (`fila`, `MES`, días-cama, `ocupacion`), con los 12 meses siempre.

    `fila` es categórica en el orden de las barras de unidades. Con `familia`, solo sus unidades y con el rótulo que no
    repite la familia (como en sus barras). Con más de `MAX_LINEAS_UNIDAD` unidades, las más chicas (por camas) se juntan en
    «Otras unidades» sumando sus días-cama. Un mes sin días-cama disponibles queda vacío.
    """
    c = camas_hospital(cod)
    c = c[c["ANIO"] == anio]
    if familia is not None:
        c = c[c["AREA_FUNCIONAL"].map(familia_unidad) == familia]
    u = _por_familia(unidades_de(c))
    nombre = dict(zip(u["area"], u["corto"])) if familia is None else _etiquetas_en_familia(u, familia)
    if len(u) > MAX_LINEAS_UNIDAD:
        grandes = set(u.nlargest(MAX_LINEAS_UNIDAD - 1, "camas")["area"])
        nombre = {a: (n if a in grandes else OTRAS_UNIDADES) for a, n in nombre.items()}
    orden = list(dict.fromkeys(nombre[a] for a in u["area"] if nombre[a] != OTRAS_UNIDADES))
    orden += [OTRAS_UNIDADES] if OTRAS_UNIDADES in nombre.values() else []
    fila = c["AREA_FUNCIONAL"].astype(str).map(_nombre_unidad).map(nombre)
    g = c.assign(fila=fila).groupby(["fila", "MES"])[["dias_cama_disponibles", "dias_cama_ocupados"]].sum()
    g = g.reindex(pd.MultiIndex.from_product([orden, range(1, 13)], names=["fila", "MES"])).reset_index()
    g = g.assign(ocupacion=g["dias_cama_ocupados"] / g["dias_cama_disponibles"].where(g["dias_cama_disponibles"] > 0) * 100)
    return g.assign(fila=pd.Categorical(g["fila"], categories=orden, ordered=True))


def unidades(cod: str, anio: int) -> pd.DataFrame:
    """Unidades del hospital en un año (ver `unidades_de`)."""
    c = camas_hospital(cod)
    return unidades_de(c[c["ANIO"] == anio])


def _porcentaje(v: float | None, dec: int = 1) -> str:
    return SIN_VALOR if v is None or pd.isna(v) else f"{tx.numero(v, dec)} %"


def tabla_unidades(u: pd.DataFrame) -> pd.DataFrame:
    """Tabla que se ve: nombre de la unidad, camas (número), ocupación en texto («—» si no hay días-cama) y egresos."""
    return pd.DataFrame({"Unidad": u["area"], "Camas disponibles": u["camas"].astype(float),
                         "Ocupación": [_porcentaje(v) for v in u["ocupacion"]], "Egresos": u["egresos"].astype(int)})


def _valores(c: pd.DataFrame) -> dict:
    """Los indicadores de las filas `c` (un hospital y un año): camas disponibles (promedio), ocupación, rotación, traslados
    internos y egresos."""
    return {"camas": ind.camas_promedio(c), "ocupacion": ind.ocupacion(c), "rotacion": ind.rotacion(c),
            "traslados": int(c["traslados"].sum()), "egresos": int(c["egresos"].sum())}


def nota_fuente(egresos_rem: int, egresos_grd: int, anio: int) -> str:
    """Nota de fuente con lo que dicen los datos de ese hospital y año: si sus egresos del REM20 coinciden con los GRD de
    hospitalización (diferencia de 1 % o menos), si difieren (con las dos cifras) o si el hospital no informa GRD ese año."""
    if egresos_grd == 0:
        return f"{NOTA_REM20} En {anio} este hospital no informa GRD: el REM20 es la única fuente de ese año."
    if egresos_rem and abs(egresos_rem / egresos_grd - 1) <= TOLERANCIA_EGRESOS:
        return f"{NOTA_REM20} En {anio} sus egresos coinciden con los GRD de hospitalización del hospital."
    return (f"{NOTA_REM20} En {anio} sus egresos ({tx.numero(egresos_rem)}) no coinciden del todo con los GRD de "
            f"hospitalización del hospital ({tx.numero(egresos_grd)}).")


def _variacion(f: dict, b: dict | None, clave: str, tipo: str) -> ind.Variacion:
    """Variación del año foco frente a la base; sin base o sin valor en alguno de los dos años no hay comparación."""
    if b is None or f[clave] is None or b[clave] is None:
        return ind.Variacion("", "neutro", False)
    return ind.variacion(f[clave], b[clave], tipo, "neutro", b["egresos"])


def _tarjetas(f: dict, b: dict | None, foco: int, base: int | None) -> None:
    """Rotación y traslados internos. Las camas disponibles y la ocupación del año ya están en «En cifras» (y la ocupación
    frente al año base, en la lectura de la curva); la letalidad del REM20 no va porque repite la mortalidad GRD."""
    with cp.fila("fpar", "hosp_camas_kpi"):
        cp.tarjeta_kpi("Rotación", SIN_VALOR if f["rotacion"] is None else tx.numero(f["rotacion"], 1),
                       _variacion(f, b, "rotacion", "valor"), cp.ayuda("rotacion"))
        cp.tarjeta_kpi("Traslados internos", tx.numero(f["traslados"], 0), _variacion(f, b, "traslados", "valor"),
                       cp.ayuda("traslados"))
    if b is not None:
        st.caption(f"Rotación y traslados internos de {foco}; la variación, frente a {base}.")


def _lectura_curva(s: pd.DataFrame, foco: int, f: dict, b: dict | None, base: int | None) -> str:
    """«En 2025 estuvo ocupado el 79,3 % de los días-cama disponibles; …» (solo cifras, sin juicio)."""
    if f["ocupacion"] is None:
        return f"En {foco} el hospital no tiene días-cama disponibles registrados."
    texto = f"En {foco} estuvo ocupado el {tx.numero(f['ocupacion'], 1)} % de los días-cama disponibles"
    anio = s[(s["mes"].dt.year == foco) & s["ocupacion"].notna()]
    if not anio.empty:
        pico = anio.loc[anio["ocupacion"].idxmax()]
        texto += f"; el mes de mayor ocupación fue {tx.MESES[pico['mes'].month - 1]} ({tx.numero(pico['ocupacion'], 1)} %)"
    if b is not None and b["ocupacion"] is not None:
        texto += f", frente al {tx.numero(b['ocupacion'], 1)} % de {base}"
    return texto + "."


def _curva(cod: str, anios: list[int], p: ind.Periodo, f: dict, b: dict | None) -> None:
    """Ocupación mensual del hospital en los meses de los años elegidos, y solo esos (con un año, sus 12 meses)."""
    s = serie_ocupacion(cod)
    visibles = s[s["mes"].dt.year.isin(anios)]
    notas = ()
    if visibles["ocupacion"].isna().any():
        notas += ("Los meses sin línea son meses sin días-cama disponibles o sin datos del REM20.",)
    if (visibles["ocupacion"] > 100).any():
        notas += (AVISO_SOBRE_100,)
    titulo = tx.con_periodo("Ocupación mensual (%)", anios)
    tabla = cm.tabla_humana(visibles.assign(mes=visibles["mes"].dt.strftime("%m/%Y")), {"mes": "Mes", "ocupacion": "Ocupación (%)"})
    cm.grafico(titulo, gr.serie_meses(visibles, "ocupacion", anios, "Ocupación mensual", gr._C["primary"], 1, " %"), _lectura_curva(s, p.foco, f, b, p.base), "g_hosp_camas_ocupacion",
               cp.ayuda("curva_ocupacion"), notas, tabla=tabla)


COLUMNAS_TABLA_UNIDADES = {
    # sin ancho fijo: la columna toma el ancho del nombre más largo (hasta 500 px) y no lo corta; si la tabla no cabe, se
    # desplaza de lado y el nombre completo se ve también al hacer doble clic en la celda
    "Unidad": st.column_config.TextColumn("Unidad", help=AYUDA_UNIDAD),
    "Camas disponibles": st.column_config.NumberColumn("Camas disponibles", format="%.1f", width="small"),
    "Ocupación": st.column_config.TextColumn("Ocupación", width="small"),
    "Egresos": st.column_config.NumberColumn("Egresos", format="localized", width="small")}


def _lectura_mayor(nombre: str, que: str, camas: float, total: float, anio: int, de: str = "") -> str:
    """«La familia con más camas en 2025 es X: 323 de 763 (42 %).» (solo cifras)."""
    return (f"La {que} con más camas{de} en {anio} es {nombre}: {tx.numero(camas, 1)} de {tx.numero(total, 1)} "
            f"({tx.numero(camas / total * 100, 0)} %).")


def _notas_ocupacion(ocupacion: pd.Series, que: str) -> tuple[str, ...]:
    notas = ("A la derecha, la ocupación del año de cada barra.",)
    if ocupacion.isna().any():
        notas += (f"«—»: {que} sin días-cama disponibles en el año (su ocupación no se calcula).",)
    return notas


def _grafico_familias(f: pd.DataFrame, anio: int) -> None:
    """Nivel general con un año: camas por familia de ese año, cada familia en su color, con la ocupación del año escrita a
    la derecha."""
    texto = _lectura_mayor(f.iloc[0]["familia"], "familia", f.iloc[0]["camas"], float(f["camas"].sum()), anio)
    cm.grafico(tx.con_periodo("Camas por familia de unidades", [anio]), gr.barras_unidades(filas_familias(f)), texto,
               "g_hosp_camas_familias",
               cp.ayuda("camas_por_familia"), _notas_ocupacion(f["ocupacion"], "familias"), tabla=tabla_familias(f))


def _grafico_unidades(cod: str, u: pd.DataFrame, familia: str, anio: int) -> None:
    """Nivel específico con un año: camas de las unidades de la familia elegida, cada una en su color; la tabla con nombres
    completos en «Ver en tabla»."""
    total = float(u["camas"].sum())
    texto = (_lectura_mayor(u.iloc[0]["corto"], "unidad", u.iloc[0]["camas"], total, anio, f" de {familia}") if len(u) > 1
             else f"En {anio}, {familia} es una sola unidad: {u.iloc[0]['corto']}, con {tx.numero(total, 1)} camas.")
    por_area, _ = colores_unidades(cod, familia)
    filas = filas_unidades(u, rotulos=False)
    filas = filas.assign(color=filas["clave"].map(por_area).fillna(gr.PALETA_CAMAS[0]))
    cm.grafico(tx.con_periodo(f"Camas por unidad · {familia}", [anio]), gr.barras_unidades(filas), texto,
               "g_hosp_camas_unidades", cp.ayuda("camas_por_unidad"), _notas_ocupacion(u["ocupacion"], "unidades"),
               tabla=tabla_unidades(u), columnas_tabla=COLUMNAS_TABLA_UNIDADES)


def _notas_sin_anios(e: pd.DataFrame, de: str) -> tuple[str, ...]:
    sin = [str(a) for a, v in e.groupby("ANIO")["camas"].sum().items() if v == 0]
    return (f"El REM20 no trae camas {de} en {', '.join(sin)}.",) if sin else ()


def anios_parciales(cod: str) -> dict[int, int]:
    """Años en que el REM20 del hospital trae menos de 12 meses con días-cama disponibles → meses que trae (200717 en 2020
    trae 9). Las camas de ese año son el promedio de esos meses: en una evolución se lee como un salto que no existió."""
    c = camas_hospital(cod)
    meses = c[c["dias_cama_disponibles"] > 0].groupby("ANIO")["MES"].nunique()
    return {int(a): int(n) for a, n in meses.items() if 0 < n < 12}


def _notas_periodo(cod: str, anios) -> tuple[str, ...]:
    """Notas de una evolución de camas en los años que se ven: los años parciales del REM20 que caen ahí y la pandemia
    (o solo el cambio de nombre de un área, si 2020 y 2021 no se ven)."""
    pandemia = NOTA_RECONVERSION if {2020, 2021} & set(anios) else (
        "Un cambio entre años puede ser un área que el REM20 registra con otro nombre.")
    return nota_parciales(cod, anios) + (pandemia,)


def nota_parciales(cod: str, anios=None) -> tuple[str, ...]:
    """Nota de los años parciales del REM20 (vacía si todos sus años, o los de `anios`, traen los 12 meses)."""
    p = {a: n for a, n in anios_parciales(cod).items() if anios is None or a in anios}
    if not p:
        return ()
    detalle = " y ".join(f"{a} ({n} de 12 meses)" for a, n in sorted(p.items()))
    return (f"Año parcial del REM20: {detalle}; las camas de ese año son el promedio de los meses informados.",)


def orden_por_camas(e: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Las series de una evolución (`ANIO`, `columna`, `camas`) de más a menos camas en el período, «Otras…» al final: el
    orden en que las líneas toman los colores (las 4 más grandes, de la paleta; las demás, en gris)."""
    total = e.groupby(columna, sort=False)["camas"].sum()
    orden = sorted(total.index, key=lambda k: (str(k).startswith("Otras"), -total[k]))
    return e.assign(_o=e[columna].map({k: i for i, k in enumerate(orden)})).sort_values(["_o", "ANIO"]).drop(columns="_o")


def solo_anios(e: pd.DataFrame, anios, columna: str) -> pd.DataFrame:
    """La evolución (`ANIO`, `columna`, `camas`) en los años elegidos, sin las series que no tienen camas en ninguno."""
    e = e[e["ANIO"].isin(list(anios))]
    con = e.groupby(columna, sort=False)["camas"].sum()
    return e[e[columna].isin(con[con > 0].index)]


def _grafico_evolucion(cod: str, anios: tuple[int, ...]) -> None:
    """Nivel general con varios años: camas por familia en los años elegidos (solo esos), una línea sólida por familia en
    su color."""
    e = orden_por_camas(solo_anios(evolucion_familias(cod), anios, "familia"), "familia")
    if e.empty:
        st.caption(f"El REM20 no trae camas por unidad de este hospital en {tx.rotulo_periodo(anios)}.")
        return
    tabla = e.pivot_table(index="ANIO", columns="familia", values="camas", aggfunc="sum", sort=False).reset_index()
    cm.grafico(tx.con_periodo("Camas por familia de unidades", anios),
               gr.lineas_camas(e, "familia", colores=COLOR_FAMILIA),
               lectura_evolucion(e),
               "g_hosp_camas_evolucion", cp.ayuda("familia_unidad"), _notas_sin_anios(e, "de este hospital") + _notas_periodo(cod, anios),
               tabla=cm.tabla_humana(tabla.rename_axis(columns=None)))


def _grafico_evolucion_unidades(cod: str, familia: str, anios: tuple[int, ...]) -> None:
    """Nivel específico con varios años: camas de las unidades de la familia elegida en los años elegidos, una línea
    sólida por unidad en su color."""
    e = orden_por_camas(solo_anios(evolucion_unidades(cod, familia), anios, "unidad"), "unidad")
    if e.empty:
        st.caption(f"El REM20 no trae camas de {familia} en {tx.rotulo_periodo(anios)}.")
        return
    tabla = e.pivot_table(index="ANIO", columns="unidad", values="camas", aggfunc="sum", sort=False).reset_index()
    cm.grafico(tx.con_periodo(f"Camas por unidad · {familia}", anios),
               gr.lineas_camas(e, "unidad", colores=colores_unidades(cod, familia)[1]),
               lectura_evolucion(e, "unidad"), "g_hosp_camas_evolucion_unidades", cp.ayuda("camas_por_unidad"),
               _notas_sin_anios(e, f"de {familia} en este hospital") + _notas_periodo(cod, anios), tabla=cm.tabla_humana(tabla.rename_axis(columns=None)))


def _lectura_calor(m: pd.DataFrame, anio: int) -> str:
    v = m.dropna(subset=["ocupacion"])
    if v.empty:
        return f"En {anio} ninguna unidad tiene días-cama disponibles registrados."
    alto = v.loc[v["ocupacion"].idxmax()]
    return (f"En {anio}, la ocupación mensual más alta fue la de {alto['fila']} en {tx.MESES[int(alto['MES']) - 1]}: "
            f"{tx.numero(alto['ocupacion'], 1)} %.")


def _grafico_calor_periodo(cod: str, anios: tuple[int, ...], familia: str) -> None:
    """Nivel específico (C) con varios años: ocupación mensual por unidad en los meses de todos los años elegidos, con un
    corte entre años (misma clave `g_hosp_camas_calor`)."""
    m = pd.concat([ocupacion_unidad_mes(cod, a, familia).assign(ANIO=a) for a in anios], ignore_index=True)
    m = m.assign(fila=m["fila"].astype(str))
    notas = ("Cada año va con sus 12 meses; entre años elegidos que no son seguidos, la línea se corta.",)
    if m["ocupacion"].isna().any():
        notas += ("Los meses sin punto son meses sin días-cama disponibles en esa unidad o sin datos del REM20.",)
    if (m["ocupacion"] > 100).any():
        notas += (AVISO_SOBRE_100,)
    if OTRAS_UNIDADES in set(m["fila"]):
        notas += (f"«{OTRAS_UNIDADES}» junta las unidades con menos camas de cada año, sumando sus días-cama.",)
    v = m.dropna(subset=["ocupacion"])
    texto = (f"En {tx.rotulo_periodo(anios)}, la ocupación mensual más alta fue la de {v.loc[v['ocupacion'].idxmax(), 'fila']} "
             f"en {tx.MESES[int(v.loc[v['ocupacion'].idxmax(), 'MES']) - 1]} de {int(v.loc[v['ocupacion'].idxmax(), 'ANIO'])}: "
             f"{tx.numero(v['ocupacion'].max(), 1)} %." if not v.empty
             else f"En {tx.rotulo_periodo(anios)} ninguna unidad tiene días-cama disponibles registrados.")
    tabla = m.assign(Mes=[tx.MESES[int(x) - 1] for x in m["MES"]])[["ANIO", "fila", "Mes", "ocupacion"]]
    cm.grafico(tx.con_periodo(f"Ocupación mensual por unidad · {familia}", anios),
               gr.lineas_ocupacion_periodo(m, list(anios), colores_unidades(cod, familia)[1]),
               texto, "g_hosp_camas_calor", cp.ayuda("ocupacion_unidad"), notas,
               tabla=cm.tabla_humana(tabla, {"fila": "Unidad (nombre corto)", "ocupacion": "Ocupación (%)"}))


def _grafico_calor(cod: str, anio: int, familia: str) -> None:
    """Nivel específico (C): ocupación mensual del año foco, una línea por unidad de la familia elegida (la clave
    `g_hosp_camas_calor` se conserva: antes era un mapa de calor)."""
    m = ocupacion_unidad_mes(cod, anio, familia)
    notas = ()
    if m["ocupacion"].isna().any():
        notas += ("Los meses sin punto son meses sin días-cama disponibles en esa unidad.",)
    if (m["ocupacion"] > 100).any():
        notas += (AVISO_SOBRE_100,)
    if OTRAS_UNIDADES in set(m["fila"]):
        notas += (f"«{OTRAS_UNIDADES}» junta las unidades con menos camas, sumando sus días-cama; cada una está en el gráfico "
                  "de camas por unidad.",)
    tabla = m.assign(Mes=[tx.MESES[int(x) - 1] for x in m["MES"]])[["fila", "Mes", "ocupacion"]]
    cm.grafico(tx.con_periodo(f"Ocupación mensual por unidad · {familia}", [anio]), gr.lineas_ocupacion(m, colores_unidades(cod, familia)[1]), _lectura_calor(m, anio),
               "g_hosp_camas_calor", cp.ayuda("ocupacion_unidad"), notas,
               tabla=cm.tabla_humana(tabla, {"fila": "Unidad (nombre corto)", "ocupacion": "Ocupación (%)"}))


def _etiqueta_opcion(f: pd.DataFrame):
    camas = dict(zip(f["familia"], f["camas"]))
    return lambda o: (o if o == TODAS_FAMILIAS or o not in camas
                      else f"{o} · {tx.numero(camas[o], 1 if camas[o] < 10 else 0)} camas")


def _selector_familia(f: pd.DataFrame, con_camas: bool = True) -> str:
    """Selector del nivel específico; si la familia guardada no está en este hospital y período, vuelve a la vista general.
    Con un año cada opción dice sus camas; con varios, solo el nombre (las camas cambian de un año a otro)."""
    opciones = opciones_familia(f)
    etiqueta = _etiqueta_opcion(f if con_camas else f.iloc[0:0])
    rotulos = tuple(etiqueta(o) for o in opciones)
    actual = st.session_state.get(CLAVE_FAMILIA)
    if actual not in opciones:
        st.session_state[CLAVE_FAMILIA] = TODAS_FAMILIAS
    elif st.session_state.get(f"{CLAVE_FAMILIA}_rotulos") != rotulos:
        # otro hospital o año con la misma familia: se reasigna para que el cuadro muestre sus camas, no las del anterior
        st.session_state[CLAVE_FAMILIA] = actual
    st.session_state[f"{CLAVE_FAMILIA}_rotulos"] = rotulos
    return st.selectbox("Ver las unidades de una familia", opciones, key=CLAVE_FAMILIA, format_func=etiqueta,
                        help=cp.ayuda("familia_unidad"), width=420)


def familias_periodo(cod: str, anios: tuple[int, ...]) -> pd.DataFrame:
    """Familias con camas en alguno de los años elegidos (las del último año primero, de más a menos camas)."""
    partes = [familias(cod, a) for a in sorted(anios, reverse=True)]
    f = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["familia", "camas"])
    return f.drop_duplicates("familia").reset_index(drop=True)


@st.fragment
def _detalle_familia(cod: str, anio: int, anios: tuple[int, ...]) -> None:
    """Selector de familia y sus gráficos, con la misma regla de años que la vista general: con un año, sus unidades de
    ese año (barras) y su ocupación mensual de ese año; con varios, la evolución de sus unidades en esos años y su ocupación
    mensual en esos años. Es un fragmento: al elegir otra familia solo se redibuja esto."""
    varios = len(anios) > 1
    f = familias_periodo(cod, anios) if varios else familias(cod, anio)
    if f.empty:
        return
    familia = _selector_familia(f, con_camas=not varios)
    if familia == TODAS_FAMILIAS:
        st.caption("Elige una familia para ver sus unidades: " + ("camas y ocupación mensual en los años elegidos."
                                                                 if varios else f"camas y ocupación mensual de {anio}."))
        return
    if varios:
        _grafico_evolucion_unidades(cod, familia, anios)
        _grafico_calor_periodo(cod, anios, familia)
    else:
        _grafico_unidades(cod, unidades_de_familia(unidades(cod, anio), familia), familia, anio)
        _grafico_calor(cod, anio, familia)


def _unidades(cod: str, anio: int, anios: tuple[int, ...]) -> None:
    """Camas de lo general a lo específico, con la regla de años de la página: con un año, las barras por familia de ese
    año; con varios, solo la evolución por familia de esos años (nunca los dos gráficos a la vez). Debajo, el selector de
    familia con sus unidades."""
    with st.container(key="hosp_camas_graficos"):
        if len(anios) > 1:
            _grafico_evolucion(cod, anios)
        else:
            f = familias(cod, anio)
            if f.empty:  # filas del REM20 en el año, pero todas con 0 camas
                st.caption(f"En {anio} el REM20 no registra camas por unidad en este hospital.")
                return
            _grafico_familias(f, anio)
        _detalle_familia(cod, anio, anios)


def camas(sel: Seleccion, cod: str) -> None:
    """Camas y ocupación del hospital (REM20): tarjetas del año foco, curva mensual y camas por unidad.

    Sigue al hospital y al año foco, no al tipo de atención ni a que haya egresos GRD; sin filas del REM20 en el año lo dice.
    """
    p = hp._periodo(sel)
    c = camas_hospital(cod)
    foco = c[c["ANIO"] == p.foco]
    if foco.empty:
        st.info(f"El REM20 no trae camas de este hospital en {p.foco}.")
        return
    base = c[c["ANIO"] == p.base] if p.base is not None else None
    b = _valores(base) if base is not None and not base.empty else None
    f = _valores(foco)
    with st.container(key="hosp_camas"):
        st.subheader("Camas y ocupación")
        st.caption(f"Año {p.foco}" + (" · Las camas son de hospitalización, aunque en la barra lateral esté elegido «Ambulatorio»."
                                      if sel.tipo == ha.AMB else ""))
        _tarjetas(f, b, p.foco, p.base)
        _curva(cod, hp._anios_vistos(sel, p), p, f, b)
        _unidades(cod, p.foco, tuple(hp._anios_vistos(sel, p)))
        st.caption(nota_fuente(f["egresos"], hp._egresos_del_anio(cod, ha.HOSP, p.foco), p.foco))
