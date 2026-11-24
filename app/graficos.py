"""Figuras Plotly del dashboard con el estilo del mockup (sin Streamlit)."""
from __future__ import annotations

import json
import math
import textwrap
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from indicadores import Periodo
from textos import numero

# Paleta categórica (primary, teal, ocre, ciruela) revisada con el validador de daltonismo de la guía de dataviz: las tres
# primeras se distinguen entre sí con cualquier tipo de daltonismo y las cuatro tienen contraste ≥ 3:1 sobre blanco.
# `serie_2` (celeste) no es una categoría: marca el año base o el contexto, junto a un dato en primary.
# Regla de color: el contexto va en gris azulado (`muted`, `text_secondary`); UN solo color de énfasis (`enfasis`, fucsia)
# para lo que hay que leer (año foco, valor destacado, línea foco del índice); el azul oscuro queda para texto y marca.
# El fucsia tiene contraste 4,91:1 sobre blanco, pero con protanopia se acerca al azul principal: por eso el énfasis
# siempre lleva rótulo con el valor o una posición destacada, nunca solo el color.
# Grises y azul medio revalidados (2026-11-23, WCAG y Machado 2009): `muted` #6B7889 (4,49:1 sobre blanco; antes #8A97A8,
# 2,97:1) y `_AZUL_MEDIO` #5B8CC6 (3,49:1; antes #6C9BD2, 2,89:1). Primary y ciruela se confunden con protanopia (ΔE 3,8):
# en las líneas la ciruela va con trazo cortado y toda serie lleva rótulo directo (`estilos_series`).
# Un significado por color en Hospitales: la escala de azules es solo el % de origen del mapa; las camas son barras de un
# solo azul con la ocupación escrita, y las familias o unidades son líneas rotuladas (sin rampa de azules).
COLORES = {
    "primary": "#1D5FAD", "primary_dark": "#0E3A73", "teal": "#0F9384", "ocre": "#BF7414", "ciruela": "#8457B8",
    "serie_2": "#8BBBEA", "enfasis": "#D6197A",
    "bg": "#F3F6FA", "card": "#FFFFFF", "border": "#E2E8F0", "grid": "#E8EDF3", "text": "#142742",
    "text_secondary": "#5A6A80", "muted": "#6B7889", "positive": "#1E9E5A", "negative": "#D14343",
    "warning": "#9A6700",
}
_C = COLORES
_ESCALA = [[0, "#EAF2FB"], [1, _C["primary_dark"]]]
_PALETA = [_C["primary"], _C["teal"], _C["ocre"], _C["ciruela"]]
_AZUL_MEDIO = "#5B8CC6"  # azul medio de la paleta: escalones del pictograma y complejidad mediana del mapa de hospitales
# Años base: rampa de grises azulados, del más claro (el más antiguo) al más oscuro; el último año (foco) va en énfasis.
_RAMPA_BASE = [[0, "#B4C0CE"], [1, _C["text_secondary"]]]


def colores_anios(n: int) -> list[str]:
    """Un color por año (`n` años, del más antiguo al más reciente): grises azulados ordenados para los años base y el
    color de énfasis para el último (el año foco). Con un año base solo, ese año va en `muted`."""
    if n <= 0:
        return []
    if n == 1:
        return [_C["enfasis"]]
    if n == 2:
        return [_C["muted"], _C["enfasis"]]
    from plotly.colors import sample_colorscale, unlabel_rgb
    muestras = sample_colorscale(_RAMPA_BASE, [i / (n - 2) for i in range(n - 1)])
    return ["#{:02X}{:02X}{:02X}".format(*(round(c) for c in unlabel_rgb(m))) for m in muestras] + [_C["enfasis"]]


ALTURA_MOSAICO = 320  # px: el mismo alto para los gráficos del mosaico de Inicio, así las tarjetas de una fila calzan
ALTURA_MAPA_HOSPITAL, ALTURA_MAPA_HOSPITAL_CELULAR = 520, 420  # px: el mapa de la ficha va en una columna angosta; bajo ella, más bajo
ALTURA_MAPA = 720  # px: Chile es largo, el mapa va más alto; ocupa el alto de dos filas del mosaico

_FORMAS = {
    "sexo": ("donut", "barras_100"), "hospitales": ("tabla_ier", "cometa"), "mapa": ("egresos", "variacion"),
}


def forma(grafico: str, p: Periodo, n_anios: int) -> str:
    """Elige la forma del gráfico según el modo y el número de años.

    Capítulos: barras con un año; con dos, barras base → foco; con tres o más, minigráficos de línea. Con un solo año
    nunca hay minigráficos (serían líneas de un punto), aunque el modo sea «comparar».
    """
    comparar = p.modo == "comparar"
    if grafico == "capitulos":
        if not comparar or n_anios <= 1:
            return "barras"
        return "base_foco" if n_anios == 2 else "minigraficos"
    if grafico == "edad":
        return "columnas" if not comparar else ("agrupadas" if n_anios <= 4 else "mapa_calor")
    if grafico not in _FORMAS:
        raise ValueError(f"Gráfico desconocido: {grafico}")
    return _FORMAS[grafico][comparar]


def _base(fig: go.Figure, altura: int = 360) -> go.Figure:
    """Aplica el diseño común: fondo transparente, fuente Inter, leyenda arriba, grilla suave y números chilenos en los ejes."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=altura, separators=",.",
        font=dict(family="Inter, sans-serif", color=_C["text"]), margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=_C["text_secondary"])),
        hoverlabel=dict(font_family="Inter, sans-serif", bgcolor=_C["card"], bordercolor=_C["border"],
                        font_color=_C["text"]))
    # Ejes en segundo plano: marcas en gris azulado, grilla suave; los datos llevan el color.
    ejes = dict(gridcolor=_C["grid"], zerolinecolor=_C["grid"], exponentformat="none", separatethousands=True,
                tickfont=dict(color=_C["text_secondary"]), title_font=dict(color=_C["text_secondary"]))
    fig.update_xaxes(**ejes)
    fig.update_yaxes(**ejes)
    return fig


def _textos(serie: pd.Series, dec: int = 1) -> list[str]:
    """Formatea una serie con separadores chilenos para hover y etiquetas."""
    return [numero(float(v), dec) for v in serie]


def _rango_con_etiquetas(valores: pd.Series, holgura: float = 0.15) -> list[float]:
    """Rango del eje que deja espacio a las etiquetas de valor al final de cada barra, según el signo."""
    lo, hi = min(0.0, float(valores.min())), max(0.0, float(valores.max()))
    ancho = (hi - lo) or 1.0
    return [lo - holgura * ancho if lo < 0 else 0.0, hi + holgura * ancho if hi > 0 else 0.0]


def etiqueta_pct(v: float) -> str:
    """% con los decimales que hagan falta para no leerse «0,0»: 1 decimal desde 1 %, y 2 cifras significativas bajo 1 %.

    Bajo 0,001 no se distingue de cero con decimales útiles: «< 0,001».
    """
    if v >= 1:
        return numero(v, 1)
    for dec, minimo in ((2, 0.1), (3, 0.01), (4, 0.001)):
        if v >= minimo:
            return numero(v, dec)
    return "< 0,001"


def barras_h(df: pd.DataFrame, etiqueta: str, valor: str, dec: int = 1, textos: list[str] | None = None) -> go.Figure:
    """Barras horizontales ordenadas de mayor a menor; `dec` = 0 para conteos. `textos` son las etiquetas a medida de cada
    barra (en el orden de `df`), para magnitudes muy distintas en un mismo gráfico."""
    d = df.sort_values(valor)
    t = [textos[i] for i in [df.index.get_loc(k) for k in d.index]] if textos is not None else _textos(d[valor], dec)
    fig = go.Figure(go.Bar(x=d[valor], y=d[etiqueta], orientation="h", marker=dict(color=_C["primary"], cornerradius=4),
                           text=t, textposition="outside", cliponaxis=False, customdata=t,
                           hovertemplate="%{y}: %{customdata}<extra></extra>"))
    fig.update_xaxes(range=_rango_con_etiquetas(d[valor]))
    return _base(fig, max(240, 28 * len(d) + 60))


def histograma_estancia(df: pd.DataFrame, mediana: int | None, p90: int | None) -> go.Figure:
    """Egresos por día de estancia (`DIAS`, `episodios`), con la mediana (énfasis) y el percentil 90 (gris) marcados."""
    t = _textos(df["episodios"], 0)
    fig = go.Figure(go.Bar(x=df["DIAS"], y=df["episodios"], marker=dict(color=_C["primary"]), customdata=t,
                           hovertemplate="%{x} días: %{customdata} egresos<extra></extra>"))
    for valor, nombre, color, trazo in ((mediana, "Mediana", _C["enfasis"], "solid"), (p90, "P90", _C["text_secondary"], "dash")):
        if valor is not None:
            fig.add_vline(x=valor, line=dict(color=color, width=2, dash=trazo))
            fig.add_annotation(x=valor, y=1, yref="paper", text=f"{nombre}: {numero(valor)}", showarrow=False, xanchor="left",
                               yanchor="bottom", xshift=4, font=dict(color=color, size=12))
    _base(fig)
    fig.update_layout(bargap=0.1, margin=dict(l=10, r=10, t=40, b=10))  # sitio arriba para los rótulos de las líneas
    fig.update_xaxes(title_text="Días de estancia", rangemode="tozero")
    fig.update_yaxes(title_text="Egresos")
    return fig


def rango_estancia(df: pd.DataFrame, grupo: str, tope: int = 30, alto_fila: int = 46) -> go.Figure:
    """Mediana y percentil 90 de la estancia por grupo (`grupo`, `mediana`, `p90`, `texto_mediana`, `texto_p90`): un
    segmento por grupo de la mediana (punto fucsia, como en el histograma) al percentil 90 (punto gris), con los días
    escritos. Sobre `tope` días la base trae tramos: el punto va al inicio del tramo y el texto dice el tramo. Un grupo
    oculto (menos de 30 egresos) no se dibuja. Los grupos van en su orden (de arriba abajo), no ordenados por valor."""
    d = df.dropna(subset=["mediana"])
    fig = go.Figure()
    for _, r in d.iterrows():
        fig.add_trace(go.Scatter(x=[r["mediana"], r["p90"]], y=[r[grupo]] * 2, mode="lines", showlegend=False,
                                 line=dict(color=_C["border"], width=6), hoverinfo="skip"))
    for col, nombre, color, pos in (("mediana", "Mediana", _C["enfasis"], "middle left"),
                                    ("p90", "Percentil 90", _C["text_secondary"], "middle right")):
        fig.add_trace(go.Scatter(x=d[col], y=d[grupo], mode="markers+text", name=nombre, text=d[f"texto_{col}"],
                                 textposition=pos, textfont=dict(size=11, color=color), cliponaxis=False,
                                 marker=dict(color=color, size=11, line=dict(color="white", width=1)),
                                 customdata=d[f"texto_{col}"], hovertemplate=f"%{{y}} · {nombre}: %{{customdata}}<extra></extra>"))
    _base(fig, max(240, alto_fila * len(d) + 90))
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=list(d[grupo]), autorange="reversed",
                     showgrid=False)
    tope_x = max(float(d["p90"].max()) if len(d) else 1.0, 1.0)
    fig.update_xaxes(range=[-0.15 * tope_x, tope_x * 1.3], title_text="Días de estancia")  # sitio para los textos
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), margin=dict(l=10, r=10, t=40, b=10))
    return fig


def _signo(v: float, dec: int = 1) -> str:
    """Diferencia con signo explícito: «+0,2», «−3,1» (un cero redondeado va sin signo)."""
    s = numero(v, dec)
    return s if s.startswith("−") or not any(c in "123456789" for c in s) else "+" + s


def barras_base_foco(df: pd.DataFrame, etiqueta: str, valor: str, anio: str, base, foco) -> go.Figure:
    """Barras base → foco por categoría: la base en gris, el foco en el color de énfasis, rotulado con su valor y la
    diferencia con la base, «16,0 (−3,1)». La categoría con el mayor valor del foco va arriba.

    `anio` es la columna que distingue los dos grupos (dos años, o dos medidas del mismo año) y `base`/`foco` sus valores.
    """
    t = df.pivot_table(index=etiqueta, columns=anio, values=valor, aggfunc="sum", observed=True)
    t = t.reindex(columns=[base, foco]).sort_values(foco, na_position="first")
    b, f = t[base], t[foco]
    rotulos = [numero(float(v), 1) + ("" if pd.isna(d) else f" ({_signo(float(d))})") if pd.notna(v) else ""
               for v, d in zip(f, f - b)]
    y = [str(k) for k in t.index]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=y, x=b, name=str(base), orientation="h", marker=dict(color=_C["muted"], cornerradius=3),
                         customdata=_textos(b), hovertemplate=f"%{{y}} ({base}): %{{customdata}}<extra></extra>"))
    fig.add_trace(go.Bar(y=y, x=f, name=str(foco), orientation="h", marker=dict(color=_C["enfasis"], cornerradius=3),
                         text=rotulos, textposition="outside", cliponaxis=False,
                         constraintext="none",  # sin esto Plotly achica el rótulo al grosor de la barra y no se lee
                         textfont=dict(color=_C["text"], size=11), customdata=_textos(f),
                         hovertemplate=f"%{{y}} ({foco}): %{{customdata}}<extra></extra>"))
    # las barras base y foco de cada categoría van juntas: el foco arriba de la pareja, con su rótulo
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
    fig.update_xaxes(range=_rango_con_etiquetas(pd.concat([b, f]).dropna(), holgura=0.35))
    fig.update_yaxes(type="category")  # categorías (o años) como texto
    _base(fig, max(240, 34 * len(t) + 70))
    # leyenda como texto en una línea: la de Plotly, con etiquetas largas a la izquierda, ponía un año por línea
    leyenda = "   ".join(f"<span style='color:{c}'>■</span> {n}" for n, c in ((base, _C["muted"]), (foco, _C["enfasis"])))
    fig.add_annotation(text=leyenda, xref="paper", yref="paper", x=1, y=1, xanchor="right", yanchor="bottom",
                       showarrow=False, font=dict(size=12, color=_C["text_secondary"]))
    fig.update_layout(showlegend=False, margin=dict(t=30))
    return fig


def _corto(texto: str, largo: int = 30) -> str:
    """Acorta un nombre largo para el título de un minigráfico (el nombre completo queda en el hover)."""
    return texto if len(texto) <= largo else texto[:largo - 1].rstrip() + "…"


def minigraficos(df: pd.DataFrame, etiqueta: str, valor: str, anio: str, columnas: int = 2) -> go.Figure:
    """Minigráficos (small multiples): una línea pequeña por categoría a lo largo de los años, en una grilla de
    `columnas`. La línea va en gris; el último año (foco) es un punto en el color de énfasis con su valor rotulado a la
    derecha, y el primer año lleva su valor en gris a la izquierda. Cada minigráfico tiene su propia escala vertical: se
    lee la forma del cambio y las cifras de los extremos, no el alto entre minigráficos. Ordenados por el valor del foco.
    """
    from plotly.subplots import make_subplots
    anios = sorted(df[anio].unique())
    ultimo = anios[-1]
    orden = (df[df[anio] == ultimo].groupby(etiqueta, observed=True)[valor].sum().sort_values(ascending=False).index)
    cats = [k for k in orden] + [k for k in df[etiqueta].unique() if k not in set(orden)]
    filas = -(-len(cats) // columnas)
    fig = make_subplots(rows=filas, cols=columnas, subplot_titles=[_corto(str(k)) for k in cats],
                        horizontal_spacing=0.14, vertical_spacing=min(0.5 / max(filas, 1), 0.12))
    x = [str(a) for a in anios]  # años como texto
    for i, k in enumerate(cats):
        g = df[df[etiqueta] == k].groupby(anio)[valor].sum().reindex(anios)
        n = len(g)
        lo, hi = float(g.min()), float(g.max())
        holgura = (hi - lo) * 0.25 or abs(hi) * 0.1 or 1.0  # aire arriba y abajo: los rótulos no tocan el título
        rot = [numero(float(v), 1) if j in (0, n - 1) and pd.notna(v) else "" for j, v in enumerate(g)]
        colores = [_C["muted"]] * (n - 1) + [_C["enfasis"]]
        fig.add_trace(go.Scatter(
            x=x, y=g.values, name=str(k), mode="lines+markers+text", text=rot, cliponaxis=False,
            textposition=["middle left"] + ["middle right"] * (n - 1),
            textfont=dict(size=11, color=[_C["text_secondary"]] * (n - 1) + [_C["enfasis"]]),
            line=dict(color=_C["muted"], width=2), marker=dict(color=colores, size=[4] * (n - 1) + [8]),
            customdata=_textos(g), hovertemplate=f"{k} %{{x}}: %{{customdata}}<extra></extra>"),
            row=i // columnas + 1, col=i % columnas + 1)
        fig.update_yaxes(range=[lo - holgura, hi + holgura], row=i // columnas + 1, col=i % columnas + 1)
    _base(fig, 40 + 86 * filas)
    fig.update_layout(showlegend=False, margin=dict(l=34, r=40, t=30, b=10))
    fig.update_annotations(font=dict(size=11, color=_C["text"]))  # títulos de los minigráficos
    # ejes mínimos: solo el primer y el último año abajo de cada minigráfico, sin números en el eje vertical
    fig.update_xaxes(type="category", tickvals=[x[0], x[-1]], showgrid=False, tickfont=dict(size=10), fixedrange=True,
                     range=[-0.6, len(x) - 0.4])
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, fixedrange=True)
    return fig


def donut(df: pd.DataFrame, etiqueta: str, valor: str) -> go.Figure:
    """Anillo de composición con porcentaje y cantidad en el hover."""
    pct = df[valor] / df[valor].sum() * 100
    cd = [f"{numero(float(p), 1)} % ({numero(float(v), 0)})" for p, v in zip(pct, df[valor])]
    fig = go.Figure(go.Pie(labels=df[etiqueta], values=df[valor], hole=0.6, sort=False,
                           marker=dict(colors=_PALETA, line=dict(color=_C["card"], width=2)),
                           texttemplate="%{percent:.1%}", textfont=dict(color="white", size=13),
                           insidetextorientation="horizontal", customdata=cd,
                           hovertemplate="%{label}: %{customdata}<extra></extra>"))
    fig.add_annotation(text=f"<b>{numero(float(df[valor].sum()), 0)}</b><br>egresos", showarrow=False,
                       font=dict(size=14, color=_C["text"]), x=0.5, y=0.5, xref="paper", yref="paper")
    _base(fig, 280)
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.02, x=0.5, xanchor="center"),
                      margin=dict(l=10, r=10, t=10, b=30))  # leyenda abajo: arriba tapaba el anillo
    return fig


def barras_100(df: pd.DataFrame, anio: str, etiqueta: str, valor: str) -> go.Figure:
    """Barras horizontales apiladas al 100 % por año, con el porcentaje dentro de cada tramo."""
    pct = df[valor] / df.groupby(anio)[valor].transform("sum") * 100
    d = df.assign(_pct=pct)
    fig = go.Figure()
    for i, (k, g) in enumerate(d.groupby(etiqueta, sort=False)):
        etq = [numero(float(p), 1) + " %" for p in g["_pct"]]
        cd = [f"{e} ({numero(float(v), 0)})" for e, v in zip(etq, g[valor])]
        fig.add_trace(go.Bar(y=g[anio].astype(str), x=g["_pct"], name=str(k), orientation="h", marker_color=_PALETA[i % 4],
                             marker_line=dict(color=_C["card"], width=2),  # 2 px de separación entre tramos
                             text=etq, textposition="inside", textfont=dict(color="white"), customdata=cd,
                             hovertemplate=f"{k}: %{{customdata}}<extra></extra>"))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(ticksuffix=" %", range=[0, 100])
    fig.update_yaxes(type="category")  # años como texto: con número salían «2.025»
    return _base(fig, 100 + 50 * df[anio].nunique())


def columnas(df: pd.DataFrame, etiqueta: str, valor: str, anio: str | None = None) -> go.Figure:
    """Columnas por categoría; agrupadas por año si se indica `anio` (años base en gris, el foco en énfasis)."""
    fig = go.Figure()
    grupos = [(None, df)] if anio is None else list(df.groupby(anio))
    colores = [_C["primary"]] if anio is None else colores_anios(len(grupos))  # un año: el azul de las demás barras
    for (a, g), color in zip(grupos, colores):
        etq = _textos(g[valor]) if anio is None else None  # con un año, la cifra sobre cada columna
        fig.add_trace(go.Bar(x=g[etiqueta], y=g[valor], name="" if a is None else str(a),
                             marker=dict(color=color, cornerradius=4), text=etq, textposition="outside",
                             cliponaxis=False, textfont=dict(color=_C["text_secondary"]),
                             customdata=_textos(g[valor]), hovertemplate="%{x}: %{customdata}<extra></extra>"))
    fig.update_layout(barmode="group", showlegend=anio is not None, bargap=0.3)
    if anio is None:
        fig.update_yaxes(range=_rango_con_etiquetas(df[valor]))
    return _base(fig)


LARGO_ETIQUETA_FILA = 24  # caracteres por línea del rótulo de una fila del mapa de calor; más largo se parte en dos
ALTO_FILA_PARTIDA = 30  # px por fila cuando algún rótulo va en dos líneas, para que no se toquen entre sí


def mapa_calor(df: pd.DataFrame, fila: str, columna: str, valor: str) -> go.Figure:
    """Mapa de calor fila × columna con el valor en cada celda.

    Un rótulo de fila largo («Diabetes + Hipertensión + EPOC + ERC») se parte en líneas de `LARGO_ETIQUETA_FILA`
    caracteres: en una tarjeta angosta, Plotly no le da más margen y se cortaba por la izquierda. Si hay rótulos partidos,
    la figura crece para que cada fila tenga sitio para dos líneas.
    """
    t = df.pivot_table(index=fila, columns=columna, values=valor, aggfunc="sum")
    txt = [[numero(float(v), 1) for v in r] for r in t.values]
    fig = go.Figure(go.Heatmap(z=t.values, x=[str(c) for c in t.columns], y=list(t.index), colorscale=_ESCALA,
                               text=txt, texttemplate="%{text}", customdata=txt,
                               hovertemplate="%{y} · %{x}: %{customdata}<extra></extra>"))
    _base(fig)
    # filas y columnas como texto: si son años, con eje numérico salían «2.024»
    fig.update_xaxes(type="category")
    fig.update_yaxes(type="category")
    filas = [str(f) for f in t.index]
    if any(len(f) > LARGO_ETIQUETA_FILA for f in filas):
        partidas = ["<br>".join(textwrap.wrap(f, LARGO_ETIQUETA_FILA, break_on_hyphens=False)) or f for f in filas]
        fig.update_yaxes(tickmode="array", tickvals=list(t.index), ticktext=partidas)
        fig.update_layout(height=max(fig.layout.height, ALTO_FILA_PARTIDA * len(filas) + 100))
    return fig


# --- camas por unidad (REM20, página Hospitales) -----------------------------------------------------------------------
# Ninguno de estos gráficos usa el color para una cantidad: las camas son el largo de la barra (un solo azul) y la ocupación
# se escribe como número en su columna. Las series (familias o unidades) van en líneas con rótulo directo; el color solo
# ayuda a seguir cada línea y nunca dice «más» ni «mejor». Así el azul en escala queda solo para el mapa de origen.
LARGO_ETIQUETA_UNIDAD = 34  # caracteres por línea del rótulo de una unidad; más largo se parte, nunca se corta
ALTO_BARRA_UNIDAD = 24  # px por fila del gráfico de unidades (más si algún rótulo va en dos líneas)
ALTO_MAX_UNIDADES = 640  # px: con muchas unidades la figura no crece más (salvo lo justo para que los rótulos no se monten)
DOMINIO_BARRAS = 0.8  # fracción del ancho para las barras; el resto es la columna «Ocupación»


def _partir(texto: str, largo: int) -> str:
    return "<br>".join(textwrap.wrap(texto, largo, break_on_hyphens=False)) or texto


def _tope_ocupacion(valores) -> float:
    v = pd.Series(valores, dtype=float).dropna()
    return max(100.0, float(v.max())) if not v.empty else 100.0


def _pct_columna(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{numero(float(v), 0)} %"


def barras_unidades(filas: pd.DataFrame) -> go.Figure:
    """Barras horizontales de camas por unidad (o familia), con la ocupación del año escrita a la derecha. Con una columna
    `color`, cada barra lleva el de su familia (o unidad), el mismo que en las líneas de Camas; sin ella, un solo azul.

    `filas` viene en el orden de dibujo (de arriba abajo) con `clave` (única), `etiqueta`, `familia` (True en las filas
    que solo nombran una familia, sin barra), `camas`, `ocupacion` (vacía sin días-cama disponibles: se escribe «—») y
    `hover`. La ocupación no es un tono: entre 75 y 100 % todos los azules se parecían y «sin dato» se confundía con
    «poco ocupada». Los rótulos largos se parten en líneas de `LARGO_ETIQUETA_UNIDAD`; nada se corta.
    """
    u = filas[~filas["familia"]]
    fig = go.Figure()
    # las filas de familia van como barras de largo 0: así su rótulo aparece en el eje, en su lugar
    fig.add_trace(go.Bar(y=filas.loc[filas["familia"], "clave"], x=[0] * int(filas["familia"].sum()), name="familias",
                         orientation="h", hoverinfo="skip", showlegend=False, marker_color="rgba(0,0,0,0)"))
    fig.add_trace(go.Bar(y=u["clave"], x=u["camas"], name="camas", orientation="h",
                         text=[numero(float(v), 1 if v < 10 else 0) for v in u["camas"]], textposition="outside",
                         cliponaxis=False, constraintext="none", textfont=dict(color=_C["text"], size=11),
                         customdata=u["hover"], hovertemplate="%{customdata}<extra></extra>",
                         marker=dict(color=list(u["color"]) if "color" in u else _C["primary"], cornerradius=3)))
    for clave, ocupacion in zip(u["clave"], u["ocupacion"]):  # columna de la ocupación, alineada a la derecha
        fig.add_annotation(x=1, xref="paper", y=clave, yref="y", text=_pct_columna(ocupacion), showarrow=False,
                           xanchor="right", font=dict(size=11, color=_C["text"]))
    fig.add_annotation(x=1, xref="paper", y=1, yref="paper", yanchor="bottom", xanchor="right", text="Ocupación",
                       showarrow=False, font=dict(size=11, color=_C["text_secondary"]))
    textos = []
    for e, es_familia in zip(filas["etiqueta"], filas["familia"]):
        partido = _partir(str(e), LARGO_ETIQUETA_UNIDAD)
        textos.append(f"<b>{partido}</b>" if es_familia else partido)
    dos_lineas = sum("<br>" in t for t in textos)
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=list(filas["clave"]), autorange="reversed",
                     tickmode="array", tickvals=list(filas["clave"]), ticktext=textos, tickfont=dict(size=12),
                     showgrid=False)
    fig.update_xaxes(range=_rango_con_etiquetas(u["camas"] if not u.empty else pd.Series([1.0]), holgura=0.22),
                     showticklabels=False, showgrid=False, zeroline=False, domain=[0, DOMINIO_BARRAS])
    alto = ALTO_BARRA_UNIDAD * len(filas) + 14 * dos_lineas + 60
    # tope de alto, pero nunca menos de 20 px por fila (14 más por rótulo partido): los rótulos no se montan
    _base(fig, min(max(alto, 200), max(ALTO_MAX_UNIDADES, 20 * len(filas) + 14 * dos_lineas + 60)))
    fig.update_layout(showlegend=False, barmode="overlay", bargap=0.25, margin=dict(l=10, r=10, t=24, b=10))
    return fig


# Camas (Hospitales): nueve colores, uno por familia de unidades (y, con una familia elegida, uno por unidad). Elegidos con
# la paleta de Okabe-Ito ampliada y un script (WCAG 2 y Machado 2009 con ΔE CIELAB, 2026-11-23): todos pasan 3:1 sobre
# blanco y sobre el fondo (el más claro, el verde, 3,42 y 3,16), el par más cercano está a ΔE 24,5 con visión normal y a
# 17,5 con deuteranopia o protanopia, y ninguno se acerca al fucsia del hospital (ΔE ≥ 30). Todas las líneas van sólidas y
# del mismo grosor: el color dice la familia y nada más (y cada línea lleva además su nombre al final).
PALETA_CAMAS = ("#0072B2", "#D55E00", "#009E73", "#882255", "#00838F", "#7A4A1E", "#222222", "#332288", "#0E3A73")
GROSOR_CAMAS = 2.5


def _estilos(nombres: list[str], colores: dict[str, str] | None) -> list[tuple[str, str, float]]:
    """Con `colores` (nombre → color), todas sólidas y del mismo grosor; sin ellos, `estilos_series`."""
    if colores is None:
        return estilos_series(nombres)
    return [(colores.get(str(n), PALETA_CAMAS[i % len(PALETA_CAMAS)]), "solid", GROSOR_CAMAS) for i, n in enumerate(nombres)]


def estilos_series(nombres: list[str]) -> list[tuple[str, str, float]]:
    """(color, trazo, grosor) de cada línea, en el orden de `nombres` (de la serie más grande a la más chica).

    Las 4 primeras toman la paleta categórica (la cuarta, ciruela, con trazo cortado: con protanopia se confunde con el azul
    principal) y las demás van en gris, más delgadas. «Otras…» siempre en gris punteado. El fucsia nunca: es del hospital.
    """
    estilos, i = [], 0
    for n in nombres:
        if str(n).startswith(("Otras", "Otros")):
            estilos.append((_C["muted"], "dot", 1.5))
        elif i < len(_PALETA):
            estilos.append((_PALETA[i], "dash" if i == 3 else "solid", 2.5))
            i += 1
        else:
            estilos.append((_C["muted"], "solid", 1.5))
    return estilos


ALTO_ROTULO = 15  # px que ocupa un rótulo directo de una línea; dos rótulos nunca quedan más cerca que esto
LARGO_ROTULO_LINEA = 18  # caracteres por línea de un rótulo directo; más largo va en dos líneas


def _repartir_rotulos(ys: list[float], separacion: float, lo: float, hi: float) -> list[float]:
    """Posiciones de los rótulos (mismo orden que `ys`) lo más cerca de su línea, separadas al menos `separacion`."""
    orden = sorted(range(len(ys)), key=lambda i: ys[i])
    pos = [ys[i] for i in orden]
    for k in range(1, len(pos)):  # de abajo arriba: cada rótulo, al menos `separacion` sobre el anterior
        pos[k] = max(pos[k], pos[k - 1] + separacion)
    if pos and pos[-1] > hi:  # si el de arriba se sale, se baja todo el bloque desde arriba
        pos[-1] = hi
        for k in range(len(pos) - 2, -1, -1):
            pos[k] = min(pos[k], pos[k + 1] - separacion)
    pos = [max(p, lo) for p in pos]
    salida = [0.0] * len(ys)
    for k, i in enumerate(orden):
        salida[i] = pos[k]
    return salida


def _rotulos_directos(fig: go.Figure, finales: list[tuple[str, int, float, str]], rango: tuple[float, float],
                      alto: int, margen_vertical: int) -> None:
    """Rótulo con el nombre de cada serie al final de su línea (en su color), unido a su último punto por un trazo fino.

    `finales` = (nombre, posición del último punto en el eje de categorías, último valor, color). La posición va como
    índice: en un eje de categorías Plotly toma una `x` con forma de número («2025») como posición, no como nombre. Los rótulos se reparten para no montarse; el margen derecho crece según el
    rótulo más largo, así nada se corta. Reemplaza la leyenda: no hay que ir y volver entre colores y nombres.
    """
    lo, hi = rango
    unidad = (hi - lo) / max(alto - margen_vertical, 1)  # valor del eje por px
    partidos = [_partir(n, LARGO_ROTULO_LINEA) for n, *_ in finales]
    lineas = max((p.count("<br>") + 1 for p in partidos), default=1)
    ys = _repartir_rotulos([y for _, _, y, _ in finales], ALTO_ROTULO * lineas * unidad, lo, hi)
    for (_, x_final, y, color), texto, y_rotulo in zip(finales, partidos, ys):
        fig.add_annotation(x=x_final, y=y, xref="x", yref="y", text=texto, showarrow=True, arrowhead=0, arrowwidth=1,
                           arrowcolor=color, axref="pixel", ax=10, ayref="y", ay=y_rotulo, xanchor="left", align="left",
                           font=dict(size=10.5, color=color), standoff=2)
    largo = max((len(l) for p in partidos for l in p.split("<br>")), default=0)
    # ~6 px por carácter: a 400 px de ancho el área de las líneas queda en ~180 px con el rótulo más largo (17 caracteres)
    fig.update_layout(margin=dict(r=18 + int(6 * largo)))


def lineas_camas(e: pd.DataFrame, columna: str, destacados: list[int] | None = None,
                 colores: dict[str, str] | None = None) -> go.Figure:
    """Camas por serie y año (`ANIO`, `columna`, `camas`): una línea por familia (o por unidad) con rótulo directo.

    Reemplaza las áreas apiladas: ahí solo se leía la capa de abajo y el total, y 9 familias en 9 azules no se distinguían.
    Las series vienen en el orden en que se colorean (de más a menos camas); la pandemia (2020–2021) va en una franja gris y
    los años elegidos en la barra lateral (`destacados`), en una franja azul suave. El eje x es siempre 2019–2025.
    """
    t = e.pivot_table(index="ANIO", columns=columna, values="camas", aggfunc="sum", sort=False).fillna(0.0).sort_index()
    nombres = list(dict.fromkeys(e[columna]))
    t = t.reindex(columns=nombres)
    t = t.where(t.sum(axis=1) > 0)  # un año sin ninguna cama es un año sin REM20 del hospital: sin punto, no en cero
    x = [str(int(a)) for a in t.index]
    fig = go.Figure()
    finales = []
    for n, (color, trazo, grosor) in zip(nombres, _estilos(nombres, colores)):
        cd = [f"{numero(float(v), 1)} camas" if pd.notna(v) else "sin datos del REM20" for v in t[n]]
        fig.add_trace(go.Scatter(x=x, y=t[n], name=str(n), mode="lines+markers", line=dict(color=color, dash=trazo, width=grosor),
                                 marker=dict(color=color, size=5), customdata=cd, connectgaps=False,
                                 hovertemplate=f"{n} · %{{x}}: %{{customdata}}<extra></extra>"))
        con = t[n].dropna()
        if not con.empty:
            finales.append((str(n), x.index(str(int(con.index[-1]))), float(con.iloc[-1]), color))
    tope = float(t.max().max()) if t.notna().any().any() else 1.0
    rango = (0.0, (tope or 1.0) * 1.1)
    alto = max(340, 30 * len(nombres) + 110)  # 9 familias: ~380 px, los rótulos de dos líneas no se aprietan
    _base(fig, alto)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x, showgrid=False)
    # sin título de eje: le quitaba 30 px al gráfico en un celular; el título y el hover dicen que son camas disponibles
    fig.update_yaxes(rangemode="tozero", range=list(rango))
    fig.update_layout(showlegend=False, margin=dict(l=10, t=30, b=10))
    _franjas_anios(fig, x, destacados or [])
    _rotulos_directos(fig, finales, rango, alto, 30 + 10 + 30)
    return fig


def _franjas_anios(fig: go.Figure, x: list[str], destacados: list[int]) -> None:
    """Franja gris de la pandemia (2020–2021) y franja azul suave de los años elegidos, en un eje de años como texto."""
    pos = {a: i for i, a in enumerate(x)}
    pandemia = [pos[a] for a in ("2020", "2021") if a in pos]  # solo si cae en lo que se ve (uno o los dos años)
    if pandemia:
        fig.add_vrect(x0=min(pandemia) - 0.5, x1=max(pandemia) + 0.5, fillcolor=_C["grid"], opacity=0.6, line_width=0,
                      layer="below", annotation_text="Pandemia", annotation_position="top left",
                      annotation_font=dict(size=11, color=_C["text_secondary"]))
    elegidos = [pos[str(a)] for a in destacados if str(a) in pos]
    if elegidos:
        a0, a1 = min(elegidos), max(elegidos)
        texto = x[a0] if a0 == a1 else f"{x[a0]}–{x[a1]}"
        fig.add_vrect(x0=a0 - 0.5, x1=a1 + 0.5, fillcolor=_C["primary"], opacity=0.07, line_width=0, layer="below",
                      annotation_text=texto, annotation_position="top right", annotation_yshift=-14,  # bajo «Pandemia»: no chocan en un celular
                      annotation_font=dict(size=11, color=_C["primary"]))


def lineas_ocupacion(m: pd.DataFrame, colores: dict[str, str] | None = None) -> go.Figure:
    """Ocupación mensual del año por unidad (`fila` categórica en orden, `MES`, `ocupacion`): una línea por unidad.

    Reemplaza el mapa de calor: la pregunta «¿qué meses estuvo más llena cada unidad?» es de forma en el tiempo, y se lee
    mejor como posición en una línea que como tono (con valores de 85 a 98 % el calor era un solo azul). El eje y va fijo
    de 0 a 100 % (o hasta el mayor valor, si pasa de 100), con una guía en 100 %. Un mes sin días-cama queda sin punto.
    """
    t = m.pivot_table(index="fila", columns="MES", values="ocupacion", aggfunc="first", observed=False, dropna=False)
    t = t.reindex(columns=range(1, 13))
    nombres = [str(f) for f in t.index]
    x = list(MESES_CORTOS)
    fig = go.Figure()
    finales = []
    for n, (_, fila), (color, trazo, grosor) in zip(nombres, t.iterrows(), _estilos(nombres, colores)):
        cd = [f"{numero(float(v), 1)} %" if pd.notna(v) else "sin días-cama" for v in fila]
        fig.add_trace(go.Scatter(x=x, y=list(fila.values), name=n, mode="lines+markers", connectgaps=False,
                                 line=dict(color=color, dash=trazo, width=grosor), marker=dict(color=color, size=5),
                                 customdata=cd, hovertemplate=f"{n} · %{{x}}: %{{customdata}}<extra></extra>"))
        ultimo = fila.dropna()
        if not ultimo.empty:
            finales.append((n, int(ultimo.index[-1]) - 1, float(ultimo.iloc[-1]), color))
    tope = _tope_ocupacion(t.values.ravel())
    rango = (0, tope * 1.05)
    alto = max(320, ALTO_ROTULO * 2 * len(nombres) + 80)
    _base(fig, alto)
    fig.add_hline(y=100, line=dict(color=_C["muted"], dash="dot", width=1))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x, showgrid=False, tickfont=dict(size=11))
    fig.update_yaxes(range=list(rango), ticksuffix=" %")
    fig.update_layout(showlegend=False, margin=dict(l=10, t=20, b=10))
    _rotulos_directos(fig, finales, rango, alto, 20 + 10 + 30)
    return fig


PANDEMIA = ((2020, 3), (2021, 12))  # meses de la franja «Pandemia» (marzo de 2020 a diciembre de 2021)


def eje_meses(anios: list[int]) -> tuple[list[str], dict[tuple[int, int], int], list[str], list[str]]:
    """Eje de categorías con los meses de los años elegidos, y solo esos: (etiquetas, posición de cada (año, mes), marcas
    del eje y su texto).

    Con un año, las 12 marcas son los meses («ene» … «dic»); con varios, una marca por año en su enero. Entre dos años
    elegidos que no son seguidos (2019 y 2021) va una categoría vacía: la línea se corta y no une años con otros en medio.
    """
    anios = sorted({int(a) for a in anios})
    x, pos = [], {}
    for i, a in enumerate(anios):
        if i and a != anios[i - 1] + 1:
            x.append(" " * i)  # corte entre años no seguidos: una categoría vacía sin punto
        for mes in range(1, 13):
            pos[(a, mes)] = len(x)
            x.append(f"{MESES_CORTOS[mes - 1]} {a}")
    if len(anios) == 1:
        return x, pos, list(x), list(MESES_CORTOS)
    return x, pos, [f"{MESES_CORTOS[0]} {a}" for a in anios], [str(a) for a in anios]


def _franja_pandemia_meses(fig: go.Figure, pos: dict[tuple[int, int], int]) -> None:
    """Franja gris «Pandemia» sobre los meses de marzo de 2020 a diciembre de 2021 que están en el eje (ninguna si no hay)."""
    (a0, m0), (a1, m1) = PANDEMIA
    dentro = sorted(k for (a, m), k in pos.items() if (a0, m0) <= (a, m) <= (a1, m1))
    if not dentro:
        return
    tramos, inicio = [], dentro[0]  # meses seguidos en el eje (un corte entre años separa la franja)
    for prev, k in zip(dentro, dentro[1:] + [None]):
        if k != prev + 1:
            tramos.append((inicio, prev))
            inicio = k
    for i, (d, h) in enumerate(tramos):
        fig.add_vrect(x0=d - 0.5, x1=h + 0.5, fillcolor=_C["grid"], opacity=0.6, line_width=0, layer="below",
                      **(dict(annotation_text="Pandemia", annotation_position="top left",
                              annotation_font=dict(size=11, color=_C["text_secondary"])) if i == 0 else {}))


def _ejes_meses(fig: go.Figure, x: list[str], marcas: list[str], textos: list[str]) -> None:
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x, showgrid=False, tickmode="array",
                     tickvals=marcas, ticktext=textos, tickfont=dict(size=11))


def serie_meses(df: pd.DataFrame, columna: str, anios: list[int], nombre: str, color: str, dec: int = 0,
                sufijo: str = "") -> go.Figure:
    """Una serie mensual (`mes` fecha, `columna`) en los meses de los años elegidos y solo esos (regla de años de
    Hospitales): con un año, sus 12 meses; con varios, los meses de esos años seguidos, con un corte entre años no
    seguidos. Un mes sin dato queda sin punto, nunca en 0. La franja de la pandemia va solo si cae en lo que se ve."""
    x, pos, marcas, textos = eje_meses(anios)
    y = [None] * len(x)
    for mes, v in zip(df["mes"], df[columna]):
        k = pos.get((mes.year, mes.month))
        if k is not None and pd.notna(v):
            y[k] = float(v)
    cd = ["" if not e.strip() else (f"{numero(v, dec)}{sufijo}" if v is not None else "sin dato") for e, v in zip(x, y)]
    fig = go.Figure(go.Scatter(x=x, y=y, name=nombre, mode="lines+markers", connectgaps=False,
                               line=dict(color=color, width=2.5), marker=dict(color=color, size=4 if len(anios) > 2 else 6),
                               customdata=cd, hovertemplate="%{x}: %{customdata}<extra></extra>"))
    _base(fig)
    _franja_pandemia_meses(fig, pos)
    _ejes_meses(fig, x, marcas, textos)
    fig.update_yaxes(rangemode="tozero", ticksuffix=sufijo)
    fig.update_layout(showlegend=False)
    return fig


def lineas_ocupacion_periodo(m: pd.DataFrame, anios: list[int], colores: dict[str, str] | None = None) -> go.Figure:
    """Ocupación mensual por unidad en los meses de todos los años elegidos (`fila`, `ANIO`, `MES`, `ocupacion`).

    Como `lineas_ocupacion`, pero el eje x recorre los meses de cada año elegido (`eje_meses`: un corte entre años no
    seguidos) con una marca por año y la franja de la pandemia si cae en lo que se ve.
    """
    anios = sorted(anios)
    x, pos, marcas, textos = eje_meses(anios)
    nombres = [str(f) for f in dict.fromkeys(m["fila"].astype(str))]
    fig = go.Figure()
    finales = []
    for n, (color, trazo, grosor) in zip(nombres, _estilos(nombres, colores)):
        y = [None] * len(x)
        for _, r in m[m["fila"].astype(str) == n].iterrows():
            k = pos.get((int(r["ANIO"]), int(r["MES"])))
            if k is not None and pd.notna(r["ocupacion"]):
                y[k] = float(r["ocupacion"])
        cd = ["" if not v.strip() else (f"{numero(yy, 1)} %" if yy is not None else "sin días-cama") for v, yy in zip(x, y)]
        fig.add_trace(go.Scatter(x=x, y=y, name=n, mode="lines+markers", connectgaps=False,
                                 line=dict(color=color, dash=trazo, width=grosor), marker=dict(color=color, size=3),
                                 customdata=cd, hovertemplate=f"{n} · %{{x}}: %{{customdata}}<extra></extra>"))
        con = [(i, v) for i, v in enumerate(y) if v is not None]
        if con:
            finales.append((n, con[-1][0], con[-1][1], color))
    valores = m["ocupacion"].to_numpy(dtype=float) if len(m) else []
    tope = _tope_ocupacion(valores)
    rango = (0, tope * 1.05)
    alto = max(320, ALTO_ROTULO * 2 * len(nombres) + 80)
    _base(fig, alto)
    fig.add_hline(y=100, line=dict(color=_C["muted"], dash="dot", width=1))
    for a in anios[1:]:  # una línea fina al empezar cada año
        fig.add_vline(x=pos[(a, 1)] - 0.5, line=dict(color=_C["border"], width=1))
    _franja_pandemia_meses(fig, pos)
    _ejes_meses(fig, x, marcas, textos)
    fig.update_yaxes(range=list(rango), ticksuffix=" %")
    fig.update_layout(showlegend=False, margin=dict(l=10, t=20, b=10))
    _rotulos_directos(fig, finales, rango, alto, 20 + 10 + 30)
    return fig


def _formato(v, dec: int, sufijo: str) -> str:
    return "sin dato" if v is None or pd.isna(v) else f"{numero(float(v), dec)}{sufijo}"


def lineas_anios(df: pd.DataFrame, serie: str, valor: str, anios: list[int], dec: int = 1, sufijo: str = "",
                 colores: dict[str, str] | None = None, alto: int | None = None) -> go.Figure:
    """Una línea por serie a lo largo de los años elegidos (`ANIO`, `serie`, `valor`), con rótulo directo al final.

    Es la forma «varios años» de Hospitales: el eje x lleva solo los años elegidos, como texto (2019, 2021 y 2025 quedan
    seguidos y rotulados), y un año sin dato (el hospital no informa, o la celda tiene menos de 30 egresos) queda sin
    punto: nunca en 0. Las series vienen en el orden en que se colorean (`estilos_series`); `colores` fija el color de
    alguna (por ejemplo la mediana en énfasis). El eje y parte de 0.
    """
    x = [str(int(a)) for a in sorted(anios)]
    nombres = list(dict.fromkeys(df[serie].astype(str)))
    t = (df.assign(**{serie: df[serie].astype(str)})
         .pivot_table(index="ANIO", columns=serie, values=valor, aggfunc="first", dropna=False)
         .reindex(index=sorted(anios), columns=nombres))
    fig = go.Figure()
    finales = []
    for n, (color, trazo, grosor) in zip(nombres, estilos_series(nombres)):
        color = (colores or {}).get(n, color)
        y = [None if pd.isna(v) else float(v) for v in t[n]]
        cd = [_formato(v, dec, sufijo) for v in y]
        fig.add_trace(go.Scatter(x=x, y=y, name=n, mode="lines+markers", connectgaps=False,
                                 line=dict(color=color, dash=trazo, width=grosor), marker=dict(color=color, size=6),
                                 customdata=cd, hovertemplate=f"{n} · %{{x}}: %{{customdata}}<extra></extra>"))
        con = [(i, v) for i, v in enumerate(y) if v is not None]
        if con:
            finales.append((n, con[-1][0], con[-1][1], color))
    tope = float(t.max().max()) if t.notna().any().any() else 1.0
    rango = (0.0, (tope or 1.0) * 1.12)
    alto = alto or max(320, ALTO_ROTULO * 2 * len(nombres) + 90)
    _base(fig, alto)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x, showgrid=False)
    fig.update_yaxes(rangemode="tozero", range=list(rango), ticksuffix=sufijo)
    fig.update_layout(showlegend=False, margin=dict(l=10, t=24, b=10))
    _rotulos_directos(fig, finales, rango, alto, 24 + 10 + 30)
    return fig


def paneles_anios(df: pd.DataFrame, indicadores: list[str], anios: list[int], nombre_hospital: str,
                  nombre_referencia: str, columnas: int = 2) -> go.Figure:
    """Paneles pequeños (small multiples), uno por indicador, con dos líneas año a año: el hospital (énfasis, continua) y
    la referencia (gris, cortada). `df` = (`ANIO`, `indicador`, `lado` «hospital»/«referencia», `valor`, `texto` del
    hover). Cada panel tiene su propia escala (se leen las formas y las cifras, no el alto entre paneles); un año sin dato
    queda sin punto. Una sola leyenda arriba con los dos lados."""
    from plotly.subplots import make_subplots
    x = [str(int(a)) for a in sorted(anios)]
    filas = math.ceil(len(indicadores) / columnas)
    fig = make_subplots(rows=filas, cols=columnas, subplot_titles=indicadores, vertical_spacing=0.6 / max(filas, 1) / 2,
                        horizontal_spacing=0.12)
    lados = (("hospital", nombre_hospital, _C["enfasis"], "solid"), ("referencia", nombre_referencia, _C["muted"], "dash"))
    for k, indicador in enumerate(indicadores):
        fila, col = k // columnas + 1, k % columnas + 1
        d = df[df["indicador"] == indicador]
        for lado, nombre, color, trazo in lados:
            s = d[d["lado"] == lado].set_index("ANIO").reindex(sorted(anios))
            y = [None if pd.isna(v) else float(v) for v in s["valor"]]
            cd = ["sin dato" if v is None else str(t) for v, t in zip(y, s["texto"])]
            fig.add_trace(go.Scatter(x=x, y=y, name=nombre, legendgroup=lado, showlegend=k == 0, mode="lines+markers",
                                     connectgaps=False, line=dict(color=color, dash=trazo, width=2.5 if lado == "hospital" else 2),
                                     marker=dict(color=color, size=6), customdata=cd,
                                     hovertemplate=f"{nombre} · %{{x}}: %{{customdata}}<extra></extra>"), row=fila, col=col)
    alto = 190 * filas + 90
    _base(fig, alto)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=x, showgrid=False, tickfont=dict(size=10))
    fig.update_yaxes(tickfont=dict(size=10), nticks=4)
    fig.update_annotations(font=dict(size=12, color=_C["text"]))
    # la leyenda va sobre los títulos de los paneles de arriba (~26 px por encima del área de gráficos)
    fig.update_layout(margin=dict(l=10, r=10, t=70, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1 + 26 / (alto - 80), x=0))
    return fig


# Líneas de la serie de Inicio: (columna, nombre, color, trazo)
SERIE_INICIO = (("todos", "Todos los hospitales", _C["primary"], "solid"), ("panel", "Panel estable", _C["serie_2"], "dash"))


def serie_mensual(df: pd.DataFrame, destacados: list[int], rango: tuple[int, int] | None = None,
                  series: tuple[tuple[str, str, str, str], ...] = SERIE_INICIO) -> go.Figure:
    """Serie mensual con pandemia y años destacados; por omisión, todos los hospitales y el panel.

    `series` = (columna, nombre, color, trazo) de cada línea: la de un solo hospital pasa solo la suya. `rango` = (primer
    año, último año): el eje abre en esos años; los datos de todos los años siguen cargados y el doble clic vuelve a
    mostrarlos.
    """
    fig = go.Figure()
    for col, nombre, color, dash in series:
        fig.add_trace(go.Scatter(x=df["mes"], y=df[col], name=nombre, mode="lines", line=dict(color=color, dash=dash),
                                 customdata=_textos(df[col], 0), hovertemplate="%{x|%m/%Y}: %{customdata}<extra></extra>"))
    fig.add_vrect(x0="2020-03-01", x1="2021-12-31", fillcolor=_C["grid"], opacity=0.6, line_width=0,
                  layer="below", annotation_text="Pandemia", annotation_position="top left")
    for a in destacados:
        fig.add_vrect(x0=f"{a}-01-01", x1=f"{a}-12-31", fillcolor=_C["primary"], opacity=0.05, line_width=0,
                      layer="below", annotation_text=str(a), annotation_position="top left")
    fig.update_xaxes(tickformat="%Y")
    if rango:
        visibles = df[df["mes"].dt.year.between(*rango)][[c for c, *_ in series]]
        fig.update_xaxes(range=[f"{rango[0]}-01-01", f"{rango[1]}-12-31"],
                         tickformat="%m/%Y" if rango[0] == rango[1] else "%Y")
        if visibles.notna().any().any():  # el eje y también se ajusta a los años elegidos
            lo, hi = float(visibles.min().min()), float(visibles.max().max())
            holgura = (hi - lo) * 0.1 or hi * 0.1 or 1.0
            fig.update_yaxes(range=[max(0.0, lo - holgura), hi + holgura])
    return _base(fig)


def cometa(df: pd.DataFrame) -> go.Figure:
    """Cometa casemix-IER por hospital: del año base (gris) al año foco (énfasis, con el nombre rotulado)."""
    fig = go.Figure()
    for r in df.itertuples():
        fig.add_trace(go.Scatter(x=[r.casemix_base, r.casemix_foco], y=[r.ier_base, r.ier_foco], mode="lines",
                                 line=dict(color=_C["muted"], width=1.5), opacity=0.6, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=df["casemix_base"], y=df["ier_base"], mode="markers", name="Año base",
                             marker=dict(color=_C["muted"], size=6), text=df["nombre"],
                             hovertemplate="%{text} (base)<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["casemix_foco"], y=df["ier_foco"], mode="markers+text", name="Año foco",
                             marker=dict(color=_C["enfasis"], size=11), text=df["nombre"], textposition="top center",
                             textfont=dict(color=_C["text"], size=11),
                             customdata=list(zip(_textos(df["casemix_foco"], 2), _textos(df["ier_foco"], 2))),
                             hovertemplate="%{text}<br>Casemix %{customdata[0]} · IER %{customdata[1]}<extra></extra>"))
    fig.add_hline(y=1, line=dict(color=_C["muted"], dash="dot"), annotation_text="lo esperado")
    fig.update_xaxes(title="Casemix (complejidad)")
    fig.update_yaxes(title="IER")
    return _base(fig, 440)


def _linea_indice_estilo(nombre: str, i: int) -> dict:
    """Color y trazo de cada serie del índice: la línea foco (hospitalización del panel) en énfasis, todos en gris
    punteado, ambulatorio teal."""
    if "todos" in nombre:
        return dict(color=_C["muted"], dash="dot")
    if "Ambulatorio" in nombre:
        return dict(color=_C["teal"], dash="solid")
    if "panel" in nombre:
        return dict(color=_C["enfasis"], dash="solid")
    return dict(color=_PALETA[i % len(_PALETA)], dash="solid")


def linea_indice(df: pd.DataFrame) -> go.Figure:
    """Índice de actividad (2019 = 100) por año y tipo de episodio."""
    fig = go.Figure()
    grupos = sorted(df.groupby("TIPO_EPISODIO"), key=lambda kg: "todos" not in str(kg[0]))  # «todos» al fondo
    finales = {k: float(g.sort_values("ANIO")["indice"].iloc[-1]) for k, g in grupos}
    mas_bajo = min(finales, key=finales.get)  # su cifra final va bajo el punto: así no choca con la de la serie vecina
    for i, (k, g) in enumerate(grupos):
        g = g.sort_values("ANIO")
        etq = [""] * (len(g) - 1) + [numero(finales[k], 1)]
        fig.add_trace(go.Scatter(x=g["ANIO"].astype(str), y=g["indice"], name=str(k), mode="lines+markers+text", text=etq,
                                 line=_linea_indice_estilo(str(k), i), marker=dict(color=_linea_indice_estilo(str(k), i)["color"]),
                                 textposition="bottom center" if k == mas_bajo and len(grupos) > 1 else "top center", customdata=_textos(g["indice"], 0), hovertemplate=f"{k} %{{x}}: %{{customdata}}<extra></extra>"))
    fig.add_hline(y=100, line=dict(color=_C["muted"], dash="dot"))
    anios = [str(int(a)) for a in sorted(df["ANIO"].unique())]
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=anios)  # años como texto: con número salían «2.019»
    _marcar_minimo_y_ultimo(fig, df, anios)
    return _base(fig)


def _marcar_minimo_y_ultimo(fig: go.Figure, df: pd.DataFrame, anios: list[str]) -> None:
    """Rotula, en la serie de hospitalización del panel, el año con el índice más bajo y el último año (valor y año en el texto).

    En un eje de categorías Plotly toma una `x` con forma de número como posición, no como nombre: por eso se da el índice del año."""
    g = df[(df["TIPO_EPISODIO"] == "Hospitalización · panel")].sort_values("ANIO")
    if len(g) < 2:
        return
    minimo, ultimo = g.loc[g["indice"].idxmin()], g.iloc[-1]
    # desplazamientos (px) del rótulo: en diagonal y hacia abajo, donde no tapan las cifras ni las otras líneas
    marcas = [(minimo, "Más bajo", 60, 34)] if minimo["ANIO"] != ultimo["ANIO"] else []
    marcas.append((ultimo, "Último año", -75, 50))
    for fila, rotulo, dx, dy in marcas:
        fig.add_annotation(x=anios.index(str(int(fila["ANIO"]))), y=float(fila["indice"]), xref="x", yref="y", showarrow=True, arrowhead=0,
                           arrowcolor=_C["enfasis"], ax=dx, ay=dy,
                           text=f"<b>{rotulo} · {int(fila['ANIO'])}: {numero(float(fila['indice']), 1)}</b>",
                           font=dict(size=11, color=_C["enfasis"]), bgcolor=_C["card"], bordercolor=_C["enfasis"], borderpad=3)



def pareto_fig(df: pd.DataFrame, max_barras: int | None = None) -> go.Figure:
    """Pareto de GRD: barras de peso (las primeras `max_barras`) y línea de porcentaje acumulado de todos los GRD."""
    x = list(range(1, len(df) + 1))
    b = df if max_barras is None else df.head(max_barras)
    fig = go.Figure(go.Bar(x=x[:len(b)], y=b["pct"], name="% del peso", marker_color=_C["primary"], text=b["DESCRIPCION_GRD"],
                           customdata=_textos(b["pct"], 2), hovertemplate="%{text}: %{customdata} %<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=df["pct_acum"], name="% acumulado (eje derecho)", mode="lines", line=dict(color=_C["teal"]),
                             yaxis="y2", customdata=_textos(df["pct_acum"]), hovertemplate="Acumulado: %{customdata} %<extra></extra>"))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 100], ticksuffix=" %"))
    fig.update_xaxes(title="GRD ordenados por peso")
    fig.update_yaxes(ticksuffix=" %")
    _base(fig)
    fig.update_layout(yaxis2=dict(showgrid=False), margin=dict(r=50))
    return fig


def cuadrante_fig(df: pd.DataFrame) -> go.Figure:
    """Dispersión % de episodios vs % de peso por capítulo, con diagonal de igualdad."""
    tope = float(max(df["pct_episodios"].max(), df["pct_peso"].max())) * 1.05
    fig = go.Figure(go.Scatter(x=df["pct_episodios"], y=df["pct_peso"], mode="markers+text", text=df["CAPITULO_CIE10"],
                               textposition="top center", marker=dict(color=_C["primary"], size=10), showlegend=False,
                               customdata=list(zip(_textos(df["pct_episodios"]), _textos(df["pct_peso"]))),
                               hovertemplate="%{text}<br>Episodios %{customdata[0]} % · Peso %{customdata[1]} %<extra></extra>"))
    fig.add_trace(go.Scatter(x=[0, tope], y=[0, tope], mode="lines", line=dict(color=_C["muted"], dash="dot"),
                             showlegend=False, hoverinfo="skip"))
    fig.update_xaxes(title="% de episodios", ticksuffix=" %")
    fig.update_yaxes(title="% del peso", ticksuffix=" %")
    return _base(fig, 420)


GEOJSON = Path(__file__).parent / "recursos" / "regiones.geojson"  # geoBoundaries CHL ADM1 (BCN), cita en Metodología
REGIONES_MAPA = {  # nombre en el GeoJSON → nombre en la base
    "Región de Arica y Parinacota": "Arica y Parinacota", "Región de Tarapacá": "Tarapacá",
    "Región de Antofagasta": "Antofagasta", "Región de Atacama": "Atacama", "Región de Coquimbo": "Coquimbo",
    "Región de Valparaíso": "Valparaíso", "Región Metropolitana de Santiago": "Metropolitana",
    "Región del Libertador Bernardo O'Higgins": "O'Higgins", "Región del Maule": "Maule", "Región de Ñuble": "Ñuble",
    "Región del Bío-Bío": "Biobío", "Región de La Araucanía": "Araucanía", "Región de Los Ríos": "Los Ríos",
    "Región de Los Lagos": "Los Lagos", "Región de Aysén del Gral.Ibañez del Campo": "Aysén",
    "Región de Magallanes y Antártica Chilena": "Magallanes",
}
_ESCALA_MAPA = [[0, "#C6DBEF"], [1, _C["primary_dark"]]]  # parte más oscura que _ESCALA: el mapa no se pierde en el fondo
_ESCALA_DIVERGENTE = [[0, "#B35806"], [0.5, "#F4F1EC"], [1, _C["primary_dark"]]]  # baja naranjo, sube azul


@lru_cache(maxsize=1)
def regiones_geojson() -> dict:
    """GeoJSON de las 16 regiones con el nombre de la base en `id` (traducido con `REGIONES_MAPA`)."""
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    for f in geo["features"]:
        f["id"] = REGIONES_MAPA[f["properties"]["nombre"]]
    return geo


def mapa_regiones(df: pd.DataFrame, valor: str, divergente: bool = False, dec: int = 0) -> go.Figure:
    """Mapa de Chile por región del paciente: egresos con escala secuencial o variación % con escala divergente en 0.

    «Sin región» no se pinta. El encuadre es Chile continental: Rapa Nui y Juan Fernández siguen en Valparaíso, pero no
    se usan para encuadrar, porque el mapa quedaría diminuto.
    """
    orden = {r: i for i, r in enumerate(REGIONES_MAPA.values())}  # de norte a sur: así se pintan al aparecer
    d = df[df["REGION_PACIENTE"].isin(orden)].sort_values("REGION_PACIENTE", key=lambda s: s.astype(str).map(orden))
    texto = [numero(float(v), dec) + (" %" if divergente else "") for v in d[valor]]
    tope = float(d[valor].abs().max()) if divergente and len(d) else None
    fig = go.Figure(go.Choropleth(
        geojson=regiones_geojson(), locations=d["REGION_PACIENTE"], z=d[valor], customdata=texto,
        colorscale=_ESCALA_DIVERGENTE if divergente else _ESCALA_MAPA, zmid=0 if divergente else None,
        zmin=-tope if tope else None, zmax=tope if tope else None,
        marker=dict(line=dict(color="white", width=0.6)), hovertemplate="%{location}: %{customdata}<extra></extra>",
        colorbar=dict(thickness=10, len=0.5, x=0.98, separatethousands=True, exponentformat="none",
                      ticksuffix=" %" if divergente else "")))
    return _geo_chile(fig)


LIMITES_CHILE = ([-76, -66.3], [-56, -17.4])  # longitud, latitud del encuadre de Chile continental (sin islas)


def _geo_chile(fig: go.Figure, encuadre: tuple[list[float], list[float]] = LIMITES_CHILE,
               altura: int = ALTURA_MAPA) -> go.Figure:
    """Mapa mercator sin fondo ni ejes, encuadrado en `encuadre` (longitud, latitud); por omisión, Chile continental."""
    fig.update_geos(visible=False, projection_type="mercator", lonaxis_range=encuadre[0], lataxis_range=encuadre[1],
                    bgcolor="rgba(0,0,0,0)")
    _base(fig, altura)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    return fig


def _vertices(coords) -> list[tuple[float, float]]:
    """Todos los pares (lon, lat) de las coordenadas anidadas de un polígono o multipolígono."""
    if coords and isinstance(coords[0], (int, float)):
        return [(coords[0], coords[1])]
    return [v for c in coords for v in _vertices(c)]


@lru_cache(maxsize=32)
def encuadre_region(region: str, holgura: float = 0.4) -> tuple[list[float], list[float]]:
    """Longitud y latitud que encuadran una región (nombre de la base), sin sus islas lejanas.

    Se usan solo los vértices dentro del encuadre de Chile continental: Rapa Nui y Juan Fernández (Valparaíso) o el
    territorio antártico (Magallanes) dejarían el mapa diminuto. Se agrega `holgura` en grados y, si la región es angosta,
    se ensancha para que el mapa no pierda la forma.
    """
    (lon0, lon1), (lat0, lat1) = LIMITES_CHILE
    for f in regiones_geojson()["features"]:
        if f["id"] == region:
            v = [(x, y) for x, y in _vertices(f["geometry"]["coordinates"]) if lon0 <= x <= lon1 and lat0 <= y <= lat1]
            break
    else:
        return list(LIMITES_CHILE[0]), list(LIMITES_CHILE[1])
    if not v:  # región sin vértices dentro del encuadre continental: Chile entero
        return list(LIMITES_CHILE[0]), list(LIMITES_CHILE[1])
    xs, ys = [x for x, _ in v], [y for _, y in v]
    # Un mapa de ~1:1,3 (alto/ancho de la tarjeta) evita que una región angosta quede como una raya.
    ancho, alto = max(xs) - min(xs) + 2 * holgura, max(ys) - min(ys) + 2 * holgura
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    ancho = max(ancho, alto * 0.55)
    return [round(cx - ancho / 2, 2), round(cx + ancho / 2, 2)], [round(cy - alto / 2, 2), round(cy + alto / 2, 2)]


ALTURA_MAPA_MIN, ALTURA_MAPA_MAX, ALTURA_MAPA_GRANDE = 300, 520, 700  # px: recuadro de la región con zoom y mapa ampliado
ANCHO_BARRA_COLOR, MARGEN_TITULO_MAPA = 57, 44  # px: lo que la barra de color le quita al ancho del mapa y el título al alto


def altura_mapa_region(region: str, ancho_px: int = 330) -> int:
    """Alto total del recuadro del mapa de la ficha acercado a `region`, según la forma de su encuadre (300 a 520 px).

    Proyección mercator: el alto del mapa es proporcional a la diferencia de y(lat) = ln(tan(45° + lat/2)) y el ancho a la
    diferencia de longitud en radianes; así una región ancha (Metropolitana) queda baja y una larga (Aysén) alta. Plotly
    encaja esa caja en lo que queda del recuadro, que a lo ancho es `ancho_px` menos la barra de color y a lo alto el alto
    total menos el título de la figura; se suman ambos para que el mapa llene el recuadro en vez de dejar aire.
    """
    (lon0, lon1), (lat0, lat1) = encuadre_region(region)
    y = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    razon = (y(lat1) - y(lat0)) / math.radians(lon1 - lon0)
    alto = (ancho_px - ANCHO_BARRA_COLOR) * razon + MARGEN_TITULO_MAPA
    return int(min(ALTURA_MAPA_MAX, max(ALTURA_MAPA_MIN, round(alto))))


_BASE_MAPA = "#EEF1F5"  # regiones sin dato de origen (y todas, si el hospital no informa egresos)
_BASE_HOSPITALES = "#D8E1EC"  # regiones del mapa de hospitales: un poco más marcadas, para que se vea la forma de Chile tras los puntos


def mapa_hospital(origen: pd.DataFrame, hospital: tuple[float, float, str], otros: pd.DataFrame,
                  encuadre: tuple[list[float], list[float]] | None = None) -> go.Figure:
    """Mapa de la ficha: de dónde vienen los egresos del hospital y dónde está.

    `origen` trae `REGION_PACIENTE` y `pct` (% de los egresos del hospital; «Sin región» no se pinta). Todas las regiones
    usan una misma escala absoluta de 0 a 100 %: la región de la que viene casi todo queda la más oscura y las demás casi
    blancas, y el hover dice el % real de cada una con `etiqueta_pct` (nunca «0,0 %»). El hospital va con una estrella en
    el color de énfasis y `otros` (`LATITUD`, `LONGITUD`, `NOMBRE_DEIS`) son los demás hospitales de su región: puntos
    grises iguales que solo muestran el nombre, sin cifras ni tamaños, para que nunca se lean como una comparación. Con
    `origen` vacío dibuja solo la ubicación. `encuadre` (longitud, latitud) acerca el mapa; por omisión, Chile continental.
    """
    regiones = list(REGIONES_MAPA.values())
    fig = go.Figure(go.Choropleth(
        geojson=regiones_geojson(), locations=regiones, z=[0] * len(regiones), colorscale=[[0, _BASE_MAPA], [1, _BASE_MAPA]],
        showscale=False, marker=dict(line=dict(color="white", width=0.6)), hoverinfo="skip", name="base"))
    d = origen[origen["REGION_PACIENTE"].isin(regiones) & (origen["pct"] > 0)]  # sin egresos de una región: queda en la base
    if len(d):
        fig.add_trace(go.Choropleth(
            geojson=regiones_geojson(), locations=d["REGION_PACIENTE"], z=d["pct"], zmin=0, zmax=100,
            customdata=[etiqueta_pct(float(v)) + " %" for v in d["pct"]], colorscale=_ESCALA_MAPA, showscale=True,
            marker=dict(line=dict(color="white", width=0.6)), name="origen",
            hovertemplate="%{location}: %{customdata} de los egresos<extra></extra>",
            colorbar=dict(thickness=10, len=0.5, x=0.98, ticksuffix=" %", separatethousands=True, exponentformat="none")))
    if len(otros):
        fig.add_trace(go.Scattergeo(
            lat=list(otros["LATITUD"]), lon=list(otros["LONGITUD"]), mode="markers", name="otros", text=list(otros["NOMBRE_DEIS"]),
            marker=dict(size=7, color=_C["muted"], line=dict(color="white", width=0.8)),
            hovertemplate="%{text}<extra></extra>"))
    lat, lon, nombre = hospital
    fig.add_trace(go.Scattergeo(
        lat=[lat], lon=[lon], mode="markers", name="hospital", text=[nombre],
        marker=dict(size=16, symbol="star", color=_C["enfasis"], line=dict(color="white", width=1.2)),
        hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(showlegend=False)
    _geo_chile(fig, encuadre or LIMITES_CHILE, ALTURA_MAPA_HOSPITAL)
    fig.update_layout(height=None, autosize=True)  # el alto lo da la tarjeta (CSS en `componentes.estilos`): 520 px, o 420 en celular
    return fig


RAZON_ANCHO_ZOOM = 1.0  # ancho/alto mínimo (en proyección) de la caja del mapa de hospitales


def _ensanchar_encuadre(encuadre: tuple[list[float], list[float]], razon: float = RAZON_ANCHO_ZOOM) -> tuple[list[float], list[float]]:
    """Ensancha la longitud del encuadre (sin tocar la latitud) hasta que la caja tenga al menos `razon` de ancho/alto.

    En Plotly la caja que fijan `lonaxis`/`lataxis` es también la zona que responde a la rueda y al arrastre y que recorta
    el dibujo al acercar: con Chile (una raya de ~85 px) el zoom quedaba confinado a esa raya. Ensanchándola, el mapa se ve
    igual en pantallas anchas (lo limita el alto) y el zoom ocupa un recuadro cuadrado.
    """
    (lon0, lon1), (lat0, lat1) = encuadre
    y = lambda lat: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    ancho = max(lon1 - lon0, math.degrees(razon * (y(lat1) - y(lat0))))
    centro = (lon0 + lon1) / 2
    return [round(centro - ancho / 2, 2), round(centro + ancho / 2, 2)], list(encuadre[1])


_NIVELES_COMPLEJIDAD = (  # (valor del catálogo, nombre en la leyenda, color): azul oscuro para alta y azul medio para mediana
    ("Alta Complejidad", "Alta complejidad", _C["primary_dark"]),
    ("Mediana Complejidad", "Mediana complejidad", _AZUL_MEDIO),
)


def mapa_hospitales(estab: pd.DataFrame, region: str | None) -> go.Figure:
    """Mapa de dónde están los hospitales: un punto por hospital, todos del mismo tamaño y coloreados por complejidad.

    `estab` trae `NOMBRE_DEIS`, `COMUNA`, `NIVEL_COMPLEJIDAD`, `LATITUD`, `LONGITUD` y, para filtrar por `region`,
    `REGION_HOSPITAL`. Sin región se ve Chile continental; con ella, solo los hospitales de esa región y su encuadre.
    El hover muestra nombre, comuna y complejidad: ninguna cifra de actividad y ningún tamaño por egresos ni camas. El
    fucsia queda para el hospital elegido en Hospitales, así que aquí solo van azules. Los puntos son chicos y con contorno
    blanco porque en la Región Metropolitana varios hospitales quedan a pocos km.
    """
    d = estab.dropna(subset=["LATITUD", "LONGITUD"])
    if region is not None:
        d = d[d["REGION_HOSPITAL"] == region]
    regiones = list(REGIONES_MAPA.values())
    fig = go.Figure(go.Choropleth(
        geojson=regiones_geojson(), locations=regiones, z=[0] * len(regiones), colorscale=[[0, _BASE_HOSPITALES], [1, _BASE_HOSPITALES]],
        showscale=False, marker=dict(line=dict(color="white", width=0.6)), hoverinfo="skip", name="base", showlegend=False))
    for valor, nombre, color in _NIVELES_COMPLEJIDAD:
        g = d[d["NIVEL_COMPLEJIDAD"] == valor]
        fig.add_trace(go.Scattergeo(
            lat=list(g["LATITUD"]), lon=list(g["LONGITUD"]), mode="markers", name=nombre, text=list(g["NOMBRE_DEIS"]),
            customdata=list(g["COMUNA"]), marker=dict(size=8, color=color, line=dict(color="white", width=0.8)),
            hovertemplate=f"%{{text}}<br>%{{customdata}} · {nombre.lower()}<extra></extra>"))
    _geo_chile(fig, _ensanchar_encuadre(LIMITES_CHILE if region is None else encuadre_region(region)), ALTURA_MAPA_HOSPITAL)
    fig.update_layout(height=None, autosize=True, showlegend=True, dragmode="pan",  # el alto lo da el CSS: 520 px, o 420 en celular
                      legend=dict(orientation="h", x=0.02, y=0.02, xanchor="left", yanchor="bottom", entrywidthmode="pixels", entrywidth=150,
                                  bgcolor="rgba(255,255,255,0.8)", font=dict(color=_C["text_secondary"])))
    return fig


def piramide(df: pd.DataFrame) -> go.Figure:
    """Pirámide por edad y sexo del último año (hombres a la izquierda); el primer año, si hay dos, como contorno."""
    anios = sorted(df["ANIO"].unique())
    fig = go.Figure()
    for a in anios[-1:] if len(anios) == 1 else [anios[-1], anios[0]]:
        actual = a == anios[-1]
        for sexo, color, signo in (("Hombre", _C["primary"], -1), ("Mujer", _C["teal"], 1)):
            g = df[(df["ANIO"] == a) & (df["SEXO"] == sexo)]
            marcador = dict(color=color) if actual else dict(color="rgba(0,0,0,0)", line=dict(color=_C["text"], width=1.5))
            fig.add_trace(go.Bar(y=g["GRUPO_EDAD"], x=signo * g["pct"], orientation="h", marker=marcador,
                                 name=f"{sexo} {a}" if len(anios) > 1 else sexo, customdata=[f"{numero(float(v), 1)} %" for v in g["pct"]],
                                 hovertemplate=f"{sexo} %{{y}} ({a}): %{{customdata}}<extra></extra>"))
    fig.update_layout(barmode="overlay", bargap=0.1)
    paso = 5 if float(df["pct"].max()) > 10 else 2
    marcas = [k * paso for k in range(-int(df["pct"].max() // paso) - 1, int(df["pct"].max() // paso) + 2)]
    fig.update_xaxes(tickvals=marcas, ticktext=[f"{numero(abs(m))} %" for m in marcas], title="← Hombres · Mujeres →")
    return _base(fig)


MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def calendario(df: pd.DataFrame) -> go.Figure:
    """Calendario de egresos (como el de contribuciones de GitHub): una fila por año y un cuadro por mes, más oscuro con
    más egresos por día. `df` trae `mes` (primer día del mes) y `episodios`.

    Se cuenta por día y no por mes para que febrero, más corto, no parezca un mes flojo.
    """
    d = df.assign(anio=df["mes"].dt.year, m=df["mes"].dt.month, por_dia=df["episodios"] / df["mes"].dt.days_in_month)
    t = d.pivot_table(index="anio", columns="m", values="por_dia", aggfunc="sum").reindex(columns=range(1, 13))
    n = d.pivot_table(index="anio", columns="m", values="episodios", aggfunc="sum").reindex(index=t.index, columns=range(1, 13))
    cd = [[f"{numero(float(v), 0)} por día ({numero(float(k), 0)} en el mes)" if pd.notna(v) else "sin datos"
           for v, k in zip(fv, fk)] for fv, fk in zip(t.values, n.values)]
    fig = go.Figure(go.Heatmap(
        z=t.values, x=list(MESES_CORTOS), y=[str(a) for a in t.index], colorscale=_ESCALA_MAPA, xgap=3, ygap=3,
        customdata=cd, hovertemplate="%{x} %{y}: %{customdata}<extra></extra>", hoverongaps=False,
        colorbar=dict(orientation="h", thickness=8, len=0.6, x=0.5, xanchor="center", y=-0.04, yanchor="top",
                      separatethousands=True, exponentformat="none", title=dict(text="egresos por día", side="top"))))
    # escala abajo y meses sin girar: en el celular la escala al lado le quitaba ancho a los cuadros
    fig.update_xaxes(side="top", showgrid=False, fixedrange=True, tickangle=0, tickfont=dict(size=10))
    fig.update_yaxes(autorange="reversed", type="category", showgrid=False, fixedrange=True)  # años como texto
    _base(fig, 110 + 34 * len(t))
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=50))
    return fig


def repartir_100(pct: dict[str, float]) -> dict[str, int]:
    """Reparte 100 cuadros entre categorías según su %, sin perder ni sobrar ninguno (resto mayor primero)."""
    total = sum(pct.values()) or 1.0
    exacto = {k: v / total * 100 for k, v in pct.items()}
    cuadros = {k: int(v) for k, v in exacto.items()}
    for k in sorted(exacto, key=lambda k: exacto[k] - cuadros[k], reverse=True)[:100 - sum(cuadros.values())]:
        cuadros[k] += 1
    return cuadros


_ESCALONES = ("#DCE3EC", _AZUL_MEDIO, _C["primary_dark"])  # de menos a más: gris, azul medio, azul oscuro


def pictograma(pct: dict[str, float], unidad: str = "egresos", titulo: str = "") -> go.Figure:
    """Pictograma de 100 cuadros (waffle): cada cuadro es 1 de cada 100 `unidad`; `pct` = {categoría: %}, en orden.
    `titulo` encabeza la leyenda y el hover (por ejemplo «Crónicas»), así los nombres de las categorías pueden ser cortos.

    Las categorías van de la menos a la más intensa: con más de tres, los colores se repiten de la paleta categórica.
    """
    cuadros = repartir_100(pct)
    colores = list(_ESCALONES) if len(cuadros) <= 3 else _PALETA
    nombres = list(cuadros)
    cat = [i for i, k in enumerate(nombres) for _ in range(cuadros[k])]  # 100 valores, por filas desde arriba
    z = [cat[f * 10:(f + 1) * 10] for f in range(10)]
    txt = [[f"{titulo + ': ' if titulo else ''}{nombres[c].lower()} · {cuadros[nombres[c]]} de cada 100 {unidad}" for c in fila]
           for fila in z]
    n = len(nombres)
    escala = [[j / n, colores[i]] for i in range(n) for j in (i, i + 1)]  # una franja de color por categoría
    fig = go.Figure(go.Heatmap(z=z, zmin=-0.5, zmax=n - 0.5, colorscale=escala, showscale=False, xgap=3, ygap=3, text=txt,
                               hovertemplate="%{text}<extra></extra>"))
    for i, nombre in enumerate(nombres):  # leyenda: un cuadro de color por categoría con su cantidad
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=f"{nombre} ({cuadros[nombre]})",
                                 marker=dict(symbol="square", size=12, color=colores[i])))
    fig.update_xaxes(visible=False, fixedrange=True, constrain="domain")
    fig.update_yaxes(visible=False, fixedrange=True, autorange="reversed", scaleanchor="x", constrain="domain")
    _base(fig, ALTURA_MOSAICO)
    # leyenda abajo a la izquierda: centrada, en el celular se cortaba la primera categoría al pasar a tres líneas
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.02, x=0, xanchor="left",
                                  title=dict(text=titulo, side="top") if titulo else None),  # título arriba: a su izquierda cortaba la última categoría
                      margin=dict(l=10, r=10, t=10, b=80))
    return fig


def sankey(df: pd.DataFrame, origen: str, destino: str, valor: str) -> go.Figure:
    """Sankey de flujos: región del paciente a la izquierda, región del hospital a la derecha; el ancho de cada cinta es
    el número de egresos. Las regiones de cada lado van de la que mueve más a la que mueve menos."""
    izq = list(df.groupby(origen)[valor].sum().sort_values(ascending=False).index)
    der = list(df.groupby(destino)[valor].sum().sort_values(ascending=False).index)
    pos_izq, pos_der = {r: i for i, r in enumerate(izq)}, {r: len(izq) + i for i, r in enumerate(der)}
    fig = go.Figure(go.Sankey(
        arrangement="snap", valueformat=",.0f",
        node=dict(label=izq + der, pad=12, thickness=14, line=dict(width=0),
                  color=[_C["primary"]] * len(izq) + [_C["teal"]] * len(der),
                  customdata=["vive en"] * len(izq) + ["se atiende en"] * len(der),
                  hovertemplate="%{customdata} %{label}: %{value} egresos<extra></extra>"),
        link=dict(source=df[origen].astype(str).map(pos_izq), target=df[destino].astype(str).map(pos_der), value=df[valor],
                  color="rgba(29, 95, 173, 0.22)", customdata=_textos(df[valor], 0),
                  hovertemplate="%{source.label} → %{target.label}: %{customdata} egresos<extra></extra>"),
        textfont=dict(family="Inter, sans-serif", color=_C["text"], size=12)))
    for x, texto, lado in ((0, "Región del paciente", "left"), (1, "Región del hospital", "right")):
        fig.add_annotation(x=x, y=1.06, xref="paper", yref="paper", text=texto, showarrow=False, xanchor=lado,
                           font=dict(size=12, color=_C["text_secondary"]))
    _base(fig, max(ALTURA_MOSAICO, 28 * max(len(izq), len(der)) + 60))
    fig.update_layout(margin=dict(l=10, r=10, t=36, b=10))
    return fig
