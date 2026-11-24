"""Pantalla de carga con el gatito: se muestra solo la primera vez que se calcula algo con una selección nueva."""
import base64
from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import Hashable, Iterator

import streamlit as st

SVG = Path(__file__).parent / "recursos" / "gatito.svg"
ALT = "Ilustración de un gatito jugando con un ovillo de lana que suelta el hilo"
NOTA = "Las próximas veces será instantáneo."


@st.cache_resource
def _registro() -> set:
    """Claves ya calculadas en este servidor (compartido entre sesiones, igual que `st.cache_data`)."""
    return set()


def reiniciar_registro() -> None:
    """Olvida las claves vistas (para las pruebas)."""
    _registro().clear()


def _imagen() -> str:
    """El SVG como imagen incrustada: `st.html` descarta un `<svg>` en línea, pero deja pasar `<img>` con datos, y la
    animación CSS del SVG sigue funcionando dentro de una imagen."""
    datos = base64.b64encode(SVG.read_bytes()).decode()
    return f'<img role="img" alt="{ALT}" width="320" height="170" src="data:image/svg+xml;base64,{datos}">'


def _html(mensaje: str) -> str:
    estilo = ("display:flex;flex-direction:column;align-items:center;gap:.4rem;padding:1rem 0;text-align:center;"
              "font-size:.95rem")
    return (f'<div style="{estilo}">{_imagen()}'
            f'<p style="margin:0">{escape(mensaje)}</p>'
            f'<p style="margin:0;font-size:.85rem;opacity:.75">{escape(NOTA)}</p></div>')


@contextmanager
def calculando(clave: Hashable, mensaje: str) -> Iterator[None]:
    """Envuelve un cálculo: si `clave` no se ha visto, muestra el gatito con el `mensaje` y lo quita al terminar.

    Consultar el registro ANTES de llamar a la función con `st.cache_data` evita que un acierto de caché (instantáneo)
    muestre la ilustración. Si una entrada de la caché se expulsa (`max_entries`), el registro dirá «ya visto» y el
    cálculo se repetirá sin ilustración: es aceptable. Si el cálculo falla, la clave no se registra."""
    registro = _registro()
    if clave in registro:
        yield
        return
    caja = st.empty()
    caja.html(_html(mensaje))
    try:
        yield
    finally:
        caja.empty()
    registro.add(clave)
