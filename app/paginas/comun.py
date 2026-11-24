"""Piezas compartidas por las páginas: catálogo, filtros, clave de caché, cobertura, cambios y gráficos con lectura."""
import textwrap
from collections.abc import Callable

import pandas as pd
import streamlit as st

import componentes as cp
import datos
import graficos as gr
import indicadores as ind
import plantillas as pl
import textos as tx
from seleccion import Seleccion, catalogo, selector  # noqa: F401 (reexportados para las páginas)

TOP = 10


@st.cache_data
def hospitales_por_anio(tipo: str, region: str | None = None, servicio: str | None = None) -> dict[int, int]:
    """Hospitales que informan cada año para el tipo de atención, dentro de la región y el servicio elegidos."""
    s = Seleccion(anios=datos.anios_disponibles(), tipo=tipo, panel=False, region=region, servicio=servicio)
    return ind.hospitales_por_anio(datos.filtrar(datos.cargar_para("perfil", ("COD_HOSPITAL",), s), s))


def cobertura(sel: Seleccion, p: ind.Periodo) -> bool:
    """Advierte si el año base y el foco tienen distinto número de hospitales; dice si advirtió."""
    hosp = hospitales_por_anio(sel.tipo, sel.region, sel.servicio)
    if sel.hospital is None and ind.cobertura_distinta(p, hosp, sel.panel):
        f, b = hosp.get(p.foco, 0), hosp.get(p.base, 0)
        n = f - b
        cp.aviso("Cobertura distinta", f"En {p.foco} informan {f} hospitales y en {p.base}, {b}"
                 + (" (con la región o el servicio elegidos)" if sel.region or sel.servicio else "") + ": "
                 f"{abs(n)} hospitales {'más' if n > 0 else 'menos'}. Por eso los totales no se comparan del todo; para "
                 "ver siempre el mismo grupo, activa «Solo panel de 65 hospitales».")
        return True
    return False


def clave(sel: Seleccion) -> tuple:
    """Selección como tupla hashable para las funciones con caché."""
    return (tuple(sel.anios), sel.tipo, sel.panel, sel.region, sel.servicio, sel.hospital, sel.sexo,
            sel.grupo_edad, sel.capitulo, sel.grd)


def desde_clave(clave: tuple) -> Seleccion:
    """Reconstruye la selección desde su tupla."""
    return Seleccion(list(clave[0]), *clave[1:])


def cambio(r: pd.DataFrame, col: str, p: ind.Periodo, valor: str = "pct", relativo: bool = False,
            minimo: int = 0) -> pd.Series:
    """Cambio base→foco por categoría (pp, o % si es relativo), solo con ≥ `minimo` episodios en la base."""
    t = r.pivot_table(index=col, columns="ANIO", values=valor, aggfunc="sum")
    if p.base not in t or p.foco not in t:
        return pd.Series(dtype=float)
    if minimo:
        n = r[r["ANIO"] == p.base].groupby(col)["episodios"].sum()
        t = t[t.index.isin(n[n >= minimo].index)]
    f, b = t[p.foco].fillna(0), t[p.base]
    return ((f - b) / b.where(b > 0) * 100 if relativo else f - b.fillna(0)).dropna()


def mayor_cambio(serie: pd.Series) -> tuple | None:
    """Categoría con el mayor cambio absoluto y su valor (None si no hay categorías)."""
    if serie.empty:
        return None
    k = serie.abs().idxmax()
    return k, float(serie[k])


def lectura_cambio(nombre: str, p: ind.Periodo, serie: pd.Series, campos: tuple[str, str], pocos: bool) -> str:
    """Lectura de comparación con la categoría de mayor cambio, o la de pocos casos."""
    mayor = mayor_cambio(serie)
    if mayor is None or pocos:
        return tx.lectura(nombre, p, pocos_casos=True)
    return tx.lectura(nombre, p, **dict(zip(campos, mayor)))


LARGO_TITULO = 40  # caracteres por línea del título: más largo se parte para no salirse de una tarjeta angosta (celular)
ALTO_LINEA_TITULO = 22  # px que ocupa cada línea del título dentro de la figura (Plotly sube un título de varias líneas)
AVISO_CELDAS = f"Celdas con menos de {ind.MIN_CASOS} episodios no se muestran."


def _con_titulo(fig, titulo: str, largo: int = LARGO_TITULO) -> None:
    """Pone el título dentro de la figura (arriba a la izquierda) y le deja sitio en el margen superior.

    Dentro de la figura el título sobrevive a la pantalla completa, al zoom y a la descarga como imagen. Se ancla al
    contenedor (no al área del gráfico) y se suma su alto al margen que ya fijó cada gráfico, de modo que las leyendas y
    los títulos de los minigráficos, que viven en ese margen, quedan justo debajo y no se tocan.
    """
    lineas = textwrap.wrap(titulo, largo, break_on_hyphens=False) or [titulo]
    margen = fig.layout.margin.t if fig.layout.margin.t is not None else MARGEN_SUPERIOR
    fig.update_layout(
        title=dict(text="<br>".join(lineas), x=0, xref="container", xanchor="left", y=1, yref="container", yanchor="top",
                   pad=dict(t=6 + 18 * (len(lineas) - 1), l=4), font=dict(size=14, weight="bold")),
        margin=dict(t=margen + ALTO_LINEA_TITULO * len(lineas) + 12))


COLUMNAS = {"ANIO": "Año", "episodios": "Egresos", "pct": "% de egresos", "capitulo": "Capítulo CIE-10",
            "GRUPO_EDAD": "Grupo de edad", "SEXO": "Sexo", "REGION_PACIENTE": "Región del paciente"}
CONTEOS = ("Egresos", "Hospitalizaciones", "Hospitales")  # columnas de conteo: sin decimales
MARGEN_SUPERIOR = 80  # margen superior por defecto de Plotly cuando el gráfico no fija el suyo


def tabla_humana(df: pd.DataFrame, renombres: dict[str, str] | None = None) -> pd.DataFrame:
    """Tabla de lo que dibuja un gráfico, para «Ver en tabla».

    Nombres de columna humanos y los años como texto, nunca «2.024». Las columnas numéricas siguen siendo numéricas
    (así la tabla se ordena por valor y no como texto); su formato se da al mostrarla con `config_columnas`.
    """
    t = df.drop(columns=["oculta"], errors="ignore").rename(columns={**COLUMNAS, **(renombres or {})})
    for col in t.columns:
        if col == "Año":
            t[col] = t[col].map(lambda v: tx.SIN_DATO if pd.isna(v) else str(int(v)))
    return t


def config_columnas(t: pd.DataFrame) -> dict:
    """Formato de pantalla de las columnas numéricas de «Ver en tabla».

    Compromiso: `NumberColumn` no admite separadores chilenos a medida. Los conteos usan «localized» (separador de miles
    según el idioma del navegador: punto con es-CL) y los demás un decimal con `%.1f` (punto decimal). Una celda vacía
    (oculta por tener pocos casos) se ve en blanco, no «—». Se prefiere esto a convertir en texto, que ordenaría mal.
    """
    cfg = {}
    for col in t.columns:
        if pd.api.types.is_numeric_dtype(t[col]):
            entera = col in CONTEOS or pd.api.types.is_integer_dtype(t[col])
            cfg[col] = st.column_config.NumberColumn(col, format="localized" if entera else "%.1f")
    return cfg


def grafico(titulo: str, fig, texto: str, key: str, ayuda: str | None = None, notas: tuple[str, ...] = (),
            altura: int | None = None, tabla: pd.DataFrame | None = None,
            bajo_figura: Callable[[], None] | None = None, config: dict | None = None, cifra: str | None = None,
            largo_titulo: int = LARGO_TITULO, columnas_tabla: dict | None = None) -> None:
    """Dibuja en una tarjeta un gráfico con su título dentro de la figura, su lectura rápida y notas cortas.

    El «?» del glosario (`ayuda`) va en la esquina superior derecha, sobre el título de la figura. Con `tabla` se ofrece «Ver en tabla» con los
    números que alimentan el gráfico. En un mosaico la tarjeta se estira al alto de su fila: el espacio que sobra queda
    entre el gráfico y la lectura. `altura` iguala el alto de los gráficos de una misma fila. `config` es la configuración
    de Plotly del gráfico (rueda del mouse, barra de herramientas); sin ella, la de siempre. `cifra` es una frase grande que
    va en lo alto de la tarjeta, sobre el gráfico (el dato dominante, con el gráfico mostrando solo el resto).
    `largo_titulo` (caracteres por línea del título) se acorta en las tarjetas angostas, como la del mapa de la ficha.
    `columnas_tabla` ajusta columnas de «Ver en tabla» (ayuda, ancho) sobre el formato de siempre.
    """
    if altura:
        fig.update_layout(height=altura)
    _con_titulo(fig, titulo, largo_titulo)
    with st.container(border=True, vertical_alignment="distribute"):
        if cifra:
            st.markdown(f"### {cifra}")
        with st.container(key=f"figura_{key}"):
            st.plotly_chart(fig, key=key, **({"config": config} if config else {}))
            if bajo_figura:  # un control que va pegado bajo el gráfico, antes de la lectura
                bajo_figura()
            if ayuda:  # el «?» queda en la esquina, a la altura del título de la figura
                with st.container(key=f"ayuda_{key}"):
                    st.markdown("&#8203;", help=ayuda)  # solo el ícono (?) del help
        with st.container():
            cp.lectura(texto, key)
            for nota in notas:
                st.caption(nota)
            if tabla is not None:
                with st.expander("Ver en tabla"):
                    st.dataframe(tabla, hide_index=True, column_config={**config_columnas(tabla), **(columnas_tabla or {})})


def encabezado(titulo: str) -> None:
    """Título de página."""
    st.title(titulo)


def pct_por(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Episodios y porcentaje del año por categoría."""
    r = df.groupby(["ANIO", col], dropna=False)["episodios"].sum().reset_index()
    r["pct"] = r["episodios"] / r.groupby("ANIO")["episodios"].transform("sum") * 100
    return r


def capitulos(r: pd.DataFrame, p: ind.Periodo, n: int, pocos: bool, key: str = "g_capitulos",
              altura: int | None = None, periodo: str = "") -> None:
    """Capítulos CIE-10: barras en un año; al comparar, barras base → foco con dos años y minigráficos con tres o más.
    `periodo` («2025», «2021–2024») va al final del título cuando la página lo pide (Hospitales)."""
    top = r[r["ANIO"] == p.foco].nlargest(TOP, "pct")
    titulo = "Capítulos CIE-10 (% de egresos)" + (f" · {periodo}" if periodo else "")
    forma = gr.forma("capitulos", p, n)
    if forma == "barras":
        fila = top.iloc[0]
        texto = tx.lectura("capitulos", p, capitulo=fila["capitulo"], pct=float(fila["pct"]))
        grafico(titulo, gr.barras_h(top, "capitulo", "pct"), texto, key, altura=altura,
                tabla=tabla_humana(top[["ANIO", "capitulo", "episodios", "pct"]]))
        return
    d = r[r["capitulo"].isin(top["capitulo"])]
    texto = lectura_cambio("capitulos", p, cambio(d, "capitulo", p), ("capitulo", "pct"), pocos)
    if forma == "base_foco":
        fig = gr.barras_base_foco(d, "capitulo", "pct", "ANIO", p.base, p.foco)
    else:
        fig = gr.minigraficos(d, "capitulo", "pct", "ANIO")
        altura = None  # los minigráficos necesitan su propio alto: apretados al alto del mosaico no se leen
    grafico(titulo, fig, texto, key, tx.GLOSARIO["barras_base_foco" if forma == "base_foco"
                                                                        else "minigraficos"], altura=altura,
            tabla=tabla_humana(d[["ANIO", "capitulo", "episodios", "pct"]].sort_values(["ANIO", "pct"], ascending=[True, False])))


def tarjetas_complejidad(c: dict, n: dict, p: ind.Periodo, con_severidad: bool = True, clave: str = "complejidad") -> None:
    """Tarjetas de severidad mayor, diagnósticos secundarios promedio y estancia mediana del año foco frente a la base.

    `c` trae por año severidad_mayor (%), diag_secundarios y estancia (mediana); `n`, los egresos por año. Sin severidad
    (ambulatorio) la primera tarjeta dice «No aplica». Van en una fila de KPI (`clave` la nombra) que pasa de línea si no
    caben, en vez de tres columnas fijas que cortan «Diagnósticos secundarios» a 1024 px.
    """
    f, b = c[p.foco], c.get(p.base) if p.base is not None else None
    n_base = n.get(p.base, 0) if p.base is not None else 0
    fila = cp.fila("fpar", clave)
    col = (fila, fila, fila)
    with col[0]:
        if con_severidad:
            cp.tarjeta_kpi("Severidad mayor", f"{tx.numero(f['severidad_mayor'], 1)} %",
                           ind.variacion(f["severidad_mayor"], b and b["severidad_mayor"], "porcentaje", "neutro", n_base),
                           cp.ayuda("severidad"))
        else:
            cp.tarjeta_kpi("Severidad mayor", "No aplica", ind.Variacion("", "neutro", False), cp.ayuda("severidad"))
    with col[1]:
        cp.tarjeta_kpi("Diagnósticos secundarios", tx.numero(f["diag_secundarios"], 2),
                       ind.variacion(f["diag_secundarios"], b and b["diag_secundarios"], "valor", "neutro", n_base),
                       cp.ayuda("diag_secundarios"))
    with col[2]:
        est_f, est_b = f["estancia"], b and b["estancia"]
        var = (ind.variacion(est_f, est_b, "valor", "neutro", n_base) if est_f is not None and est_b is not None
               else ind.Variacion("", "neutro", False))
        cp.tarjeta_kpi("Estancia mediana", tx.estancia(est_f), var, cp.ayuda("mediana"))
    if p.base is not None and b is not None:
        st.caption(f"Variación frente a {p.base}: puntos porcentuales en severidad mayor y % en las otras dos." if con_severidad
                   else f"Variación frente a {p.base}, en %.")


# ---------- Comorbilidad (Análisis › Perfil y Hospitales) ----------
# Cálculo y dibujo compartidos: cada página lee su tabla (`comorbilidad` por región o `comorbilidad_hospital`) y pasa las
# filas ya filtradas; las claves de los gráficos y mosaicos van en `claves` para que no choquen entre páginas.

MAX_COMBINACIONES = 12  # filas del mapa de mortalidad: las combinaciones con más hospitalizaciones
SEVERIDADES = {1: "1 menor", 2: "2 moderada", 3: "3 mayor"}
CLAVES_CR_PERFIL = {"mosaico": "perfil_comorbilidad", "mosaico_combinaciones": "perfil_combinaciones",
                    "pictograma": "a_perfil_pictograma", "edad": "a_perfil_edad", "pares": "a_perfil_combinaciones",
                    "mortalidad": "a_perfil_mortalidad"}
CLAVES_CR_HOSPITAL = {"mosaico": "hosp_cr", "mosaico_combinaciones": "hosp_cr_combinaciones",
                      "pictograma": "g_hosp_pictograma", "edad": "g_hosp_cr_edad", "pares": "g_hosp_cr_combinaciones",
                      "mortalidad": "g_hosp_cr_mortalidad"}


def combinacion_corta(combinacion: str) -> str:
    """Rótulo de una combinación para el eje: nombres cortos unidos por « + »."""
    return " + ".join(tx.NOMBRES_CRONICAS.get(c, c) for c in combinacion.split("+"))


def visibles(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Filas con casos suficientes para dibujarse y si hubo celdas ocultas por tener menos de `MIN_CASOS` episodios."""
    return df[~df["oculta"]], bool(df["oculta"].any())


def calcular_comorbilidad(todas: pd.DataFrame, foco: int, elegidas: tuple[str, ...]) -> dict:
    """Comorbilidad con las enfermedades `elegidas` sobre filas ya filtradas (ANIO, TRAMO_EDAD, SEVERIDAD, COMBINACION,
    episodios, fallecidos): cuántas por hospitalización, cada una por edad, pares y mortalidad del año `foco`; `alguna`
    trae el % con al menos una para cada año presente."""
    todas = ind.contar_seleccionadas(todas, elegidas)
    alguna = {int(a): float(g.loc[g["N_ELEGIDAS"] > 0, "episodios"].sum() / g["episodios"].sum() * 100)
              for a, g in todas.groupby("ANIO", observed=True) if g["episodios"].sum() > 0}
    cr = todas[todas["ANIO"] == foco]
    por_edad = cr.groupby(["TRAMO_EDAD", "COMBINACION"], observed=True)["episodios"].sum().reset_index()
    por_edad["GRUPO_EDAD"] = por_edad["TRAMO_EDAD"].astype(str).map(ind.grupo_edad)
    edad = ind.pct_por_cronica(por_edad.dropna(subset=["GRUPO_EDAD"]), elegidas, "GRUPO_EDAD")
    edad = ind.enmascarar(edad).assign(condicion=lambda x: x["cronica"].map(tx.NOMBRES_CRONICAS))
    pares = ind.pares_frecuentes(cr, elegidas)
    pares = ind.enmascarar(pares).assign(nombre_a=lambda x: x["A"].map(tx.NOMBRES_CRONICAS),
                                         nombre_b=lambda x: x["B"].map(tx.NOMBRES_CRONICAS))
    rec = ind.solo_elegidas(cr[cr["SEVERIDAD"].isin([1, 2, 3])], elegidas)
    mort = ind.mortalidad_cronicas(rec, ["SEVERIDAD"], "ELEGIDAS")
    top = rec.groupby("ELEGIDAS")["episodios"].sum().nlargest(MAX_COMBINACIONES).index
    n_comb = rec["ELEGIDAS"].nunique()
    mort = ind.enmascarar(mort[mort["ELEGIDAS"].isin(top)].assign(  # las etiquetas se arman antes: enmascarar vacía lo numérico
        severidad=lambda x: x["SEVERIDAD"].map(SEVERIDADES), combinacion=lambda x: x["ELEGIDAS"].map(combinacion_corta)))
    dos = ind.mortalidad_cronicas(rec.assign(ELEGIDAS=rec["ELEGIDAS"].where(rec["ELEGIDAS"] == "Ninguna", "Alguna")),
                                  ["SEVERIDAD"], "ELEGIDAS")
    return {"alguna": alguna, "cuantas": ind.cuantas_cronicas(cr), "edad": edad, "pares": pares, "mort": mort,
            "n_comb": n_comb, "dos": dos[dos["episodios"] >= ind.MIN_CASOS].set_index(["ELEGIDAS", "SEVERIDAD"])["mortalidad"]}


def elegir_cronicas(key: str) -> tuple[str, ...]:
    """Selector de las enfermedades que cuentan como comorbilidad (no es un filtro global); devuelve las elegidas en el
    orden de la lista. La elección se comparte entre páginas por `pl.CLAVE_CRONICAS`: cada página tiene su widget `key`."""
    if key not in st.session_state:  # el widget pierde su valor al cambiar de página: se siembra desde la copia
        st.session_state[key] = pl.cronicas_vigentes()
    st.multiselect("Enfermedades que cuentan como comorbilidad", list(tx.NOMBRES_CRONICAS), key=key,
                   format_func=tx.NOMBRES_CRONICAS.get, placeholder="Elige una o más enfermedades",
                   help=tx.GLOSARIO["lista_cronicas"])
    st.caption("Lista de enfermedades crónicas definida por el equipo, con respaldo del MINSAL (GES y Encuesta Nacional de "
               "Salud); las elige quien explora. Se buscan entre los diagnósticos secundarios de cada hospitalización.")
    st.session_state[pl.CLAVE_CRONICAS] = list(st.session_state[key])
    elegidas = set(st.session_state[key])
    return tuple(k for k in tx.NOMBRES_CRONICAS if k in elegidas)


def bloque_comorbilidad(p: ind.Periodo, elegidas: tuple[str, ...], calcular: Callable[[], dict],
                        claves: dict[str, str], periodo: str | None = None) -> str | None:
    """Dibuja el bloque Comorbilidad; devuelve la frase para la respuesta corta (None si no hay datos o elegidas).

    `calcular` hace el cálculo (con su caché y su pantalla de carga) y solo se llama si hay enfermedades elegidas.
    Con `periodo` («2025») cada título termina en « · 2025» (Hospitales); sin él, los títulos de siempre (Análisis).
    """
    def titulo(t: str) -> str:
        return f"{t} · {periodo}" if periodo else t
    if not elegidas:
        st.info("Elige al menos una enfermedad para ver la comorbilidad: el pictograma, los mapas de calor y la "
                "mortalidad se calculan con las que elijas.")
        return None
    d = calcular()
    if p.foco not in d["alguna"]:
        st.info(f"No hay hospitalizaciones con esta selección en {p.foco}.")
        return None
    nombres = tx.cronicas_en_palabras("+".join(elegidas))
    texto = (f"El {tx.numero(d['alguna'][p.foco], 1)} % de las hospitalizaciones de {p.foco} tiene registrada al menos una "
             f"de las enfermedades elegidas ({nombres})")
    if p.modo == "comparar" and p.base in d["alguna"]:
        texto += f", frente al {tx.numero(d['alguna'][p.base], 1)} % de {p.base}"
    con, sin = d["dos"].get(("Alguna", 3)), d["dos"].get(("Ninguna", 3))
    if con is not None and sin is not None:
        texto += (f". Con severidad mayor, el {tx.numero(con, 1)} % de las que tienen alguna termina en fallecimiento, "
                  f"frente al {tx.numero(sin, 1)} % de las que no tienen ninguna (sin ajustar por edad)")
    st.caption(f"Solo hospitalización · año {p.foco}.")
    u = ind.Periodo("un_anio", p.foco, None)
    mosaico = cp.mosaico(claves["mosaico"])
    with mosaico:
        c = gr.repartir_100(d["cuantas"])
        grafico(titulo("De cada 100 hospitalizaciones") if periodo else f"De cada 100 hospitalizaciones ({p.foco})",
                gr.pictograma(d["cuantas"], "hospitalizaciones", "Enfermedades elegidas"),
                tx.lectura("pictograma", u, una=c[ind.CUANTAS_CRONICAS[1]], varias=c[ind.CUANTAS_CRONICAS[2]]),
                claves["pictograma"], cp.ayuda("pictograma"), altura=360)
    with mosaico:
        e, ocultas = visibles(d["edad"])
        if e.empty:
            st.markdown("Con esta selección hay muy pocos casos por grupo de edad.")
            if ocultas:
                st.caption(AVISO_CELDAS)
        else:
            fila = e.loc[e["pct"].idxmax()]
            grafico(titulo("% de hospitalizaciones con cada enfermedad por grupo de edad"),
                    gr.mapa_calor(e, "condicion", "GRUPO_EDAD", "pct"),
                    tx.lectura("cronicas_edad", u, condicion=fila["condicion"], grupo=fila["GRUPO_EDAD"], pct=float(fila["pct"])),
                    claves["edad"], cp.ayuda("mapa_calor"), (AVISO_CELDAS,) if ocultas else (),
                    tabla=tabla_humana(d["edad"][["condicion", "GRUPO_EDAD", "episodios", "pct", "oculta"]],
                                       {"condicion": "Enfermedad", "episodios": "Hospitalizaciones",
                                        "pct": "% con la enfermedad"}))
    with cp.mosaico(claves["mosaico_combinaciones"]):  # fila propia: los mapas de calor necesitan ancho
        with st.container():
            pa, ocultas = visibles(d["pares"])
            if len(elegidas) < 2:
                st.markdown("Con una sola enfermedad elegida no hay pares que mostrar.")
            elif pa.empty:
                st.markdown(tx.POCOS_CASOS)
                if ocultas:
                    st.caption(AVISO_CELDAS)
            else:
                f = pa.loc[pa["episodios"].idxmax()]
                espejo = pa.rename(columns={"nombre_a": "nombre_b", "nombre_b": "nombre_a"})  # matriz simétrica, más fácil de leer
                grafico(titulo("Pares frecuentes (% de hospitalizaciones con las dos)"),
                        gr.mapa_calor(pd.concat([pa, espejo], ignore_index=True), "nombre_a", "nombre_b", "pct"),
                        tx.lectura("pares", u, combinacion=f"{f['A']}+{f['B']}", pct=float(f["pct"])),
                        claves["pares"], cp.ayuda("pares_cronicas"), (AVISO_CELDAS,) if ocultas else (),
                        tabla=tabla_humana(d["pares"][["nombre_a", "nombre_b", "episodios", "pct", "oculta"]],
                                           {"nombre_a": "Enfermedad A", "nombre_b": "Enfermedad B",
                                            "episodios": "Hospitalizaciones", "pct": "% de hospitalizaciones"}))
        with st.container():
            m, ocultas = visibles(d["mort"])
            mayor = m[(m["SEVERIDAD"] == 3) & (m["ELEGIDAS"] != "Ninguna")]
            if mayor.empty or sin is None:
                lect = tx.lectura("mortalidad_cronicas", u, pocos_casos=True)
            else:
                f = mayor.loc[mayor["mortalidad"].idxmax()]
                lect = tx.lectura("mortalidad_cronicas", u, combinacion=f["ELEGIDAS"], mortalidad=float(f["mortalidad"]), ninguna=sin)
            notas = ((f"Se muestran las {MAX_COMBINACIONES} combinaciones con más hospitalizaciones, de {tx.numero(d['n_comb'])}.",)
                     if d["n_comb"] > MAX_COMBINACIONES else ()) + ((AVISO_CELDAS,) if ocultas else ())
            if m.empty:
                st.markdown(tx.POCOS_CASOS)
                if ocultas:
                    st.caption(AVISO_CELDAS)
            else:
                grafico(titulo("Mortalidad (%) por combinación y severidad"), gr.mapa_calor(m, "combinacion", "severidad", "mortalidad"),
                        lect, claves["mortalidad"], cp.ayuda("mapa_calor"), notas,
                        tabla=tabla_humana(d["mort"][["combinacion", "severidad", "episodios", "mortalidad", "oculta"]],
                                           {"combinacion": "Combinación", "severidad": "Severidad",
                                            "episodios": "Hospitalizaciones", "mortalidad": "Mortalidad (%)"}))
    return texto + "."
