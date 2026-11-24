"""Período, cobertura y variación de los indicadores del dashboard (funciones puras, sin Streamlit)."""
import re
from typing import NamedTuple

import pandas as pd

import textos as tx

MIN_CASOS = 30
GRUPOS_EDAD = ("0–14", "15–29", "30–44", "45–59", "60–74", "75+")


class Periodo(NamedTuple):
    """Período elegido: modo, año foco y año base (None si no hay)."""
    modo: str
    foco: int
    base: int | None


class Variacion(NamedTuple):
    """Texto, color y visibilidad de la variación de un indicador."""
    texto: str
    color: str
    mostrar: bool


def periodo(anios: list[int], disponibles: list[int]) -> Periodo:
    """Resuelve el período a partir de los años elegidos y los disponibles."""
    anios = sorted(anios)
    if not anios:
        anios = [max(disponibles)]
    if len(anios) == 1:
        foco = anios[0]
        return Periodo("un_anio", foco, foco - 1 if foco - 1 in disponibles else None)
    return Periodo("comparar", anios[-1], anios[0])


def hospitales_por_anio(perfil: pd.DataFrame) -> dict[int, int]:
    """Cuenta los hospitales distintos que reportan en cada año."""
    return {int(a): int(n) for a, n in perfil.groupby("ANIO")["COD_HOSPITAL"].nunique().items()}


def cobertura_distinta(p: Periodo, hospitales: dict[int, int], panel: bool) -> bool:
    """Indica si el año base y el foco tienen distinta cantidad de hospitales."""
    if p.base is None or panel:
        return False
    return hospitales.get(p.base, 0) != hospitales.get(p.foco, 0)


def variacion(foco: float, base: float | None, tipo: str, favorable: str, n_base: int) -> Variacion:
    """Calcula la variación foco vs base con su texto, color y visibilidad."""
    if base is None:
        return Variacion("", "neutro", False)
    if n_base < MIN_CASOS:
        return Variacion("pocos casos para comparar", "neutro", False)
    if tipo == "porcentaje":
        delta, dec, unidad = foco - base, 2, "pp"
    else:
        if base == 0:
            return Variacion("", "neutro", False)
        delta, dec, unidad = (foco - base) / base * 100, 1, "%"
    r = round(delta, dec)
    if r == 0:
        return Variacion("= sin cambio", "neutro", True)
    flecha = "↑" if r > 0 else "↓"
    if favorable == "baja":
        color = "negativo" if r > 0 else "positivo"
    else:
        color = "neutro"
    return Variacion(f"{flecha} {tx.numero(abs(r), dec)} {unidad}", color, True)


def kpis(perfil: pd.DataFrame) -> dict:
    """Calcula egresos, casemix y mortalidad (%) sumando sobre el DataFrame."""
    egresos = int(perfil["episodios"].sum())
    if egresos == 0:
        return {"egresos": 0, "casemix": None, "mortalidad": None, "n": 0}
    return {
        "egresos": egresos,
        "casemix": float(perfil["peso_total"].sum() / egresos),
        "mortalidad": float(perfil["fallecidos"].sum() / egresos * 100),
        "n": egresos,
    }


def percentil_estancia(estancia: pd.DataFrame, q: float) -> int | None:
    """Devuelve los días donde el acumulado de episodios alcanza la fracción q."""
    total = estancia["episodios"].sum()
    if estancia.empty or total == 0:
        return None
    h = estancia.sort_values("DIAS")
    acumulado = h["episodios"].cumsum() / total
    return int(h.loc[acumulado >= q, "DIAS"].iloc[0])


def por_severidad(grd: pd.DataFrame) -> pd.DataFrame:
    """Resume episodios, mortalidad (%) y estancia media por severidad 1 a 3."""
    g = grd[grd["SEVERIDAD"].isin([1, 2, 3])]
    s = g.groupby("SEVERIDAD")[["episodios", "fallecidos", "dias_estada", "episodios_con_estancia"]].sum()
    s["mortalidad"] = s["fallecidos"] / s["episodios"] * 100
    s["estancia_media"] = s["dias_estada"] / s["episodios_con_estancia"]
    return s.reset_index()[["SEVERIDAD", "episodios", "mortalidad", "estancia_media"]]


def ier(grd: pd.DataFrame, grd_nacional: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Índice de estancia relativa: días observados sobre esperados con la media nacional por GRD."""
    columnas = por + ["episodios", "dias_obs", "dias_esp", "ier"]
    hosp = grd[grd["TIPO_GRD"].isin(["MH", "PH"])]
    if hosp.empty:
        return pd.DataFrame(columns=columnas)
    nac = grd_nacional[grd_nacional["TIPO_GRD"].isin(["MH", "PH"])]
    nac = nac.groupby(["ANIO", "COD_GRD"])[["dias_estada", "episodios_con_estancia"]].sum()
    media = (nac["dias_estada"] / nac["episodios_con_estancia"]).where(nac["episodios_con_estancia"] > 0)
    media = media.rename("media_nac").reset_index()
    d = hosp.merge(media, on=["ANIO", "COD_GRD"], how="left")
    if "episodios" not in d:
        d["episodios"] = d["episodios_con_estancia"]
    d["media_nac"] = d["media_nac"].fillna(0.0)
    d["dias_esp"] = d["episodios_con_estancia"] * d["media_nac"]
    r = d.groupby(por)[["episodios", "dias_estada", "dias_esp"]].sum().reset_index()
    r = r.rename(columns={"dias_estada": "dias_obs"})
    r["ier"] = (r["dias_obs"] / r["dias_esp"]).where(r["dias_esp"] > 0)
    return r[columnas]


def grupo_edad(tramo: str | None) -> str | None:
    """Agrupa un tramo quinquenal como '[65 - 69 años]' en uno de los seis grupos de edad."""
    if tramo is None or pd.isna(tramo):
        return None
    m = re.match(r"\[(\d+)", tramo)
    if not m:
        return None
    edad = int(m.group(1))
    return GRUPOS_EDAD[min(edad // 15, 4) if edad < 75 else 5]


def pareto(grd: pd.DataFrame) -> pd.DataFrame:
    """Peso por GRD de mayor a menor con porcentaje y porcentaje acumulado."""
    r = grd.groupby(["COD_GRD", "DESCRIPCION_GRD"], dropna=False)["peso_total"].sum().reset_index()
    r = r.sort_values("peso_total", ascending=False, kind="stable").reset_index(drop=True)
    r["pct"] = r["peso_total"] / r["peso_total"].sum() * 100
    r["pct_acum"] = r["pct"].cumsum()
    return r


def n_grd_para(pareto_df: pd.DataFrame, umbral: float) -> int:
    """Número de GRD necesarios para alcanzar el umbral (0,5 = 50 %) del peso."""
    return int((pareto_df["pct_acum"] < umbral * 100 - 1e-9).sum()) + 1 if len(pareto_df) else 0


def cuadrante(perfil: pd.DataFrame) -> pd.DataFrame:
    """Porcentaje de episodios y de peso por capítulo CIE-10 (nulo como 'Sin capítulo')."""
    p = perfil.assign(CAPITULO_CIE10=perfil["CAPITULO_CIE10"].astype(str).fillna("Sin capítulo"))
    r = p.groupby("CAPITULO_CIE10")[["episodios", "peso_total"]].sum().reset_index()
    r["pct_episodios"] = r["episodios"] / r["episodios"].sum() * 100
    r["pct_peso"] = r["peso_total"] / r["peso_total"].sum() * 100
    return r[["CAPITULO_CIE10", "pct_episodios", "pct_peso"]]


def indice_actividad(mensual: pd.DataFrame) -> pd.DataFrame:
    """Episodios por año y tipo con índice 2019 = 100 dentro de cada tipo."""
    m = mensual.assign(ANIO=mensual["mes"].dt.year)
    r = m.assign(TIPO_EPISODIO=m["TIPO_EPISODIO"].astype(str)).groupby(["ANIO", "TIPO_EPISODIO"])["episodios"].sum().reset_index()
    base = r[r["ANIO"] == 2019].set_index("TIPO_EPISODIO")["episodios"]
    b = r["TIPO_EPISODIO"].map(base)
    r["indice"] = (r["episodios"] / b.where(b > 0) * 100)
    return r


def fuera_de_region(flujos: pd.DataFrame) -> pd.DataFrame:
    """Porcentaje de episodios y de peso atendidos fuera de la región del paciente (nulo como 'Sin región')."""
    flujos = flujos.astype({"REGION_PACIENTE": str, "REGION_HOSPITAL": str})  # dos `category` con categorías distintas no se comparan
    fuera = (flujos["REGION_PACIENTE"].notna() & flujos["REGION_HOSPITAL"].notna()
             & (flujos["REGION_HOSPITAL"] != flujos["REGION_PACIENTE"]))
    f = flujos.assign(REGION_PACIENTE=flujos["REGION_PACIENTE"].fillna("Sin región"),
                      fuera_ep=flujos["episodios"].where(fuera, 0), fuera_peso=flujos["peso_total"].where(fuera, 0))
    r = f.groupby("REGION_PACIENTE")[["episodios", "peso_total", "fuera_ep", "fuera_peso"]].sum().reset_index()
    r["pct_fuera_episodios"] = (r["fuera_ep"] / r["episodios"].where(r["episodios"] > 0) * 100)
    r["pct_fuera_peso"] = (r["fuera_peso"] / r["peso_total"].where(r["peso_total"] > 0) * 100)
    return r[["REGION_PACIENTE", "episodios", "pct_fuera_episodios", "pct_fuera_peso"]]


def mortalidad_cronicas(cronicas: pd.DataFrame, por: list[str], col: str = "CRONICAS") -> pd.DataFrame:
    """Episodios y mortalidad (%) por combinación de crónicas (columna `col`) dentro de las columnas dadas."""
    r = cronicas.groupby(por + [col], dropna=False, observed=True)[["episodios", "fallecidos"]].sum().reset_index()
    r["mortalidad"] = r["fallecidos"] / r["episodios"].where(r["episodios"] > 0) * 100
    return r[por + [col, "episodios", "mortalidad"]]


# --- Comorbilidad definida por la persona ---------------------------------------------------------
# `COMBINACION` trae los grupos de crónicas presentes unidos por «+» (o «Ninguna»). Hay unos pocos miles de
# combinaciones distintas: cada cálculo se hace una vez por combinación y luego se lleva a las filas.

def _partes(combinacion: str) -> list[str]:
    return [] if combinacion == "Ninguna" else combinacion.split("+")


def _por_combinacion(df: pd.DataFrame, funcion) -> pd.Series:
    """Aplica `funcion` a cada combinación distinta y devuelve el resultado alineado con las filas de `df`."""
    unicas = pd.unique(df["COMBINACION"].astype(str))
    valores = {c: funcion(_partes(c)) for c in unicas}
    return df["COMBINACION"].astype(str).map(valores)


def contar_seleccionadas(df: pd.DataFrame, elegidas: tuple[str, ...]) -> pd.DataFrame:
    """Agrega `N_ELEGIDAS`: cuántas de las enfermedades `elegidas` tiene la combinación de cada fila (0 si no se elige ninguna)."""
    elegidas = set(elegidas)
    n = _por_combinacion(df, lambda partes: sum(p in elegidas for p in partes))
    return df.assign(N_ELEGIDAS=n.astype(int) if len(df) else pd.Series(dtype=int))


def solo_elegidas(df: pd.DataFrame, elegidas: tuple[str, ...]) -> pd.DataFrame:
    """Agrega `ELEGIDAS`: la combinación recortada a las enfermedades elegidas (mismo orden), o «Ninguna»."""
    elegidas = set(elegidas)
    return df.assign(ELEGIDAS=_por_combinacion(df, lambda partes: "+".join(p for p in partes if p in elegidas) or "Ninguna"))


def pct_por_cronica(df: pd.DataFrame, elegidas: tuple[str, ...], por: str) -> pd.DataFrame:
    """% de episodios con cada enfermedad elegida dentro de cada valor de `por`; `episodios` es el total del grupo."""
    columnas = [por, "cronica", "episodios", "pct"]
    if not elegidas or df.empty:
        return pd.DataFrame(columns=columnas)
    g = df.groupby([por, "COMBINACION"], observed=True)["episodios"].sum().reset_index()
    total = g.groupby(por, observed=True)["episodios"].sum()
    filas = []
    for e in elegidas:
        tiene = _por_combinacion(g, lambda partes, e=e: e in partes).astype(bool)
        con = g[tiene].groupby(por, observed=True)["episodios"].sum().reindex(total.index, fill_value=0)
        filas.append(pd.DataFrame({por: total.index, "cronica": e, "episodios": total.values,
                                   "pct": (con / total.where(total > 0) * 100).values}))
    return pd.concat(filas, ignore_index=True)[columnas]


def pares_frecuentes(df: pd.DataFrame, elegidas: tuple[str, ...]) -> pd.DataFrame:
    """Episodios con cada par de enfermedades elegidas (A antes que B en el orden de `elegidas`) y su % del total."""
    columnas = ["A", "B", "episodios", "pct"]
    if len(elegidas) < 2 or df.empty:
        return pd.DataFrame(columns=columnas)
    g = df.groupby("COMBINACION", observed=True)["episodios"].sum()
    total = g.sum()
    partes = {c: set(_partes(str(c))) for c in g.index}
    filas = []
    for i, a in enumerate(elegidas):
        for b in elegidas[i + 1:]:
            n = int(sum(v for c, v in g.items() if a in partes[c] and b in partes[c]))
            filas.append({"A": a, "B": b, "episodios": n, "pct": n / total * 100 if total else 0.0})
    return pd.DataFrame(filas, columns=columnas)


CUANTAS_CRONICAS = ("Ninguna", "Una", "Dos o más")  # crónicas elegidas por episodio; nombres cortos para la leyenda


def cuantas_cronicas(df: pd.DataFrame) -> dict[str, float]:
    """% de episodios sin ninguna de las crónicas elegidas, con una y con dos o más (según `N_ELEGIDAS`), en el
    orden de `CUANTAS_CRONICAS`."""
    n = df["N_ELEGIDAS"].clip(upper=2)
    por = df.groupby(n)["episodios"].sum()
    total = por.sum()
    return {k: float(por.get(i, 0) / total * 100) if total else 0.0 for i, k in enumerate(CUANTAS_CRONICAS)}


def distribucion_sexo(perfil: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Episodios y porcentaje por sexo (solo HOMBRE y MUJER) y el número de episodios excluidos."""
    r = perfil.assign(SEXO=perfil["SEXO"].astype(str)).groupby("SEXO", dropna=False)["episodios"].sum().reset_index()
    ok = r["SEXO"].isin(["HOMBRE", "MUJER"])
    r, excluidos = r[ok].copy(), int(r.loc[~ok, "episodios"].sum())
    r["pct"] = r["episodios"] / r["episodios"].sum() * 100
    return r.reset_index(drop=True), excluidos


def enmascarar(df: pd.DataFrame, col_n: str = "episodios", k: int = MIN_CASOS) -> pd.DataFrame:
    """Copia del DataFrame con los valores (columnas numéricas) de las filas con `col_n` < k en NaN y la columna `oculta`.

    Las etiquetas (columnas de texto) se conservan para poder avisar qué celdas no se muestran. Con exactamente k se muestra.
    """
    r = df.copy()
    oculta = r[col_n] < k
    valores = r.select_dtypes("number").columns
    r[valores] = r[valores].astype(float).mask(oculta)
    r["oculta"] = oculta.astype(bool)
    return r


# ---------- camas y ocupación (REM20) ----------

def ocupacion(camas: pd.DataFrame) -> float | None:
    """Índice ocupacional (%) = Σ días-cama ocupados ÷ Σ días-cama disponibles × 100 sobre las filas dadas.

    Siempre se suma antes de dividir (nunca se promedian porcentajes mensuales ni de áreas). Puede pasar de 100: el REM20
    registra a veces más días ocupados que disponibles y no se corta. None si no hay días-cama disponibles.
    """
    disponibles = float(camas["dias_cama_disponibles"].sum())
    return float(camas["dias_cama_ocupados"].sum()) / disponibles * 100 if disponibles > 0 else None


def camas_promedio(camas: pd.DataFrame) -> float | None:
    """Camas promedio del período: promedio, sobre los meses presentes, de la suma de `camas_promedio` de todas las áreas del mes."""
    if camas.empty:
        return None
    return float(camas.groupby([c for c in ("ANIO", "MES") if c in camas.columns])["camas_promedio"].sum().mean())


def rotacion(camas: pd.DataFrame) -> float | None:
    """Rotación = Σ egresos ÷ camas promedio del período: cuántos egresos pasan por cada cama (definición del diccionario REM20).

    Las camas promedio son las de `camas_promedio`. None si no hay camas.
    """
    promedio = camas_promedio(camas)
    return float(camas["egresos"].sum()) / promedio if promedio else None
