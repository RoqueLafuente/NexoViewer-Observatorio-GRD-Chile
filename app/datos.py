"""Carga de los agregados versionados y aplicación de los filtros de la selección."""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pyarrow.parquet as pq
import streamlit as st

from indicadores import GRUPOS_EDAD, grupo_edad  # noqa: F401 (reexportados)

DIR_AGREGADOS = Path(__file__).resolve().parent.parent / "datos_procesados" / "agregados"
DIR_BASE = DIR_AGREGADOS.parent / "grd"  # base armonizada (puede no estar: la app solo cuenta sus variables si existe)
TABLAS = ("perfil", "mensual", "grd", "flujos", "estancia", "estancia_severidad", "cronicas", "comorbilidad")
# Tablas de DEIS y REM20: no salen de la base GRD, por eso Descargas (que recorre TABLAS) no las lista.
TABLAS_EXTERNAS = ("establecimientos", "camas")
COLUMNA_DE = {"region": "REGION_HOSPITAL", "servicio": "SS_HOSPITAL", "hospital": "COD_HOSPITAL", "sexo": "SEXO",
              "capitulo": "CAPITULO_CIE10", "grd": "COD_GRD"}


# Columnas que produce `grd_funciones.sql_agregados()` (una prueba verifica que coincidan).
COLUMNAS_REQUERIDAS = {
    "perfil": ("ANIO", "COD_HOSPITAL", "HOSPITAL", "REGION_HOSPITAL", "SS_HOSPITAL", "EN_PANEL_7_ANIOS", "REGION_PACIENTE",
               "TIPO_EPISODIO", "CAPITULO_CIE10", "TRAMO_EDAD", "SEXO", "episodios", "fallecidos", "dias_estada",
               "episodios_con_estancia", "peso_total", "severidad_mayor", "diag_secundarios", "diabetes", "hipertension",
               "epoc", "erc"),
    "mensual": ("mes", "COD_HOSPITAL", "HOSPITAL", "REGION_HOSPITAL", "EN_PANEL_7_ANIOS", "TIPO_EPISODIO", "episodios",
                "fallecidos", "peso_total", "covid"),
    "grd": ("ANIO", "COD_HOSPITAL", "HOSPITAL", "REGION_HOSPITAL", "EN_PANEL_7_ANIOS", "SEVERIDAD", "COD_GRD",
            "DESCRIPCION_GRD", "TIPO_GRD", "episodios", "peso_total", "dias_estada", "episodios_con_estancia", "fallecidos"),
    "flujos": ("ANIO", "REGION_PACIENTE", "SS_PACIENTE", "PROVINCIA_PACIENTE", "REGION_HOSPITAL", "COD_HOSPITAL", "HOSPITAL",
               "TIPO_EPISODIO", "episodios", "peso_total"),
    "estancia": ("ANIO", "COD_HOSPITAL", "REGION_HOSPITAL", "SS_HOSPITAL", "EN_PANEL_7_ANIOS", "TIPO_EPISODIO", "SEXO",
                 "TRAMO_EDAD", "CAPITULO_CIE10", "DIAS", "episodios"),
    "estancia_severidad": ("ANIO", "COD_HOSPITAL", "REGION_HOSPITAL", "EN_PANEL_7_ANIOS", "SEVERIDAD", "DIAS", "episodios"),
    "cronicas": ("ANIO", "REGION_HOSPITAL", "EN_PANEL_7_ANIOS", "TRAMO_EDAD", "SEXO", "SEVERIDAD", "CRONICAS", "episodios",
                 "fallecidos"),
    "comorbilidad": ("ANIO", "REGION_HOSPITAL", "EN_PANEL_7_ANIOS", "TRAMO_EDAD", "SEXO", "SEVERIDAD", "COMBINACION",
                     "episodios", "fallecidos"),
    # solo la lee la pestaña Hospitales: no está en TABLAS (ni en Descargas ni en `precalentar`) para no cargarla al arrancar
    "comorbilidad_hospital": ("ANIO", "COD_HOSPITAL", "TRAMO_EDAD", "SEVERIDAD", "COMBINACION", "episodios", "fallecidos"),
    "establecimientos": ("COD_HOSPITAL", "NOMBRE_DEIS", "COMUNA", "NIVEL_COMPLEJIDAD", "NIVEL_ATENCION", "TIPO_ESTABLECIMIENTO",
                         "CERTIFICACION", "TIENE_URGENCIA", "TIPO_URGENCIA", "LATITUD", "LONGITUD"),
    "camas": ("ANIO", "MES", "COD_HOSPITAL", "AREA_FUNCIONAL", "dias_cama_disponibles", "dias_cama_ocupados", "dias_estada",
              "egresos", "egresos_fallecidos", "traslados", "camas_promedio"),
}
REGENERAR = "vuelve a descargar la carpeta `datos_procesados/agregados` del repositorio"


def problemas() -> list[str]:
    """Tablas de agregados que faltan o no traen las columnas que usa la app, con un mensaje por tabla."""
    salida = []
    for tabla, requeridas in COLUMNAS_REQUERIDAS.items():
        ruta = DIR_AGREGADOS / f"{tabla}.parquet"
        if not ruta.exists():
            salida.append(f"{tabla}: no existe el archivo; {REGENERAR}.")
            continue
        try:
            columnas = set(pq.read_schema(ruta).names)
        except Exception:  # archivo ilegible o que no es parquet
            salida.append(f"{tabla}: el archivo no se puede leer; {REGENERAR}.")
            continue
        faltan = [c for c in requeridas if c not in columnas]
        if faltan:
            salida.append(f"{tabla}: faltan las columnas {', '.join(faltan)}; {REGENERAR}.")
    return salida


def variables_base() -> int | None:
    """Número de variables de la base armonizada (columnas del parquet más la partición ANIO), o None si no está."""
    archivos = sorted(DIR_BASE.glob("ANIO=*/*.parquet"))
    if not archivos:
        return None
    nombres = pq.read_schema(archivos[0]).names
    return len(nombres) + ("ANIO" not in nombres)


MAX_CATEGORIAS = 5000  # una columna de texto con menos valores distintos se guarda como `category`


def _a_category(df: pd.DataFrame) -> pd.DataFrame:
    """Pasa a `category` las columnas de texto con pocos valores distintos (menos memoria, copias de caché más rápidas)."""
    for col in df.columns:
        if (pd.api.types.is_string_dtype(df[col].dtype) or df[col].dtype == object) and df[col].nunique() < MAX_CATEGORIAS:
            df[col] = df[col].astype("category")
    return df


@st.cache_data
def cargar(tabla: str, columnas: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Lee un agregado desde su parquet (con caché), solo las `columnas` pedidas si se indican.

    Las columnas de texto salen como `category`: la igualdad y `isin` dan lo mismo que con texto, y los `groupby` ya
    usan `observed=True` por omisión en pandas 3 (no se forma el producto cartesiano de categorías).
    """
    df = pd.read_parquet(DIR_AGREGADOS / f"{tabla}.parquet", columns=None if columnas is None else list(columnas))
    return _a_category(df)


def columnas_con_filtros(tabla: str, columnas: tuple[str, ...], sel) -> tuple[str, ...]:
    """Las `columnas` más las que `filtrar` necesita para aplicar `sel` a esa tabla.

    `filtrar` ignora un filtro cuya columna no está; pasar solo `columnas` a `cargar` lo descartaría sin avisar.
    """
    extra = ["ANIO", "mes", "TIPO_EPISODIO"]
    if sel.panel:
        extra.append("EN_PANEL_7_ANIOS")
    extra += [col for campo, col in COLUMNA_DE.items() if getattr(sel, campo) is not None]
    if sel.grupo_edad is not None:
        extra.append("TRAMO_EDAD")
    esquema = set(COLUMNAS_REQUERIDAS[tabla])
    return tuple(dict.fromkeys([*columnas, *(c for c in extra if c in esquema)]))


def cargar_para(tabla: str, columnas: tuple[str, ...], sel) -> pd.DataFrame:
    """Lee solo `columnas` más las que `filtrar` necesita para aplicar `sel` (así ningún filtro se descarta sin aviso)."""
    return cargar(tabla, columnas_con_filtros(tabla, columnas, sel))


COLUMNAS_KPI = {"perfil": ("episodios", "peso_total", "fallecidos"), "estancia": ("DIAS", "episodios")}


@st.cache_resource(show_spinner="Cargando los datos (solo la primera vez)…")
def precalentar() -> None:
    """Carga los agregados una vez al iniciar el servidor, para que la primera página no los lea del disco.

    `estancia` (la más pesada) solo se lee con las columnas que usa Inicio; las demás, completas.
    """
    inicial = SimpleNamespace(anios=[], tipo="HOSPITALIZACIÓN", panel=False, grupo_edad=None, **{c: None for c in COLUMNA_DE})
    for tabla in TABLAS + TABLAS_EXTERNAS:
        if tabla in COLUMNAS_KPI:
            cargar_para(tabla, COLUMNAS_KPI[tabla], inicial)
        if tabla != "estancia":
            cargar(tabla)


def anios_disponibles() -> list[int]:
    """Años presentes en el agregado de perfil, ordenados."""
    return sorted(int(a) for a in cargar("perfil", ("ANIO",))["ANIO"].unique())


def filtrar(df: pd.DataFrame, sel, anios: list[int] | None = None) -> pd.DataFrame:
    """Aplica la selección a un agregado; ignora los filtros cuyas columnas no existen."""
    anios = sel.anios if anios is None else anios
    if "ANIO" in df.columns:
        df = df[df["ANIO"].isin(anios)]
    elif "mes" in df.columns:
        df = df[pd.to_datetime(df["mes"]).dt.year.isin(anios)]
    if "TIPO_EPISODIO" in df.columns:
        df = df[df["TIPO_EPISODIO"] == sel.tipo]
    if sel.panel and "EN_PANEL_7_ANIOS" in df.columns:
        df = df[df["EN_PANEL_7_ANIOS"] == True]  # noqa: E712
    for campo, columna in COLUMNA_DE.items():
        valor = getattr(sel, campo)
        if valor is not None and columna in df.columns:
            df = df[df[columna] == valor]
    if sel.grupo_edad is not None and "TRAMO_EDAD" in df.columns:
        df = df[df["TRAMO_EDAD"].astype(str).map(grupo_edad) == sel.grupo_edad]
    return df
