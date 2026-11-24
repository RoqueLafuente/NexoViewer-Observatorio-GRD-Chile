"""Selección global del usuario (barra lateral) y su lectura desde `st.session_state`."""
from dataclasses import dataclass

import pandas as pd
import streamlit as st

import datos
import textos as tx
from textos import GLOSARIO

TIPOS = {"Hospitalización": "HOSPITALIZACIÓN", "Ambulatorio": "AMBULATORIO"}
FILTROS_OPCIONALES = ("region", "servicio", "hospital", "sexo", "grupo_edad", "capitulo", "grd")
FILTROS = ("anios", "tipo", "panel") + FILTROS_OPCIONALES
NOMBRES = {"anios": "años", "tipo": "tipo de atención", "panel": "panel", "region": "región", "servicio": "servicio",
           "hospital": "hospital", "sexo": "sexo", "grupo_edad": "edad", "capitulo": "capítulo", "grd": "GRD"}
SEXOS = {"HOMBRE": "Hombre", "MUJER": "Mujer"}
PESTANAS_ANALISIS = ["1 · Actividad", "2 · Perfil", "3 · Peso GRD", "4 · Territorio"]
# sin número: los cinco títulos caben en la barra de pestañas de un celular
PESTANAS_HOSPITALES = ["Actividad", "Edad y origen", "Casos y estancia", "Comorbilidad", "Camas"]

# Filtros que usa cada vista (página, o «Análisis · pestaña» / «Hospitales · pestaña») y, si hace falta, por qué apaga los demás.
_BASICOS = {"anios", "tipo", "panel", "region"}
_HOSPITALES = ({"anios", "tipo"}, "Aquí eliges el hospital y con qué compararlo.")
USO = {
    "Inicio": (set(FILTROS), None),
    "Descargas": (set(FILTROS), None),
    "Hospitales": _HOSPITALES,
    **{f"Hospitales · {p}": _HOSPITALES for p in PESTANAS_HOSPITALES},  # todas las pestañas usan los mismos filtros
    "Metodología": (set(), "Esta página no usa filtros."),
    "Análisis · 1 · Actividad": ({"region"}, "Esta pregunta mira siempre los 7 años, con hospitalización y ambulatorio, "
                                             "en el panel y en todos los hospitales."),
    "Análisis · 2 · Perfil": (_BASICOS | {"sexo"}, "La pestaña Comorbilidad mira siempre hospitalizaciones, y las "
                                                   "enfermedades que cuentan se eligen dentro de la pestaña."),
    "Análisis · 3 · Peso GRD": (_BASICOS, None),
    "Análisis · 4 · Territorio": ({"anios", "tipo"}, "La región del paciente se elige dentro de la pregunta, y los "
                                                     "flujos no distinguen el panel."),
}


@dataclass
class Seleccion:
    """Filtros globales y de página que se aplican a los agregados."""
    anios: list[int]
    tipo: str
    panel: bool
    region: str | None = None
    servicio: str | None = None
    hospital: str | None = None
    sexo: str | None = None
    grupo_edad: str | None = None
    capitulo: str | None = None
    grd: str | None = None


@st.cache_data
def catalogo() -> pd.DataFrame:
    """Hospitales con su región y servicio de salud, para las opciones de los filtros."""
    p = datos.cargar("perfil", ("COD_HOSPITAL", "HOSPITAL", "REGION_HOSPITAL", "SS_HOSPITAL"))
    return p.drop_duplicates("COD_HOSPITAL").dropna(subset=["COD_HOSPITAL"]).sort_values("HOSPITAL")


@st.cache_data
def opciones() -> dict:
    """Capítulos y GRD disponibles con sus etiquetas."""
    p, g = datos.cargar("perfil", ("CAPITULO_CIE10",)), datos.cargar("grd", ("COD_GRD", "DESCRIPCION_GRD"))
    caps = sorted(str(c) for c in p["CAPITULO_CIE10"].dropna().unique())
    grd = g[["COD_GRD", "DESCRIPCION_GRD"]].dropna(subset=["COD_GRD"]).drop_duplicates("COD_GRD").sort_values("COD_GRD")
    return {"capitulos": {c: tx.etiqueta_capitulo(c) for c in caps},
            "grd": {str(k): f"{k} · {d}" for k, d in zip(grd["COD_GRD"], grd["DESCRIPCION_GRD"])}}


def etiqueta_hospital(cod: str, nombre: str) -> str:
    """«Código · nombre»: el selector busca en lo que muestra, así se encuentra un hospital por código o por nombre.

    El código va primero porque la lista recorta los nombres largos y lo que se corta es el final.
    """
    return f"{cod} · {nombre}"


def selector(col, etiqueta: str, key: str, opciones: list, nombres: dict | None = None, todos: str = "Todos",
             on_change=None) -> None:
    """Dibuja un filtro con 'Todos' (None) y limpia el valor guardado si ya no es una opción."""
    opciones = [None] + list(opciones)
    if st.session_state.get(key) not in opciones:
        st.session_state[key] = None
    nombres = nombres or {}
    # placeholder: al volver de otra página Streamlit muestra el None guardado como «sin elegir»
    col.selectbox(etiqueta, opciones, key=key, format_func=lambda v: todos if v is None else nombres.get(v, v),
                  placeholder=todos, on_change=on_change)


def vista(pagina: str) -> str:
    """Nombre de la vista actual: la página, o «Análisis · pestaña» / «Hospitales · pestaña» con la pestaña abierta."""
    if pagina == "Análisis":
        return f"Análisis · {st.session_state.get('a_pestana', PESTANAS_ANALISIS[0])}"
    if pagina == "Hospitales":
        return f"Hospitales · {st.session_state.get('h_pestana', PESTANAS_HOSPITALES[0])}"
    return pagina


def _lista(nombres: list[str], y: str = "y") -> str:
    """«a, b y c» (o «a, b ni c» con `y="ni"`)."""
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + f" {y} " + nombres[-1]


def nota_apagados(usa: set[str], razon: str | None) -> str | None:
    """Texto que dice por qué la vista muestra solo algunos filtros y cuáles no usa (None si usa todos)."""
    no_usa = [NOMBRES[f] for f in FILTROS if f not in usa]
    if not no_usa:
        return None
    return " ".join(t for t in (razon, f"Esta vista no usa: {_lista(no_usa)}.") if t)


def _cascada() -> None:
    """Al cambiar región o servicio, deja en el borrador solo el servicio y el hospital que les corresponden."""
    v = coherente(_borrador())
    for f in ("servicio", "hospital"):
        if f"d_{f}" in st.session_state:
            st.session_state[f"d_{f}"] = v[f]


GRUPOS = {"Período y atención": ("anios", "tipo", "panel"), "Territorio": ("region", "servicio", "hospital"),
          "Paciente": ("sexo", "grupo_edad"), "Diagnóstico": ("capitulo", "grd")}


def _n_apagados(usa: set[str]) -> str:
    n = len([f for f in FILTROS if f not in usa])
    return f"{n} filtro" + ("s" if n > 1 else "")


def _dibujar_grupo(filtros: tuple[str, ...], usa: set[str], cat: pd.DataFrame, op: dict) -> None:
    """Dibuja los filtros del grupo que la vista usa; la región, el servicio y el hospital se acotan en cascada."""
    if "anios" in filtros and "anios" in usa:
        st.multiselect("Años", datos.anios_disponibles(), key="d_anios")
    if "tipo" in filtros and "tipo" in usa:
        st.radio("Tipo de atención", list(TIPOS.values()), key="d_tipo",
                 format_func=lambda v: next(k for k, x in TIPOS.items() if x == v))
    if "panel" in filtros and "panel" in usa:
        st.toggle("Solo panel de 65 hospitales", key="d_panel", help=GLOSARIO["panel"])
    if "region" in filtros:
        borrador = _borrador()
        if "region" in usa:
            selector(st, "Región del hospital", "d_region", sorted(str(r) for r in cat["REGION_HOSPITAL"].dropna().unique()),
                     todos="Todas", on_change=_cascada)
            borrador = _borrador()
        if borrador["region"]:
            cat = cat[cat["REGION_HOSPITAL"] == borrador["region"]]
        if "servicio" in usa:
            selector(st, "Servicio de salud", "d_servicio", sorted(str(s) for s in cat["SS_HOSPITAL"].dropna().unique()),
                     on_change=_cascada)
            borrador = _borrador()
        if borrador["servicio"]:
            cat = cat[cat["SS_HOSPITAL"] == borrador["servicio"]]
        if "hospital" in usa:
            selector(st, "Hospital", "d_hospital", [str(h) for h in cat["COD_HOSPITAL"]],
                     {str(k): etiqueta_hospital(str(k), str(n)) for k, n in zip(cat["COD_HOSPITAL"], cat["HOSPITAL"])})
    for f, etiqueta, opc, nombres in (("sexo", "Sexo", list(SEXOS), SEXOS),
                                      ("grupo_edad", "Edad", list(datos.GRUPOS_EDAD), None),
                                      ("capitulo", "Capítulo CIE-10", list(op["capitulos"]), op["capitulos"]),
                                      ("grd", "GRD", list(op["grd"]), op["grd"])):
        if f in filtros and f in usa:
            selector(st, etiqueta, f"d_{f}", opc, nombres)


def n_cambios() -> int:
    """Número de filtros cuyo borrador difiere de la selección vigente."""
    b, v = _normal(_borrador()), _normal(_vigente())
    return sum(b[f] != v[f] for f in FILTROS)


def n_activos(filtros: tuple[str, ...], usa: set[str] | None = None) -> int:
    """Filtros del grupo cuyo borrador difiere del valor inicial (el contador «· n» del grupo).

    Solo cuenta los que la vista dibuja (`usa`): uno no dibujado no se ve y no debe sumar.
    """
    b, ini = _normal(_borrador()), _normal(valores_iniciales())
    return sum(b[f] != ini[f] for f in filtros if usa is None or f in usa)


def leer_globales(pagina: str = "Inicio") -> Seleccion:
    """Dibuja en la barra lateral solo los filtros que la vista usa y devuelve la selección vigente.

    Los widgets son un borrador (`d_<filtro>`) que arranca con la selección vigente; solo «Aplicar» lo hace vigente.
    Si la vista no usa ningún filtro no se dibuja nada y la barra no aparece.
    """
    usa, razon = USO.get(vista(pagina), (set(FILTROS), None))
    for f in FILTROS:
        if f not in usa:  # un filtro que no se dibuja no deja borrador: al volver se siembra con lo vigente
            st.session_state.pop(f"d_{f}", None)
    if not usa:
        # Streamlit deja la barra vacía si en esta sesión ya tuvo filtros: se oculta para que no aparezca.
        st.html("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] {display: none;}</style>")
        return actual()
    vigente = _vigente()
    for f in FILTROS:
        if f in usa and f"d_{f}" not in st.session_state:
            v = vigente[f]
            st.session_state[f"d_{f}"] = list(v) if f == "anios" else v
    import plantillas  # aquí y no arriba: `plantillas` importa este módulo
    with st.sidebar:
        with st.container(key="plantillas"):
            plantillas.bloque(usa, con_cronicas=vista(pagina) == "Análisis · 2 · Perfil")
        st.markdown("**Filtros**", help=GLOSARIO["filtro_apagado"])
        cat, op = catalogo(), opciones()
        for nombre, filtros in GRUPOS.items():
            if not usa & set(filtros):  # un grupo sin filtros usados no se dibuja
                continue
            n = n_activos(filtros, usa)
            # `key` fija la identidad: sin ella, al cambiar la etiqueta («· n») Streamlit pliega el grupo abierto
            with st.expander(f"{nombre} · {n}" if n else nombre, expanded=nombre == next(iter(GRUPOS)),
                             key=f"grupo_{filtros[0]}"):
                _dibujar_grupo(filtros, usa, cat, op)
        nota = nota_apagados(usa, razon)
        if nota:
            st.caption(f"Esta vista no usa {_n_apagados(usa)}.", help=nota)
        with st.container(key="pie_filtros"):
            n = n_cambios()
            fila = st.container(horizontal=True, key="pie_botones")  # en fila también con la barra angosta
            fila.button("Reiniciar", key="reiniciar", on_click=reiniciar, width="stretch")
            fila.button("Aplicar" if n == 0 else f"Aplicar · {n} cambio{'s' if n > 1 else ''}", key="aplicar",
                       type="primary", on_click=aplicar, disabled=n == 0, width="stretch")
    return actual()


def valores_iniciales() -> dict:
    """Valores de todos los filtros al abrir o reiniciar: último año, hospitalización, sin panel y el resto en «Todos»."""
    return {"anios": datos.anios_disponibles()[-1:], "tipo": TIPOS["Hospitalización"], "panel": False,
            **{f: None for f in FILTROS_OPCIONALES}}


def _borrador() -> dict:
    """Valores de los widgets `d_<filtro>`; donde no hay widget (filtro no dibujado) rige la selección vigente."""
    vigente = _vigente()
    return {f: st.session_state.get(f"d_{f}", vigente[f]) for f in FILTROS}


def _vigente() -> dict:
    """Valores de la selección aplicada (los iniciales si todavía no hay ninguna)."""
    ini = valores_iniciales()
    guardado = st.session_state.get("sel_vigente") or {}
    return {f: guardado.get(f, ini[f]) for f in FILTROS}


def _normal(valores: dict) -> dict:
    """Forma comparable: años ordenados y panel booleano."""
    return {**valores, "anios": sorted(valores["anios"] or []), "panel": bool(valores["panel"])}


def coherente(valores: dict) -> dict:
    """Copia de `valores` sin el servicio o el hospital que no pertenecen a la región o al servicio elegidos."""
    v = dict(valores)
    cat = catalogo()
    if v.get("region"):
        cat = cat[cat["REGION_HOSPITAL"] == v["region"]]
    if v.get("servicio") and v["servicio"] not in set(cat["SS_HOSPITAL"].astype(str)):
        v["servicio"] = None
    if v.get("servicio"):
        cat = cat[cat["SS_HOSPITAL"] == v["servicio"]]
    if v.get("hospital") and str(v["hospital"]) not in set(cat["COD_HOSPITAL"].astype(str)):
        v["hospital"] = None
    return v


def aplicar() -> None:
    """Copia el borrador a la selección vigente (lo que usan las páginas)."""
    st.session_state["sel_vigente"] = _normal(coherente(_borrador()))


def reiniciar() -> None:
    """Devuelve borrador, selección vigente y enfermedades de la comorbilidad a sus valores iniciales."""
    ini = valores_iniciales()
    for f, v in ini.items():
        st.session_state[f"d_{f}"] = v
    st.session_state["sel_vigente"] = dict(ini)
    for k in ("cronicas_vigentes", "cr_elegidas", "hosp_cr_elegidas"):  # también las enfermedades de la comorbilidad vuelven a las cuatro de siempre
        st.session_state.pop(k, None)


def hay_cambios() -> bool:
    """True si el borrador difiere de la selección vigente."""
    return _normal(_borrador()) != _normal(_vigente())


def actual() -> Seleccion:
    """Arma la selección vigente desde `st.session_state["sel_vigente"]` sin dibujar widgets."""
    v = _normal(_vigente())
    return Seleccion(**v)


def _corto(texto: str, largo: int = 40) -> str:
    """Recorta con «…» un texto largo para que quepa en una etiqueta."""
    return texto if len(texto) <= largo else texto[:largo - 1].rstrip() + "…"


def _anios_texto(anios: list[int]) -> str:
    """«2025», «2023–2025» (años seguidos) o «2021, 2023, 2025»."""
    a = sorted(anios)
    if not a:
        return str(max(datos.anios_disponibles()))  # sin años, las páginas usan el último (ind.periodo)
    if len(a) == 1:
        return str(a[0])
    return f"{a[0]}–{a[-1]}" if a[-1] - a[0] == len(a) - 1 else ", ".join(str(x) for x in a)


def chips(sel: Seleccion, usa: set[str]) -> list[str]:
    """Etiquetas de lo aplicado: solo filtros que la vista usa y sin los que están en «Todos»."""
    out = []
    if "anios" in usa:
        out.append(_anios_texto(sel.anios))
    if "tipo" in usa:
        out.append(next(k for k, v in TIPOS.items() if v == sel.tipo))
    if "panel" in usa and sel.panel:
        out.append("Panel de 65 hospitales")
    if "region" in usa and sel.region:
        out.append(sel.region)
    if "servicio" in usa and sel.servicio:
        out.append(sel.servicio)
    if "hospital" in usa and sel.hospital:
        cat = catalogo()
        n = cat.loc[cat["COD_HOSPITAL"].astype(str) == str(sel.hospital), "HOSPITAL"]
        out.append(_corto(str(n.iloc[0]) if len(n) else str(sel.hospital)))
    if "sexo" in usa and sel.sexo:
        out.append(SEXOS.get(sel.sexo, sel.sexo))
    if "grupo_edad" in usa and sel.grupo_edad:
        out.append(f"Edad: {sel.grupo_edad}")
    if "capitulo" in usa and sel.capitulo:
        out.append(_corto(tx.etiqueta_capitulo(sel.capitulo)))
    if "grd" in usa and sel.grd:
        out.append(_corto(opciones()["grd"].get(str(sel.grd), f"GRD {sel.grd}")))
    return out
