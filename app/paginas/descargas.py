"""Página Descargas: por tabla agregada, un Excel citable (datos, filtros aplicados y cómo citar) y un CSV."""
import io
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl import Workbook

import datos
import indicadores as ind
import textos as tx
from paginas import comun as cm
from seleccion import SEXOS, TIPOS, Seleccion, actual, catalogo, opciones

DESCRIPCION = {"perfil": "Perfil de egresos", "mensual": "Egresos por mes", "grd": "Egresos por GRD",
               "flujos": "Flujos territoriales", "estancia": "Distribución de la estancia",
               "estancia_severidad": "Estancia por severidad", "cronicas": "Condiciones crónicas",
               "comorbilidad": "Comorbilidad (15 grupos de enfermedades crónicas)"}
RUTA_DICCIONARIO = Path(__file__).resolve().parents[1] / "recursos" / "diccionario.csv"
CITA = "Fuente: FONASA, Datos Abiertos (https://datosabiertos.fonasa.cl). NexoViewer: Observatorio GRD Chile, {fecha}."
MAX_FILAS_EXCEL = 1_048_576  # filas de una hoja de Excel, contando la de títulos
# Tope de celdas (filas × columnas) del Excel. openpyxl en modo `write_only` tarda ~30 µs por celda en esta máquina
# (grd: 632 mil celdas, 21 s; perfil: 1,08 millones, 33 s), así que 450 mil celdas dan unos 14 s.
MAX_CELDAS_EXCEL = 450_000
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fecha(hoy: date | None = None) -> str:
    """Fecha en palabras («19 de noviembre de 2026»); por defecto, la de hoy."""
    hoy = hoy or date.today()
    return f"{hoy.day} de {tx.MESES[hoy.month - 1]} de {hoy.year}"


def _cita(hoy: date | None = None) -> str:
    """La cita con la fecha puesta."""
    return CITA.format(fecha=_fecha(hoy))


def cabe_en_excel(filas: int, columnas: int = 1) -> bool:
    """El Excel se ofrece si la tabla cabe en una hoja (1.048.576 filas, una es la de títulos) y no pasa el tope de
    celdas (filas × columnas) con que se arma en unos 15 segundos; sobre eso se usa el CSV."""
    return filas < MAX_FILAS_EXCEL and filas * columnas <= MAX_CELDAS_EXCEL


def _nombre_hospital(codigo: str) -> str:
    """Nombre del hospital con su código; solo el código si no está en el catálogo."""
    cat = catalogo()
    fila = cat[cat["COD_HOSPITAL"].astype(str) == str(codigo)]
    return f"{fila['HOSPITAL'].iloc[0]} ({codigo})" if len(fila) else str(codigo)


def _hoja_filtros(sel: Seleccion, p: ind.Periodo, hoy: date | None = None, tabla: str | None = None) -> pd.DataFrame:
    """Hoja «Filtros aplicados»: una fila por filtro («Todos» si no hay), la fecha y la cobertura de los datos.

    Para la tabla `comorbilidad` agrega una fila que dice de dónde sale la lista de enfermedades crónicas.
    """
    todos = datos.anios_disponibles()
    anios = ", ".join(str(a) for a in sorted(sel.anios)) + (f" (compara {p.base} con {p.foco})" if p.modo == "comparar" else "")
    tipo = next((k for k, v in TIPOS.items() if v == sel.tipo), sel.tipo)
    filas = [
        ("Años", anios),
        ("Tipo de atención", tipo),
        # «65 hospitales» y «2019–2025» coinciden con GLOSARIO.md (Panel) y Metodología; revisar si cambian los datos
        ("Panel", "Solo los 65 hospitales que informan los 7 años" if sel.panel else "Todos los hospitales"),
        ("Región", sel.region or "Todos"),
        ("Servicio de salud", sel.servicio or "Todos"),
        ("Hospital", _nombre_hospital(sel.hospital) if sel.hospital else "Todos"),
        ("Sexo", SEXOS.get(sel.sexo, sel.sexo) if sel.sexo else "Todos"),
        ("Edad", sel.grupo_edad or "Todos"),
        ("Capítulo", tx.etiqueta_capitulo(sel.capitulo) if sel.capitulo else "Todos"),
        ("GRD", opciones()["grd"].get(str(sel.grd), str(sel.grd)) if sel.grd else "Todos"),
        ("Fecha de generación", _fecha(hoy)),
        ("Cobertura de los datos", f"Egresos de {todos[0]}–{todos[-1]} de hospitales públicos con GRD "
                                   "(sin sector privado). Fuente: FONASA, Datos Abiertos."),
    ]
    if tabla == "comorbilidad":
        incluidas = ", ".join(tx.NOMBRES_CRONICAS.values())
        filas.append(("Lista de enfermedades crónicas", f"Definición del equipo (respaldo: problemas de salud GES del MINSAL, Decreto 29 de 2025, y Encuesta Nacional "
                      f"de Salud 2016-2017; rangos CIE-10 según Quan et al. 2005). Incluye: {incluidas}."))
    return pd.DataFrame(filas, columns=["Filtro", "Valor"])


def _hoja_cita(hoy: date | None = None) -> pd.DataFrame:
    """Hoja «Cómo citar»: la cita de la fuente, una línea sugerida para el dashboard y dos advertencias de lectura."""
    todos = datos.anios_disponibles()
    return pd.DataFrame({"Cómo citar": [
        _cita(hoy),
        f"Cita sugerida del dashboard: NexoViewer: Observatorio GRD Chile. Egresos hospitalarios GRD {todos[0]}–{todos[-1]} (FONASA). "
        f"Tabla descargada el {_fecha(hoy)}.",
        "El peso GRD es relativo (no es un monto en pesos) y cada fila cuenta egresos, no personas.",
    ]})


@st.cache_data(max_entries=64)
def _filas(clave: tuple, tabla: str) -> int:
    """Filas de la tabla con la selección aplicada."""
    return len(datos.filtrar(datos.cargar(tabla), cm.desde_clave(clave)))


def _csv(tabla: str, sel: Seleccion) -> bytes:
    """CSV de la tabla filtrada, con ';' y coma decimal, en UTF-8 con marca para que Excel lea los acentos."""
    return datos.filtrar(datos.cargar(tabla), sel).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def _hoja(libro, nombre: str, df: pd.DataFrame, anchos: tuple[int, ...] = ()) -> None:
    """Escribe `df` como una hoja en modo de solo escritura (fila a fila, sin armar toda la hoja en memoria)."""
    hoja = libro.create_sheet(nombre)
    for letra, ancho in zip("ABCDEFGH", anchos):
        hoja.column_dimensions[letra].width = ancho
    hoja.append(list(df.columns))
    filas = df.astype(object).where(df.notna(), None).values.tolist()  # tipos de Python; los vacíos, celdas vacías
    for fila in filas:
        hoja.append(fila)


def _xlsx(tabla: str, sel: Seleccion, p: ind.Periodo, hoy: date | None = None) -> bytes:
    """Excel con las hojas «Datos» (tabla filtrada), «Filtros aplicados» y «Cómo citar».

    Usa el modo `write_only` de openpyxl: `DataFrame.to_excel` crea una celda por valor y tarda minutos en tablas grandes.
    """
    libro = Workbook(write_only=True)
    _hoja(libro, "Datos", datos.filtrar(datos.cargar(tabla), sel))
    _hoja(libro, "Filtros aplicados", _hoja_filtros(sel, p, hoy, tabla), (24, 90))
    _hoja(libro, "Cómo citar", _hoja_cita(hoy), (120,))
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def main() -> None:
    """Por tabla, un Excel y un CSV (se arman solo al descargar), y el diccionario de datos."""
    cm.encabezado("Descargas")
    sel = actual()
    if not sel.anios:  # sin años elegidos se usa el año foco, como en las demás páginas
        anio = ind.periodo([], datos.anios_disponibles()).foco
        sel = replace(sel, anios=[anio])
        st.sidebar.caption(f"Sin años elegidos: se muestra {anio}.")
    st.markdown("Cada archivo trae la tabla agregada con los años, el tipo de atención y los filtros elegidos. "
                "El Excel (`.xlsx`) trae tres hojas: `Datos`, `Filtros aplicados` y `Cómo citar`. El CSV se abre en Excel "
                "(separador `;` y coma decimal). Fuente: FONASA, Datos Abiertos (https://datosabiertos.fonasa.cl).",
                help=tx.GLOSARIO["como_citar"])
    st.caption("El Excel se ofrece solo para tablas pequeñas; si el botón está apagado, la tabla es muy grande: descarga el CSV "
               "(trae los mismos datos, sin la hoja de filtros ni la cita) o reduce los filtros, por ejemplo a un hospital o una región.")
    st.markdown("Los filtros que una tabla no tiene (por ejemplo, sexo en `grd` o panel en `flujos`) no se aplican a esa tabla.")
    sufijo = "-".join(str(a) for a in sorted(sel.anios)) + f"_{sel.tipo.lower().replace('ó', 'o')}" + ("_panel" if sel.panel else "")
    p = ind.periodo(sel.anios, datos.anios_disponibles())
    with st.container(key="descargas_tablas"):
        for tabla in datos.TABLAS:
            filas = _filas(cm.clave(sel), tabla)
            cabe = cabe_en_excel(filas + 1, len(datos.COLUMNAS_REQUERIDAS[tabla]))
            c = st.columns([3, 2, 2, 2])
            c[0].markdown(f"**{DESCRIPCION[tabla]}** (`{tabla}`)")
            c[1].markdown(f"{tx.numero(filas)} filas")
            c[2].download_button("Descargar Excel", data=lambda t=tabla: _xlsx(t, sel, p), file_name=f"grd_{tabla}_{sufijo}.xlsx",
                                 mime=MIME_XLSX, key=f"dlx_{tabla}", on_click="ignore", disabled=not cabe,
                                 help=None if cabe else "La tabla es demasiado grande para armar el Excel (tardaría minutos): usa el CSV, que trae los mismos datos (sin la hoja de filtros ni la cita).")
            c[3].download_button("Descargar CSV", data=lambda t=tabla: _csv(t, sel), file_name=f"grd_{tabla}_{sufijo}.csv",
                                 mime="text/csv", key=f"dl_{tabla}", on_click="ignore")
    st.subheader("Diccionario de datos")
    dic = pd.read_csv(RUTA_DICCIONARIO, encoding="utf-8")
    st.markdown("Qué significa cada columna de las tablas.", help=tx.GLOSARIO["diccionario_datos"])
    st.download_button("Descargar diccionario (CSV)", data=lambda: dic.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name="grd_diccionario_de_datos.csv", mime="text/csv", key="dl_diccionario", on_click="ignore")
    with st.expander("Ver el diccionario de datos"):
        st.dataframe(dic, hide_index=True, key="t_diccionario")


main()
