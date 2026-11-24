"""Anclas del recorrido guiado: por página, las claves de los contenedores que el recorrido puede resaltar.

Cada clave `x` es un `st.container(key="x")` que Streamlit dibuja con la clase CSS `st-key-x`; el recorrido (`recorrido.py`)
las usa como selector `.st-key-x`. Las claves son estables: no se renombran sin cambiar también esta tabla.

Notas para quien arme los pasos:
- `plantillas`, `pie_filtros` (barra lateral) y `franja` (filtros aplicados) están en toda página que dibuja filtros; la
  franja solo existe si hay algún filtro que mostrar.
- `lectura_resumen_*` (Análisis) es por pestaña: solo existe la de la pestaña abierta, y solo si hay texto que mostrar.
- `graficos_analisis` envuelve el contenido de la pestaña abierta (el recorrido resalta su primera tarjeta de gráfico) y
  `metodo_analisis` el desplegable «Cómo se calcula y advertencias».
- En un paso, `lectura_resumen_*` (con «*») vale para la de la pestaña abierta, sea cual sea; si hay dos (Perfil › Comorbilidad dibuja
  `lectura_resumen_perfil` y `lectura_resumen_comorbilidad`), `querySelector` toma la primera, la del Perfil, y está bien.
- `pestanas_analisis` envuelve las pestañas; para resaltar una sola usar `.st-key-a_pestana`.
- Hospitales sigue el mismo camino que Análisis: `pestanas_hospitales` envuelve sus cinco pestañas (el recorrido resalta la
  fila de pestañas) y `graficos_hospitales` el contenido de la abierta; el recorrido solo apunta a lo siempre visible y a la
  pestaña inicial (Actividad), nunca a otra pestaña.
- `kpis_inicio`, `mosaico_inicio`, `tabla_hospitales` y `mapa_hospitales` solo existen si la selección tiene egresos.
"""

_FILTROS = ("plantillas", "pie_filtros", "franja")

ANCLAS: dict[str, tuple[str, ...]] = {
    "Inicio": (*_FILTROS, "kpis_inicio", "mosaico_inicio", "tabla_hospitales", "mapa_hospitales"),
    "Análisis": (*_FILTROS, "pestanas_analisis", "lectura_resumen_actividad", "lectura_resumen_perfil",
                 "lectura_resumen_comorbilidad", "lectura_resumen_peso", "lectura_resumen_territorio", "graficos_analisis", "metodo_analisis"),
    # solo lo siempre visible y la pestaña inicial (Actividad): las secciones de las otras pestañas (hosp_quienes,
    # hosp_casos, hosp_estancia, hosp_comorbilidad, hosp_camas…) conservan su clave, pero no se dibujan hasta abrirlas
    "Hospitales": (*_FILTROS, "hosp_selector", "hosp_ficha", "hosp_resumen", "hosp_mapa",
                   "pestanas_hospitales", "graficos_hospitales", "hosp_referencia", "hosp_actividad", "hosp_serie"),
    "Descargas": (*_FILTROS, "descargas_tablas"),
    "Metodología": (),
}
