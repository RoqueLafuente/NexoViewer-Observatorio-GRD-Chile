"""Página Metodología: qué es el proyecto, fuentes, cobertura, tratamiento de los datos, indicadores, comorbilidad,
límites, cómo citar y glosario."""
from pathlib import Path

import streamlit as st

import datos
import indicadores as ind
import textos as tx
from paginas import comun as cm

RAIZ = Path(__file__).resolve().parents[2]
CITA = "Fuente: FONASA, Datos Abiertos (https://datosabiertos.fonasa.cl)"
CITA_MAPA = ("**Mapa de regiones.** Límites de la Biblioteca del Congreso Nacional (BCN), vía geoBoundaries "
             "(https://www.geoboundaries.org, CHL ADM1), licencia CC BY 3.0 IGO; simplificado para la app.")

ACERCA = (
    "NexoViewer: Observatorio GRD Chile reúne los egresos hospitalarios codificados en GRD de los hospitales públicos de "
    "Chile entre 2019 y 2025. Está pensado para investigadores y analistas de salud pública que no programan: pueden "
    "filtrar, mirar indicadores ya calculados y descargar las tablas para seguir trabajando con ellas. El equipo muestra "
    "los datos y no saca conclusiones; las preguntas las pone quien explora.\n\n"
    "Inicio resume lo elegido. Análisis responde cuatro preguntas: actividad, perfil de los egresos (con su comorbilidad), "
    "peso GRD y territorio. Hospitales muestra un hospital a elección en cinco pestañas: Actividad, Edad y origen, Casos y "
    "estancia, Comorbilidad y Camas. Descargas entrega las tablas en Excel y CSV con su diccionario de datos. Los filtros "
    "están en la barra lateral y cambian los números al pulsar «Aplicar»; una plantilla guarda un conjunto de filtros para "
    "volver a usarlo. Inicio, Análisis, Hospitales y Descargas tienen un recorrido guiado que se repite con «Ver recorrido»."
)

FUENTES = (
    f"**Egresos GRD (FONASA).** Una fila por egreso de los hospitales públicos que codifican en GRD, un archivo por año de "
    f"alta, 2019–2025. {CITA}. FONASA pide citarla en toda difusión.",
    "**Camas y ocupación (REM20, DEIS-MINSAL, https://deis.minsal.cl).** Resumen estadístico mensual con las camas y los "
    "días-cama de cada hospital por área funcional. Alimenta la pestaña Camas de Hospitales y las camas de «En cifras». No "
    "trae diagnósticos ni GRD, así que no se cruza con los casos del hospital. Sus egresos se cuentan aparte, pero para el "
    "mismo hospital y año coinciden con los egresos GRD de hospitalización: la razón REM20 ÷ GRD es 0,938 en 2019 y está "
    "entre 1,000 y 1,004 desde 2020.",
    "**Catálogo de establecimientos de salud (DEIS-MINSAL, datos.gob.cl, licencia CC0).** "
    "https://datos.gob.cl/dataset/3bf4cf7c-f638-4735-9a01-f65faae4beca. Da la ficha de cada hospital (comuna, nivel de "
    "atención, urgencia y ubicación) y el mapa de hospitales de Inicio. La complejidad del establecimiento (alta o mediana) "
    "sale de este catálogo y describe al hospital, no a sus egresos.",
    CITA_MAPA,
)

# Conteos de la limpieza de la base armonizada (los agregados ya vienen sin estas filas): 6.944.613 filas de FONASA
# − 4.084 copias − 19 registros dañados = 6.940.510 egresos; `estancia` suma 6.940.446 (64 sin estancia válida).
TRATAMIENTO = (
    "No se borra ninguna fila de los archivos de FONASA: los problemas se marcan y las tablas del dashboard dejan fuera lo "
    "marcado. De 6.944.613 filas quedan 6.940.510 egresos.",
    "**Filas duplicadas.** 4.084 filas idénticas a otra en todas sus columnas se cuentan una sola vez.",
    "**Registros dañados.** 19 registros de 2019 sin datos legibles quedan fuera.",
    "**Estancias inválidas.** 64 egresos con estancia negativa o sin fechas válidas no entran en la estancia ni en el IER, "
    "pero sí en los demás indicadores. Las estancias de 0 días y las de más de un año se conservan.",
    "**Estancias largas.** Hasta 30 días la estancia va día a día; sobre 30 se agrupa en tramos (31–60, 61–90, 91–180, "
    "181–365 y más de 365 días), y la mediana y el percentil 90 se calculan con esos tramos.",
    "**Egresos sin GRD.** Los 6.668 egresos inagrupables o sin GRD no aparecen al elegir hospitalización o ambulatorio.",
    "**Pocos casos.** En los gráficos de comorbilidad y de territorio, las celdas con menos de 30 episodios no se muestran, "
    "porque un porcentaje de tan pocos casos cambia mucho; un aviso bajo el gráfico dice cuándo pasa. En Hospitales, el "
    "origen con menos de 30 egresos se muestra en conteos y los grupos o años con menos de 30 quedan en blanco. Tampoco se "
    "calcula la variación frente a un año con menos de 30 episodios.",
)

INDICADORES = (
    "**Egresos.** Número de episodios: cada uno es una hospitalización o atención ambulatoria completa, del ingreso al alta.",
    "**Estancia.** Días entre el ingreso y el alta. Como es muy asimétrica (en hospitalización, mediana de 3 días y media "
    "de 7,1), se resume con la mediana y el percentil 90.",
    "**Peso GRD.** Peso relativo de cada GRD: 1 es el egreso promedio de referencia y un GRD de peso 2 pesa el doble.",
    "**Casemix.** Suma de los pesos GRD ÷ egresos: qué tan complejos son, en promedio, los casos atendidos.",
    "**Mortalidad bruta.** Egresos con alta por fallecimiento ÷ egresos × 100, sin ajustar por edad ni severidad.",
    "**Índice de estancia relativa (IER).** Días de estancia observados ÷ días esperados. Los esperados suman, para cada "
    "GRD, los egresos del hospital por la estancia media nacional de ese GRD en el mismo año. Solo hospitalización.",
    "**Índice de actividad.** Egresos del año ÷ egresos de 2019 × 100.",
    "**Ocupación de camas (índice ocupacional).** Σ días-cama ocupados ÷ Σ días-cama disponibles × 100. Se suma antes de "
    "dividir y nunca se promedian porcentajes. Puede pasar de 100 % porque el REM20 a veces registra más días ocupados que "
    "disponibles; sin días-cama disponibles se ve «—».",
    "**Camas disponibles (promedio).** Para cada mes se suman las camas de todas las áreas del hospital y luego se promedian "
    "los meses informados. La rotación divide los egresos del REM20 por esas camas.",
    "**Referencia en Hospitales.** El país o una región se calcula juntando los egresos de sus hospitales, no promediando "
    "hospitales; los egresos de la referencia se muestran como promedio por hospital.",
)

# Definición de comorbilidad redactada por el equipo. Referencias abiertas y verificadas el 23-11-2026.
COMORBILIDAD = (
    "**Qué es.** Comorbilidad es tener más de una enfermedad al mismo tiempo. Aquí es una definición operacional del equipo: "
    "una hospitalización tiene una enfermedad crónica si alguno de sus diagnósticos secundarios registrados empieza con una de "
    "las categorías CIE-10 de 3 caracteres de ese grupo; el diagnóstico principal no cuenta. Se cuentan egresos, no personas, "
    "y solo hospitalizaciones, tanto en Análisis como en Hospitales.",
    "**La lista.** 15 grupos: diabetes, hipertensión, EPOC, enfermedad renal crónica, insuficiencia cardíaca, cardiopatía "
    "isquémica, ACV, asma, cáncer, demencia, depresión, epilepsia, hepática crónica, obesidad y VIH (códigos en el Glosario). "
    "Criterios: enfermedad de larga duración, frecuente o relevante en salud pública, reconocida por el MINSAL y que se "
    "identifica con categorías CIE-10. Quien explora elige cuáles cuentan; por defecto, diabetes, hipertensión, EPOC y ERC, "
    "las cuatro con que partió el proyecto.",
    "**Por qué no el índice de Charlson.** Lo descartó el equipo: resume las enfermedades en un puntaje con pesos que mide, "
    "con otra escala, lo que el GRD ya mide con la severidad. Aquí se prefirió mostrar cada enfermedad por separado y que la "
    "defina quien explora.",
    "**Referencias (fuente principal: MINSAL).** Ministerio de Salud, Subsecretaría de Salud Pública (2025). Decreto 29: "
    "aprueba Garantías Explícitas en Salud del Régimen General de Garantías en Salud. https://www.bcn.cl/leychile/navegar?idNorma=1220430 "
    "(13 de los 15 grupos son problemas de salud GES). Ministerio de Salud, Departamento de Epidemiología (2017). Encuesta "
    "Nacional de Salud 2016-2017: primeros resultados. "
    "https://epi.minsal.cl/wp-content/uploads/2017/12/2017.21.07_pdf.primeros.resultados.pdf (obesidad).",
    "**Respaldo de los rangos CIE-10.** Quan H, Sundararajan V, Halfon P, et al. (2005). Coding algorithms for defining "
    "comorbidities in ICD-9-CM and ICD-10 administrative data. Medical Care. "
    "https://doi.org/10.1097/01.mlr.0000182534.19832.83 (también insuficiencia cardíaca, que no está en las listas del MINSAL). "
    "Tonelli M, Wiebe N, Fortin M, et al. (2015). Methods for identifying 30 chronic conditions: application to administrative "
    "data. BMC Medical Informatics and Decision Making 15:31. https://pmc.ncbi.nlm.nih.gov/articles/PMC4415341/",
)

# Cifras verificadas contra los agregados el 24-11-2026: 3,75 → 5,70 diagnósticos secundarios y casemix 0,91 → 1,07 en
# hospitalización; 65 hospitales hasta 2022, 68, 72 y 76 desde 2023. Si los datos cambian, se revisan aquí a mano.
LIMITES = (
    "**No se cuentan personas ni reingresos.** Cada fila es un egreso: una persona hospitalizada dos veces aparece dos "
    "veces. Los identificadores de persona vienen encriptados y no se usan.",
    "**No hay montos en pesos.** El peso GRD es relativo, no un valor en dinero; la suma de pesos mide volumen de trabajo "
    "ponderado por la complejidad de los casos.",
    "**La codificación cambió desde 2020.** Los diagnósticos secundarios por hospitalización suben de 3,75 (2019) a 5,70 "
    "(2025) y el casemix de 0,91 a 1,07. Parte de ese aumento, y del de enfermedades crónicas registradas, viene de "
    "registrar más y no de casos distintos. Tenlo presente al comparar años.",
    "**La cobertura cambió entre 2022 y 2023.** Hasta 2022 informan 65 hospitales; en 2023 son 68, en 2024 72 y en 2025 76. "
    "Los totales de años con distinta cobertura no se comparan directamente: el panel mantiene los mismos 65 en todos los años.",
    "**Solo sector público.** Las atenciones en clínicas y hospitales privados no están, tampoco en los flujos entre regiones.",
    "**El IER y el casemix no son una medida de calidad.** Describen la actividad de cada hospital y la complejidad de los "
    "casos que atiende.",
    "**La comorbilidad es un mínimo.** Solo cuenta lo anotado como diagnóstico secundario en esa hospitalización, no ajusta "
    "por edad y sube en parte por codificación desde 2020. La lista de 15 grupos es una definición operacional del equipo "
    "con respaldo del MINSAL, no una lista oficial ni validada.",
)

COMO_CITAR = (
    "Al usar cifras o tablas de NexoViewer, cita la fuente y la herramienta: «Fuente: FONASA, Datos Abiertos "
    "(https://datosabiertos.fonasa.cl). NexoViewer: Observatorio GRD Chile, fecha de consulta». Cada Excel de Descargas "
    "trae esa cita en la hoja «Cómo citar» y los filtros usados en «Filtros aplicados». Si usas camas, la ficha o los mapas, "
    "cita también el REM20 o el catálogo de establecimientos del DEIS-MINSAL y geoBoundaries."
)


@st.cache_data
def _cobertura() -> str:
    """Hospitales que informan por año, hospitales del panel y egresos, calculados desde `perfil`."""
    p = datos.cargar("perfil", ("ANIO", "EN_PANEL_7_ANIOS", "COD_HOSPITAL", "episodios"))
    anios = datos.anios_disponibles()
    por_anio = ind.hospitales_por_anio(p)
    panel = p.loc[p["EN_PANEL_7_ANIOS"] == True, "COD_HOSPITAL"].nunique()  # noqa: E712
    tramos: list[list] = []  # años seguidos con el mismo número de hospitales: [n, primer año, último año]
    for a, n in por_anio.items():
        if tramos and tramos[-1][0] == n:
            tramos[-1][2] = a
        else:
            tramos.append([n, a, a])
    partes = [f"{n} en {a}" if a == b else f"{n} entre {a} y {b}" for n, a, b in tramos]
    return (f"{p['COD_HOSPITAL'].nunique()} hospitales públicos informan GRD a FONASA en {anios[0]}–{anios[-1]}: "
            + ", ".join(partes[:-1]) + (" y " if len(partes) > 1 else "") + partes[-1]
            + f". Los {panel} que informan los {len(anios)} años forman el panel. En total hay "
              f"{tx.numero(p['episodios'].sum())} egresos. No incluye el sector privado.")


def _lista(textos: tuple[str, ...]) -> None:
    st.markdown("\n".join(f"- {t}" for t in textos))


def main() -> None:
    """Arma la página de metodología."""
    cm.encabezado("Metodología")
    st.subheader("Acerca del proyecto")
    st.markdown(ACERCA)
    st.subheader("Fuentes")
    _lista(FUENTES)
    st.subheader("Cobertura")
    st.markdown(_cobertura())
    st.subheader("Tratamiento de los datos")
    _lista(TRATAMIENTO)
    st.subheader("Cómo se calculan los indicadores")
    _lista(INDICADORES)
    st.subheader("Comorbilidad: definición del equipo y referencias")
    _lista(COMORBILIDAD)
    st.subheader("Límites y usos no recomendados")
    _lista(LIMITES)
    st.subheader("Cómo citar")
    st.markdown(COMO_CITAR)
    st.subheader("Glosario")
    texto = (RAIZ / "GLOSARIO.md").read_text(encoding="utf-8").lstrip()
    st.markdown(texto.partition(texto.splitlines()[0])[2].lstrip() if texto.startswith("# ") else texto)


main()
