"""Plantillas de filtros: conjuntos con nombre que llenan el borrador de la barra lateral.

Tres orígenes: las predefinidas del equipo, las propias (guardadas en la sesión) y las importadas desde un archivo JSON.
Cargar una plantilla solo llena el borrador; los números cambian cuando se pulsa «Aplicar».
"""
import json
import re
from dataclasses import dataclass

import streamlit as st

import datos
import indicadores as ind
import seleccion as sel
import textos as tx

CLAVE_PROPIAS = "plantillas_propias"
CLAVE_CRONICAS = "cronicas_vigentes"  # copia de `cr_elegidas` que no es un widget, para que sobreviva al cambio de página
CLAVE_ERROR = "plantilla_error"
CRONICAS_POR_DEFECTO = ["DIABETES", "HIPERTENSION", "EPOC", "ERC"]  # las cuatro que se contaban antes de la lista ampliada
MAX_NOMBRE = 60
MAX_BYTES = 100_000
VERSION = 1


@dataclass(frozen=True)
class Plantilla:
    """Nombre, filtros (solo los de la vista donde se creó) y, en el Perfil, las enfermedades que cuentan como comorbilidad."""
    nombre: str
    filtros: dict
    cronicas: tuple[str, ...] | None = None


def _completa(**valores) -> dict:
    """Todos los filtros: los de `valores` y, para el resto, sus valores iniciales."""
    return {**sel.valores_iniciales(), **valores}


PREDEFINIDAS: list[Plantilla] = [
    Plantilla("Mayores de 75 años, hospitalización", _completa(anios=[2025], tipo="HOSPITALIZACIÓN", grupo_edad="75+")),
    Plantilla("Región Metropolitana, un año", _completa(anios=[2025], tipo="HOSPITALIZACIÓN", region="Metropolitana")),
    Plantilla("Cardiometabólicas", _completa(anios=[2025], tipo="HOSPITALIZACIÓN"),
              ("DIABETES", "HIPERTENSION", "INSUF_CARDIACA", "CARDIOPATIA_ISQUEMICA", "ACV", "OBESIDAD")),
    Plantilla("Panel de 65 hospitales, ambulatorio", _completa(anios=[2023, 2024, 2025], tipo="AMBULATORIO", panel=True)),
]


# ---------------------------------------------------------------- validación y archivo

def _opciones_validas() -> dict:
    """Valores permitidos de cada filtro opcional (los mismos que ofrecen los selectores)."""
    cat, op = sel.catalogo(), sel.opciones()
    return {"region": {str(r) for r in cat["REGION_HOSPITAL"].dropna().unique()},
            "servicio": {str(x) for x in cat["SS_HOSPITAL"].dropna().unique()},
            "hospital": {str(h) for h in cat["COD_HOSPITAL"]}, "sexo": set(sel.SEXOS),
            "grupo_edad": set(datos.GRUPOS_EDAD), "capitulo": set(op["capitulos"]), "grd": set(op["grd"])}


def _validar_filtros(filtros: dict) -> dict:
    """Devuelve los filtros normalizados o levanta `ValueError` diciendo cuál no sirve."""
    if not isinstance(filtros, dict):
        raise ValueError("La plantilla no tiene la lista de filtros en el formato esperado.")
    desconocidos = [k for k in filtros if k not in sel.FILTROS]
    if desconocidos:
        raise ValueError(f"La plantilla trae filtros que esta aplicación no conoce: {', '.join(map(str, desconocidos))}.")
    validos, salida = _opciones_validas(), {}
    for f, v in filtros.items():
        nombre = sel.NOMBRES[f]
        if f == "anios":
            anios = datos.anios_disponibles()
            if not isinstance(v, list) or any(not isinstance(a, int) or isinstance(a, bool) or a not in anios for a in v):
                raise ValueError(f"En «{nombre}» hay años que no existen en los datos (disponibles: {anios[0]} a {anios[-1]}).")
            salida[f] = sorted(set(v))
        elif f == "tipo":
            if v not in sel.TIPOS.values():
                raise ValueError(f"En «{nombre}» solo se admite {' o '.join(sel.TIPOS.values())}.")
            salida[f] = v
        elif f == "panel":
            if not isinstance(v, bool):
                raise ValueError(f"En «{nombre}» solo se admite verdadero o falso.")
            salida[f] = v
        else:
            if v is not None and (not isinstance(v, str) or v not in validos[f]):
                raise ValueError(f"El valor {v!r} no es una opción válida de «{nombre}».")
            salida[f] = v
    return salida


def _validar_cronicas(cronicas) -> tuple[str, ...] | None:
    if cronicas is None:
        return None
    if not isinstance(cronicas, list):
        raise ValueError("La lista de enfermedades crónicas de la plantilla no tiene el formato esperado.")
    malas = [c for c in cronicas if not isinstance(c, str) or c not in tx.NOMBRES_CRONICAS]
    if malas:
        raise ValueError(f"La plantilla trae enfermedades crónicas que no existen en la lista: {', '.join(map(str, malas))}.")
    return tuple(c for c in tx.NOMBRES_CRONICAS if c in cronicas)


def _validar_nombre(nombre) -> str:
    if not isinstance(nombre, str) or not nombre.strip():
        raise ValueError("La plantilla necesita un nombre.")
    nombre = " ".join(nombre.split())
    if len(nombre) > MAX_NOMBRE:
        raise ValueError(f"El nombre es demasiado largo (máximo {MAX_NOMBRE} letras).")
    return nombre


def a_json(p: Plantilla) -> str:
    """Texto JSON de la plantilla, para descargarla."""
    cuerpo = {"version": VERSION, "nombre": p.nombre, "filtros": p.filtros}
    if p.cronicas is not None:
        cuerpo["cronicas"] = list(p.cronicas)
    return json.dumps(cuerpo, ensure_ascii=False, indent=2)


def desde_json(texto: str) -> Plantilla:
    """Lee una plantilla desde su JSON; si algo no sirve levanta `ValueError` con un mensaje para una persona."""
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("El archivo está vacío: no trae ninguna plantilla.")
    try:
        d = json.loads(texto)
    except (ValueError, RecursionError):  # RecursionError: JSON anidado miles de veces (no es subclase de ValueError)
        raise ValueError("El archivo no es una plantilla válida: no se pudo leer como JSON.") from None
    if not isinstance(d, dict):
        raise ValueError("El archivo no tiene el formato de una plantilla.")
    extra = [k for k in d if k not in ("version", "nombre", "filtros", "cronicas")]
    if extra:
        raise ValueError(f"La plantilla trae campos que esta aplicación no conoce: {', '.join(extra)}.")
    if "nombre" not in d or "filtros" not in d:
        raise ValueError("A la plantilla le falta el nombre o los filtros.")
    return Plantilla(_validar_nombre(d["nombre"]), _validar_filtros(d["filtros"]), _validar_cronicas(d.get("cronicas")))


def hay_filas(p: Plantilla) -> bool:
    """True si la plantilla, aplicada, deja al menos `MIN_CASOS` episodios en el agregado de perfil."""
    s = sel.Seleccion(**sel._normal({**sel.valores_iniciales(), **p.filtros}))
    df = datos.filtrar(datos.cargar_para("perfil", ("episodios",), s), s)
    return int(df["episodios"].sum()) >= ind.MIN_CASOS


# ---------------------------------------------------------------- estado de la sesión

def cronicas_vigentes() -> list[str]:
    """Enfermedades que cuentan como comorbilidad: las de la sesión (válidas) o las de por defecto."""
    guardadas = st.session_state.get(CLAVE_CRONICAS)
    if guardadas is None:
        return list(CRONICAS_POR_DEFECTO)
    return [c for c in tx.NOMBRES_CRONICAS if c in guardadas]


def propias() -> list[Plantilla]:
    """Plantillas guardadas o importadas en esta sesión."""
    return list(st.session_state.get(CLAVE_PROPIAS, []))


def _recordar(p: Plantilla) -> None:
    """Guarda `p` entre las propias; si ya hay una con ese nombre, la reemplaza."""
    if any(p.nombre == q.nombre for q in PREDEFINIDAS):
        raise ValueError("Ese nombre ya lo usa una plantilla predefinida: elige otro.")
    st.session_state[CLAVE_PROPIAS] = [q for q in propias() if q.nombre != p.nombre] + [p]


def guardar(nombre: str, usa: set[str] | None = None, con_cronicas: bool = False) -> Plantilla:
    """Guarda el borrador actual como plantilla propia (solo los filtros de `usa`; todos si no se indica)."""
    nombre = _validar_nombre(nombre)
    borrador = sel._borrador()
    filtros = {f: (list(v) if f == "anios" else v) for f, v in borrador.items() if usa is None or f in usa}
    elegidas = st.session_state.get("cr_elegidas", cronicas_vigentes())
    p = Plantilla(nombre, filtros, tuple(c for c in tx.NOMBRES_CRONICAS if c in elegidas) if con_cronicas else None)
    _recordar(p)
    return p


def cargar(p: Plantilla, usa: set[str] | None = None) -> None:
    """Llena el borrador con los filtros de `p` que la vista usa y deja coherentes servicio y hospital. No aplica."""
    for f, v in p.filtros.items():
        if f in sel.FILTROS and (usa is None or f in usa):
            st.session_state[f"d_{f}"] = list(v) if f == "anios" else v
    limpio = sel.coherente(sel._borrador())
    for f in ("servicio", "hospital"):
        if f"d_{f}" in st.session_state:
            st.session_state[f"d_{f}"] = limpio[f]
    if p.cronicas is not None:
        st.session_state[CLAVE_CRONICAS] = list(p.cronicas)
        for k in ("cr_elegidas", "hosp_cr_elegidas"):  # los selectores (Perfil y Hospitales) se vuelven a sembrar desde la copia
            st.session_state.pop(k, None)


def _por_etiqueta() -> dict[str, Plantilla]:
    """Plantillas por la etiqueta con que se listan: predefinidas primero, luego las propias."""
    return {**{p.nombre: p for p in PREDEFINIDAS}, **{f"{p.nombre} · propia": p for p in propias()}}


# ---------------------------------------------------------------- barra lateral

def _al_cargar(usa: set[str]) -> None:
    p = _por_etiqueta().get(st.session_state.get("plantilla_elegida"))
    if p:
        cargar(p, usa)


def _al_guardar(usa: set[str], con_cronicas: bool) -> None:
    try:
        p = guardar(st.session_state.get("plantilla_nombre", ""), usa, con_cronicas)
        st.session_state["plantilla_elegida"] = f"{p.nombre} · propia"
        st.session_state["plantilla_nombre"] = ""
    except ValueError as e:
        st.session_state[CLAVE_ERROR] = str(e)


def _importar(archivo) -> None:
    """Lee el archivo subido y lo suma a las propias, una sola vez por archivo; si no sirve, lo dice y no cambia nada.

    Mientras el archivo siga en el selector, cada ejecución lo vuelve a ver: sin esta guarda lo registraría de nuevo y
    pisaría una plantilla propia guardada después con el mismo nombre.
    """
    if st.session_state.get("plantilla_importada") == archivo.file_id:
        st.caption(f"Importada «{st.session_state.get('plantilla_importada_nombre', '')}»: ya está en la lista.")
        return
    try:
        if archivo.size > MAX_BYTES:
            raise ValueError("El archivo es demasiado grande para ser una plantilla.")
        try:
            texto = archivo.getvalue().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("El archivo no es una plantilla válida: no se pudo leer como texto.") from None
        p = desde_json(texto)
        _recordar(p)
    except ValueError as e:
        st.error(f"No se pudo importar la plantilla. {e}")
    else:
        st.session_state["plantilla_importada"] = archivo.file_id
        st.session_state["plantilla_importada_nombre"] = p.nombre
        st.rerun()  # la lista de arriba ya se dibujó: se vuelve a dibujar con la plantilla nueva


def bloque(usa: set[str], con_cronicas: bool = False) -> None:
    """Dibuja el bloque «Plantillas» (en la barra lateral) para una vista que usa los filtros `usa`."""
    if st.session_state.get("plantilla_elegida") not in _por_etiqueta():
        st.session_state.pop("plantilla_elegida", None)
    with st.expander("Plantillas", icon=":material/bookmark:"):
        st.caption("Una plantilla llena los filtros de abajo como borrador; los números cambian al pulsar «Aplicar».",
                   help=tx.GLOSARIO["plantilla"])
        etiquetas = _por_etiqueta()
        elegida = st.selectbox("Plantilla", list(etiquetas), index=None, placeholder="Elige una plantilla",
                               key="plantilla_elegida")
        st.button("Cargar", key="plantilla_cargar", on_click=_al_cargar, args=(usa,), disabled=elegida is None,
                  width="stretch")
        st.text_input("Nombre para guardar mi selección", key="plantilla_nombre", max_chars=MAX_NOMBRE)
        st.button("Guardar mi selección", key="plantilla_guardar", on_click=_al_guardar, args=(usa, con_cronicas),
                  width="stretch")
        if st.session_state.get(CLAVE_ERROR):
            st.error(st.session_state.pop(CLAVE_ERROR))
        p = etiquetas.get(elegida)
        archivo = re.sub(r"[^\w-]+", "_", p.nombre).strip("_").lower() if p else "plantilla"
        st.download_button("Exportar la elegida", a_json(p) if p else "", file_name=f"{archivo}.json",
                           mime="application/json", key="plantilla_exportar", disabled=p is None, width="stretch")
        subido = st.file_uploader("Importar una plantilla (.json)", type="json", key="plantilla_archivo")
        if subido is not None:
            _importar(subido)
