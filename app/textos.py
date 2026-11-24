"""Formato chileno de números, glosario y lecturas rápidas del dashboard (sin Streamlit)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from indicadores import Periodo

SIN_DATO = "—"
POCOS_CASOS = "Con esta selección hay muy pocos casos para sacar una conclusión."


def numero(x: float | None, dec: int = 0) -> str:
    """Formatea con punto de miles, coma decimal y signo menos Unicode (un cero redondeado va sin signo)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return SIN_DATO
    s = f"{x:,.{dec}f}".replace(",", "#").replace(".", ",").replace("#", ".")
    if s.startswith("-"):
        return s[1:] if not any(c in "123456789" for c in s) else "−" + s[1:]
    return s


def rotulo_periodo(anios) -> str:
    """Período de un gráfico para su título: «2025», «2021–2024» (años seguidos) o «2019, 2021 y 2025» (sueltos)."""
    a = sorted({int(x) for x in anios})
    if not a:
        return ""
    if len(a) == 1:
        return str(a[0])
    if a == list(range(a[0], a[-1] + 1)):
        return f"{a[0]}–{a[-1]}"
    return ", ".join(str(x) for x in a[:-1]) + f" y {a[-1]}"


def con_periodo(titulo: str, anios) -> str:
    """«Severidad (% de egresos) · 2025»: el título de un gráfico con el período que de verdad muestra."""
    return f"{titulo} · {rotulo_periodo(anios)}"


def estancia(dias: int | None) -> str:
    """Formatea una estancia en días (más de 30 se agrupa como '> 30 días')."""
    if dias is None or (isinstance(dias, float) and math.isnan(dias)):
        return SIN_DATO
    if dias > 30:
        return "> 30 días"
    return "1 día" if dias == 1 else f"{numero(dias)} días"


CAPITULOS = {
    "01": "I. Infecciosas y parasitarias",
    "02": "II. Tumores",
    "03": "III. Sangre e inmunidad",
    "04": "IV. Endocrinas, nutricionales y metabólicas",
    "05": "V. Trastornos mentales",
    "06": "VI. Sistema nervioso",
    "07": "VII. Ojo y anexos",
    "08": "VIII. Oído",
    "09": "IX. Sistema circulatorio",
    "10": "X. Sistema respiratorio",
    "11": "XI. Sistema digestivo",
    "12": "XII. Piel",
    "13": "XIII. Sistema osteomuscular",
    "14": "XIV. Sistema genitourinario",
    "15": "XV. Embarazo, parto y puerperio",
    "16": "XVI. Afecciones perinatales",
    "17": "XVII. Malformaciones congénitas",
    "18": "XVIII. Síntomas y hallazgos anormales",
    "19": "XIX. Lesiones y envenenamientos",
    "20": "XX. Causas externas",
    "21": "XXI. Factores que influyen en la salud",
    "22": "XXII. Códigos especiales (COVID-19)",
}


def etiqueta_capitulo(cap: str | None) -> str:
    """Devuelve la etiqueta corta del capítulo CIE-10 a partir de su código."""
    if cap is None or cap == "Sin capítulo":
        return "Sin capítulo"
    return CAPITULOS.get(cap, f"Capítulo {cap}")


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")

GLOSARIO = {
    "egreso": "Una hospitalización o atención ambulatoria completa, desde el ingreso hasta el alta. Es la unidad de la base: una persona hospitalizada dos veces son dos egresos.",
    "casemix": "Peso GRD medio: qué tan complejos son, en promedio, los casos que atiende un hospital o región.",
    "peso_grd": "Peso relativo fijo de cada GRD; 1 es el episodio promedio de referencia y un GRD de peso 2 pesa el doble que uno de peso 1. No son pesos chilenos ni un monto de dinero.",
    "severidad": "Qué tan grave es el episodio dentro de su GRD según las comorbilidades y complicaciones registradas: 1 menor, 2 moderada, 3 mayor.",
    "mediana": "Valor central de la estancia: la mitad de los episodios dura menos y la mitad más. La usamos en vez de la media porque la estancia es muy asimétrica.",
    "p90": "Estancia que no supera el 90 % de los episodios: el 10 % restante dura más que esto.",
    "ier": "Índice de estancia relativa: días observados ÷ días esperados según los GRD atendidos. Sobre 1 usa más días de los esperados según sus GRD; bajo 1, menos. La referencia es el promedio nacional del mismo año. Se parece al IEMA de las unidades GRD, pero usa la estancia media nacional del año y no excluye los casos extremos; no es la norma MINSAL.",
    "panel": "Los 65 hospitales que informan los 7 años. Comparar totales entre años solo vale dentro del panel, porque desde 2023 se suman 11 hospitales.",
    "cobertura": "Qué hospitales están en los datos: solo públicos que informan GRD, sin el sector privado.",
    "indice_actividad": "Egresos del año ÷ egresos de 2019 × 100, calculado con el panel. Un valor de 89,9 significa 10 % menos actividad que en 2019.",
    "cronicas": "Combinación de las cuatro condiciones crónicas registradas en el episodio: DM diabetes, HTA hipertensión, EPOC enfermedad pulmonar obstructiva crónica y ERC enfermedad renal crónica.",
    "fuera_region": "Egresos atendidos en un hospital de otra región que la de residencia del paciente, como % de los egresos de esa región. Sin región conocida no se cuenta como fuera.",
    "piramide": "Pirámide por edad y sexo: % de los egresos del año en cada grupo de edad, hombres a la izquierda y mujeres a la derecha.",
    "mapa_calor": "Mapa de calor: tabla de colores donde cada celda es un valor; más oscuro es más alto.",
    "mapa_regiones": "Mapa de regiones: Chile por región donde vive el paciente. Con un año, el color muestra los egresos (más oscuro es más); al comparar, la variación %: naranjo baja, azul sube. Los egresos sin región no se pintan.",
    "serie_mensual": "Serie de egresos por mes: todos los hospitales y el panel. Abre en los años elegidos; con doble clic sobre el gráfico se ven todos los años (2019–2025).",
    "linea_indice": "Línea de índice: índice de actividad (2019 = 100) por año para hospitalización del panel, hospitalización de todos los hospitales y ambulatorio del panel.",
    "principales_flujos": "Principales flujos: Sankey con los 10 pares región del paciente → región del hospital con más egresos, sin contar los de la misma región.",
    "sankey": "Sankey (diagrama de flujos): a la izquierda la región donde vive el paciente y a la derecha la del hospital que lo atendió; cada cinta une las dos y su ancho es el número de egresos.",
    "calendario": "Calendario de egresos: una fila por año y un cuadro por mes, como el calendario de contribuciones de GitHub. Más oscuro es más egresos por día; se cuenta por día para que febrero, más corto, no parezca un mes flojo.",
    "pictograma": "Pictograma de 100 (waffle): 100 cuadros, cada uno es 1 de cada 100 hospitalizaciones; el color dice cuántas de las enfermedades crónicas elegidas en el Perfil tiene registradas: ninguna, una, o dos o más.",
    "respuesta_corta": "Respuesta corta: una línea con borde fucsia bajo cada pregunta de Análisis que la responde en una o dos frases; se calcula con los datos y los filtros.",
    "como_se_calcula": "Cómo se calcula y advertencias: desplegable al final de cada pregunta con la advertencia de la pregunta, la fórmula en palabras y la tabla de origen.",
    "analisis": "Análisis: página con una pestaña por pregunta (1 · Actividad, 2 · Perfil, 3 · Peso GRD, 4 · Territorio). El Perfil tiene dos sub-pestañas: Perfil general y Comorbilidad.",
    "hospitales": "Página que muestra un hospital a elección. Arriba, siempre a la vista, el selector, su ficha del catálogo del DEIS con «En cifras» debajo y, al lado y del mismo alto, el mapa con su ubicación y el origen de sus egresos («Ampliar» lo abre en grande con la lectura y la tabla). Debajo, cinco pestañas, y solo se calcula la abierta: Actividad (egresos, estancia mediana, casemix, mortalidad, IER y severidad frente a la referencia que se elige ahí mismo: el país, su región u otra región; y su serie mensual), Edad y origen (a quiénes atiende y de dónde vienen sus egresos), Casos y estancia, Comorbilidad (con las enfermedades elegidas, compartidas con el Perfil) y Camas (REM20). Nunca pone un hospital junto a otro hospital ni los ordena.",
    "periodo_hospital": "Años en Hospitales: con un año elegido, cada gráfico muestra ese año (los gráficos por mes, sus 12 meses) y las variaciones lo comparan con el año anterior. Con varios, cada gráfico muestra solo los años elegidos, nunca los otros: año a año (paneles o líneas con un punto por año, la misma cifra que al elegir ese año solo) o mes a mes (los meses de esos años, con un corte entre años que no son seguidos); los gráficos de un solo año (GRD de más peso, histograma de estancia, origen por región y provincia, mapa, pictograma y mapas de calor de comorbilidad) son del último, y las variaciones lo comparan con el primero. La franja gris de la pandemia aparece solo si 2020 o 2021 están entre lo que se ve. Cada título dice su período, por ejemplo «· 2025» o «· 2021–2025». Un año en que el hospital no informa queda sin punto, no en cero.",
    "referencia_hospital": "Referencia de la página Hospitales: el país (todos los hospitales), su región (todos los hospitales de la región, incluido el elegido) u otra región. Los indicadores de una región se calculan con los egresos juntos de sus hospitales, no promediando hospitales. Una región con un solo hospital no se ofrece como otra región, porque sería otro hospital; si es la región propia, la referencia es solo ese hospital y se avisa.",
    "mapa_hospital": "Mapa del hospital: al lado de la ficha, del mismo alto, muestra dónde está el hospital (la estrella), acercado a su región, con las regiones pintadas por el % de los egresos del hospital (del último año elegido y el tipo de atención) que vienen de cada región donde vive el paciente; más oscuro es más. Los puntos grises son los otros hospitales de su región: todos iguales, solo con su nombre. El botón de la esquina lo amplía: ahí van la escala de colores, la lectura del origen, sus notas, la tabla y el interruptor «Acercar a su región»; la rueda del mouse acerca y se arrastra para mover. Los egresos sin región conocida no se pintan, pero cuentan en el 100 %.",
    "nivel_complejidad": "Nivel de complejidad: alta o mediana, según el catálogo de establecimientos del DEIS-MINSAL. La complejidad depende de la unidad asistencial, en términos del número de procedimientos complejos, grado de desarrollo alcanzado, disponibilidad de recurso humano y grado de especialización, equipamiento y horario de atención. Describe al establecimiento, no a sus egresos: no es la complejidad de los casos (severidad, diagnósticos secundarios, casemix).",
    "serie_hospital": "Serie de egresos por mes del hospital elegido, sin otros hospitales ni el total del país, en los meses de los años elegidos y solo esos: con un año, sus 12 meses. El tramo gris es la pandemia, si cae en lo que se ve. Un mes sin línea es un mes en que el hospital no informa egresos de ese tipo.",
    "origen_hospital": "Origen de los egresos: región y provincia de residencia de quien se atendió en el hospital, del año y tipo de atención elegidos. «Otra región» es el % de egresos de personas que viven fuera de la región del hospital; los egresos sin región conocida cuentan en el total pero no se grafican. Con menos de 30 egresos se muestran conteos y no porcentajes. Si una región o provincia reúne el 80 % o más, se dice con una cifra grande y el gráfico muestra solo las demás. Es la residencia de quien se atendió: no distingue derivaciones de consultas directas.",
    "grd_hospital": "GRD de más peso: los 10 GRD que más suman del peso GRD del hospital en el año. El % es la parte del peso GRD total del hospital que aporta cada GRD; un GRD puede pesar mucho por ser frecuente o por ser complejo (peso alto). Describe qué casos atiende, no cómo los atiende.",
    "ficha_hospital": "Ficha del hospital: datos oficiales del catálogo de establecimientos del DEIS-MINSAL: comuna, complejidad del establecimiento (alta o mediana), nivel de atención, tipo de establecimiento, si es autogestionado en red y si tiene urgencia hospitalaria.",
    "en_cifras": "En cifras: seis cifras del hospital en el año más reciente elegido, bajo su ficha: egresos, estancia mediana, índice casemix, camas disponibles (promedio), índice ocupacional y severidad mayor. Son las mismas de sus pestañas (las camas y la ocupación, solo aquí), solo del hospital y sin comparación. Sin egresos GRD en el año quedan solo las de camas (REM20).",
    "filtro_apagado": "Filtro que no aparece: la barra lateral muestra solo los filtros que usa la página o la pregunta abierta, y una nota dice cuáles no usa. Lo que eliges queda como borrador hasta pulsar «Aplicar»; «Reiniciar» vuelve al último año, hospitalización y sin panel, y a las cuatro enfermedades de la comorbilidad de siempre. La selección aplicada se mantiene al cambiar de página y vuelve a valer en las vistas que sí usan ese filtro.",
    "plantilla": "Plantilla: conjunto con nombre de filtros de la barra lateral (y, en el Perfil, de las enfermedades que cuentan como comorbilidad). Hay predefinidas, que prepara el equipo, y propias, que se guardan en la sesión y se exportan o importan como un archivo JSON. Cargar una plantilla solo llena el borrador: los números cambian al pulsar «Aplicar». Una plantilla solo guarda los filtros de la vista donde se creó y en otras vistas se ignoran los que no se usan.",
    "ver_en_tabla": "Ver en tabla: desplegable bajo cada gráfico principal con las cifras exactas que dibuja, en una tabla; los años van como texto y, donde hay celdas ocultas (comorbilidad y territorio), se ven en blanco.",
    "vista_guiada": "Vista guiada (recorrido guiado): unos pocos pasos que oscurecen la pantalla y resaltan una parte de la página con una tarjeta que la explica (Anterior, Siguiente, Omitir). Se abre solo la primera vez que entras a una página que lo tiene (la marca queda guardada en tu navegador) y se repite con el botón «Ver recorrido».",
    "region_paciente": "Región de origen del paciente: la región donde vive el paciente, no la del hospital que lo atendió. La usan el Perfil (región de residencia de los egresos) y Territorio, que la elige dentro de la propia pregunta.",
    "descargas": "Página con, por cada tabla agregada, un Excel (.xlsx con las hojas Datos, Filtros aplicados y Cómo citar) y un CSV, con los años, el tipo de atención y los filtros elegidos; el CSV usa separador `;`, coma decimal y UTF-8 con marca para Excel. Trae también el diccionario de datos.",
    "metodologia": "Página con qué es el proyecto, las fuentes, la cobertura, el tratamiento de los datos, cómo se calculan los indicadores, la definición de comorbilidad, los límites, cómo citar y este glosario.",
    "diccionario_datos": "Diccionario de datos: dice en lenguaje simple qué significa cada columna de las tablas agregadas (tabla, columna, significado y tipo). Se ve y se descarga en CSV desde Descargas.",
    "como_citar": "Cómo citar: cada Excel de Descargas trae una hoja «Cómo citar» con la fuente (FONASA, Datos Abiertos) y la fecha de descarga, y una hoja «Filtros aplicados» con los años y filtros de esa tabla, para que quien la use pueda reproducirla y citarla.",
    "egreso_no_persona": "Egreso frente a persona: cada fila de la base es un egreso (episodio), no una persona. Una persona hospitalizada dos veces aparece dos veces y no se usan identificadores de persona, por eso no se cuentan personas ni reingresos.",
    "que_hay_en_los_datos": "Qué hay en estos datos: línea bajo el título de Inicio con lo que contiene la base: episodios, años, hospitales, regiones, GRD y variables. Son egresos de la red pública con GRD (sin sector privado), sin filas duplicadas ni registros dañados. Cada fila es un egreso, no una persona: una persona hospitalizada dos veces aparece dos veces, y no se cuentan personas ni reingresos. La cobertura cambia entre 2022 y 2023 (ver Metodología).",
    "mortalidad": "Mortalidad intrahospitalaria: episodios con alta «fallecido» ÷ episodios × 100. Depende de la edad y la severidad: sin separarlas, los hospitales que reciben casos más graves muestran cifras más altas. En Hospitales es mortalidad bruta: no se ajusta por edad ni severidad.",
    "promedio_por_hospital": "Promedio por hospital: en la referencia de la página Hospitales (el país, su región u otra región), los egresos se muestran divididos por el número de hospitales que informan ese año, para ponerlos en la escala de un hospital.",
    "pareto": "Pareto: GRD ordenados de mayor a menor peso GRD total, con la curva acumulada: cuántos GRD suman el 50 % u 80 % del peso GRD.",
    "cuadrante": "Cuadrante volumen vs peso GRD: cada capítulo es un punto: eje X = % de episodios, eje Y = % del peso GRD. Sobre la diagonal, el capítulo tiene más % del peso GRD que % de los episodios.",
    "barras_base_foco": "Barras base → foco: cada categoría tiene dos barras, la del año base en gris y la del año foco en fucsia, rotulada con su valor y, entre paréntesis, la diferencia con la base. En la pregunta Territorio las dos barras son medidas del mismo año: % de egresos (gris) y % del peso GRD (fucsia).",
    "paneles_anios": "Paneles año a año (Hospitales › Actividad con varios años): un panel pequeño por indicador (egresos, estancia mediana, casemix, mortalidad bruta e IER) con dos líneas: el hospital en fucsia y la referencia en gris cortado. Cada panel tiene su propia escala: se leen la forma y las cifras, no el alto entre paneles. Cada punto es la misma cifra que muestra la tarjeta al elegir ese año solo. En la referencia, los egresos son un promedio por hospital. Un año en que el hospital no informa queda en blanco, no en cero.",
    "lineas_anios": "Líneas año a año (Hospitales con varios años): una línea por categoría (severidad, capítulo, enfermedad, origen o estancia) con un punto por cada año elegido y su nombre al final de la línea. Solo van los años elegidos, en orden; si no son seguidos, la línea une años con otros en medio. Cada punto es la cifra que se ve al elegir ese año solo. Un año sin egresos del hospital, o con menos de 30, queda en blanco, no en cero.",
    "minigraficos": "Minigráficos: una línea pequeña por categoría a lo largo de los años elegidos. A la izquierda, el valor del primer año en gris; a la derecha, el del último año en fucsia. Cada minigráfico tiene su propia escala: se comparan las cifras rotuladas, no el alto de las líneas.",
    "cometa": "Cometa: cada hospital o región es una flecha del año A (cola) al año B (cabeza): muestra hacia dónde se movió.",
    "comorbilidad": "Comorbilidad: tener más de una enfermedad al mismo tiempo; aquí, diagnósticos secundarios registrados en esa hospitalización, por eso toda cifra es un mínimo. Se cuentan egresos (hospitalizaciones), no personas. Desde 2020 se registran más diagnósticos secundarios por episodio (3,75 → 5,70): parte del aumento es codificación.",
    "lista_cronicas": "Enfermedades que pueden contar como comorbilidad: definición operacional del equipo, no una lista oficial ni validada. Quien explora elige cuáles cuentan; por defecto, diabetes, hipertensión, EPOC y ERC, las cuatro con que partió el proyecto. Cada grupo es una enfermedad de larga duración, frecuente o relevante en salud pública y que se identifica con categorías CIE-10 de 3 caracteres. Respaldo: 13 de los 15 son problemas de salud GES del MINSAL (Decreto 29 de 2025) y la obesidad la mide la Encuesta Nacional de Salud 2016-2017 del MINSAL; la insuficiencia cardíaca no está en esas listas y se incluye por los algoritmos CIE-10 de comorbilidad de Quan et al. (2005), que también respaldan los rangos de códigos. Códigos CIE-10: diabetes E10–E14, hipertensión I10–I13 e I15, EPOC J44, ERC (enfermedad renal crónica) N18, insuficiencia cardíaca I50, cardiopatía isquémica I20–I25, ACV (enfermedad cerebrovascular) I60–I69, asma J45–J46, cáncer C00–C97, demencia F00–F03 y G30, depresión F32–F33, epilepsia G40–G41, hepática crónica K70 y K73–K74, obesidad E66, VIH B20–B24.",
    "pares_cronicas": "Pares frecuentes: mapa de calor con cada par de enfermedades elegidas; cada celda es el % de las hospitalizaciones del año que tiene registradas las dos.",
    "estancia_grupos": "Estancia por severidad y por grupo de edad (Hospitales › Casos y estancia): con un año, para cada grupo un segmento de la mediana (punto fucsia) al percentil 90 (punto gris) de los días de estancia de sus egresos; con varios, lo mismo con una fila por grupo y año. La severidad es solo de hospitalización. Sobre 30 días la base agrupa la estancia en tramos (31–60, 61–90…): el punto va al inicio del tramo y el texto dice el tramo. Un grupo con menos de 30 egresos en el año no se muestra. Describe cuánto duran los egresos de cada grupo en el hospital, que depende de qué casos llegan; no compara hospitales.",
    "histograma_estancia": "Histograma de estancia: cuántos egresos del hospital duran 0, 1, 2… días en el año y tipo de atención elegidos. La línea fucsia es la mediana y la gris punteada el percentil 90. Se dibujan los días uno a uno hasta 30; los egresos de más de 30 días (que la tabla agrupa en tramos) no se dibujan, pero cuentan en la mediana y el percentil 90, y una nota dice cuántos son.",
    "diag_secundarios": "Diagnósticos secundarios por egreso: promedio de otras enfermedades o complicaciones registradas además del diagnóstico principal. Subió de 3,75 (2019) a 5,70 (2025), en parte por codificación.",
    "camas_promedio": "Camas disponibles (promedio): camas instaladas y en condiciones de uso según el REM20, promediadas en el año; no es la dotación de camas asignada. Para cada mes se suman las camas disponibles de todas sus áreas funcionales y luego se promedian los meses informados; las camas por unidad suman esta cifra.",
    "indice_ocupacional": "Índice ocupacional: días-cama ocupados ÷ días-cama disponibles × 100, de un año o de un mes. Se suma antes de dividir, nunca se promedian porcentajes mensuales. Puede pasar de 100 %: en algunos meses el REM20 registra más días ocupados que disponibles. Sin días-cama disponibles no se calcula y se ve «—». No tiene un valor bueno o malo universal: depende del tipo de unidad.",
    "rotacion": "Rotación: egresos del REM20 ÷ camas disponibles (promedio) del período; cuántos egresos pasan por cada cama. En un año, un valor de 50 son 50 egresos por cama. Desde 2020 los egresos del REM20 de un hospital casi siempre coinciden con sus egresos GRD de hospitalización; la nota de la sección dice si coinciden en el año.",
    "traslados": "Traslados internos: movimientos de una persona hospitalizada a otra área funcional del mismo establecimiento, que no son un egreso hospitalario ni una derivación a otro hospital. Se muestran como número en el año (REM20).",
    "familia_unidad": "Familia de unidad: grupo de áreas funcionales del REM20 según su servicio o nivel de cuidado: médico-quirúrgico, médica adulto, pediátrica, obstetricia, neonatología (solo sus cuidados básicos), cuidados intermedios (las UTI de adultos, pediátrica y neonatal) y cuidados intensivos (las UCI de adultos, pediátrica y neonatal; la ocupación de la familia junta las tres edades), psiquiatría (también sus cuidados intensivos) y otras (pensionado, sociosanitaria). Cada familia tiene su propio color, el mismo en todos los gráficos de Camas. Con un año elegido se ven las camas por familia de ese año (barras); con varios, su evolución en esos años (una línea por familia; un año sin esa familia cuenta 0). El selector «Ver las unidades de una familia» muestra después las unidades de la familia elegida, con la misma regla de años. El MINSAL llama camas críticas (UPC) a intensivos e intermedios juntos; aquí van en dos familias.",
    "camas_por_familia": "Camas por familia: con un año elegido, camas disponibles (promedio) de cada familia de unidades del hospital en ese año, cada barra en el color de su familia; las barras suman las camas disponibles del hospital. A la derecha de cada barra va escrita la ocupación de la familia en el año (días-cama ocupados ÷ disponibles de sus unidades × 100); «—» si no tiene días-cama disponibles. Al pasar el mouse: unidades, ocupación, egresos y estancia media. Con varios años, en su lugar va la evolución por familia de esos años.",
    "camas_por_unidad": "Camas por unidad: con una familia elegida en el selector, camas disponibles (promedio) de cada una de sus áreas funcionales: con un año, barras de ese año (suman las camas de la familia, con la ocupación del año escrita a la derecha; «—» si no tiene días-cama disponibles); con varios, una línea por unidad en esos años (un año sin esa unidad cuenta 0). Cada unidad tiene su propio color, el mismo en sus barras, su evolución y su ocupación mensual. Al pasar el mouse: ocupación, egresos y estancia media (días de estada ÷ egresos, REM20). «Ver en tabla» trae los nombres completos.",
    "ocupacion_unidad": "Ocupación por unidad: una línea sólida por unidad de la familia elegida, en su color, con su ocupación de cada mes (días-cama ocupados ÷ disponibles × 100) en los meses de los años elegidos (con un año, sus 12 meses), con el nombre al final de la línea y el eje fijo desde 0 %. Un mes sin punto es un mes sin días-cama disponibles en esa unidad. Si la familia tiene más de 8 unidades, las de menos camas se juntan en «Otras unidades», sumando sus días-cama.",
    "curva_ocupacion": "Ocupación mensual: para cada mes, días-cama ocupados ÷ días-cama disponibles de todas las áreas del hospital × 100 (REM20), en los meses de los años elegidos y solo esos (con un año, sus 12 meses). Un mes sin línea es un mes sin días-cama disponibles. El tramo gris es la pandemia, si cae en lo que se ve.",
}

# Variables que acepta cada lectura (las numéricas pasan por `numero`).
VARIABLES_LECTURA = {
    "capitulos": ("capitulo", "pct"),
    "serie": ("egresos", "pct"),
    "serie_anio": ("egresos", "mes", "maximo"),
    "sexo": ("pct_mujeres",),
    "edad": ("grupo", "pct"),
    "hospitales": ("n", "total", "hospital", "ier", "ier_base", "ier_foco"),
    "hospitales_sin_mejora": ("total",),
    "territorio": ("region", "pct"),
    "actividad": ("indice",),
    "pareto": ("n_grd", "pct", "n_base"),
    "cuadrante": ("capitulo", "dif"),
    "cronicas": ("capitulo", "pct"),
    "fuera_region": ("pct",),
    "cronicas_edad": ("condicion", "grupo", "pct"),
    "mortalidad_cronicas": ("combinacion", "mortalidad", "ninguna"),
    "flujos": ("origen", "destino", "valor"),
    "calendario": ("mes_bajo", "bajo", "mes_alto", "alto"),
    "pictograma": ("una", "varias"),
    "pares": ("combinacion", "pct"),
    "region_paciente": ("region", "pct"),
}
NUMERICAS = {"pct", "egresos", "pct_mujeres", "valor", "indice", "n_grd", "n_base", "dif", "maximo", "mortalidad", "ninguna",
             "n", "total", "ier", "ier_base", "ier_foco", "bajo", "alto", "una", "varias"}
_DEC = {"n_grd": 0, "n_base": 0, "egresos": 0, "valor": 0, "maximo": 0, "n": 0, "total": 0, "ier": 2, "ier_base": 2, "ier_foco": 2,
        "bajo": 0, "alto": 0, "una": 0, "varias": 0}
# Variables cuyo signo se dice con palabras ({sentido}) y se muestran sin signo, por modo: (si sube, si baja).
_SENTIDO = {
    "capitulos": ("pct", {"comparar": ("más", "menos")}),
    "serie": ("pct", {"un_anio": ("más", "menos"), "comparar": ("más", "menos")}),
    "edad": ("pct", {"comparar": ("más", "menos")}),
    "territorio": ("pct", {"comparar": ("más", "menos")}),
    "cronicas": ("pct", {"comparar": ("más", "menos")}),
    "region_paciente": ("pct", {"comparar": ("más", "menos")}),
    "cuadrante": ("dif", {"un_anio": ("más", "menos"), "comparar": ("creció", "se achicó")}),
}
# Decimales propios de una lectura (pisan a `_DEC`).
_DEC_LECTURA = {"pareto": {"pct": 0}}
# Nombres cortos de los 15 grupos de la lista de crónicas (definición del equipo), para gráficos y selectores.
NOMBRES_CRONICAS = {
    "DIABETES": "Diabetes", "HIPERTENSION": "Hipertensión", "EPOC": "EPOC", "ERC": "ERC",
    "INSUF_CARDIACA": "Insuficiencia cardíaca", "CARDIOPATIA_ISQUEMICA": "Cardiopatía isquémica", "ACV": "ACV",
    "ASMA": "Asma", "CANCER": "Cáncer", "DEMENCIA": "Demencia", "DEPRESION": "Depresión", "EPILEPSIA": "Epilepsia",
    "HEPATICA_CRONICA": "Hepática crónica", "OBESIDAD": "Obesidad", "VIH": "VIH",
}
_CRONICAS = {"DM": "diabetes", "HTA": "hipertensión",
             **{k: v if v.isupper() else v.lower() for k, v in NOMBRES_CRONICAS.items()}}

# Plantillas (un_anio, comparar); {foco} y {base} los pone `lectura`. Empiezan por el dato y dicen el sentido con palabras.
_PLANTILLAS = {
    "capitulos": (
        "{capitulo} es la causa más frecuente en {foco}: {pct} % de los egresos.",
        "{capitulo} pesa {pct} puntos {sentido} en los egresos de {foco} que en los de {base}.",
    ),
    "serie": (
        "En {foco} hubo {egresos} egresos, {pct} % {sentido} que en {base}.",
        "En {foco} hubo {egresos} egresos, {pct} % {sentido} que en {base}.",
    ),
    "serie_anio": (  # sin año base: describe solo el año foco
        "En {foco} hubo {egresos} egresos. El mes con más fue {mes}, con {maximo}.",
        "El mes con más egresos de {foco} fue {mes}, con {maximo}, en un año de {egresos}.",
    ),
    "sexo": (
        "Las mujeres son el {pct_mujeres} % de los egresos de {foco}.",
        "Las mujeres son el {pct_mujeres} % de los egresos de {foco}; las barras muestran cómo cambió desde {base}.",
    ),
    "edad": (
        "El grupo de {grupo} años es el más numeroso en {foco}: {pct} % de los egresos.",
        "El grupo de {grupo} años es el que más cambió: pesa {pct} puntos {sentido} en los egresos de {foco} que en los de {base}.",
    ),
    "hospitales": (  # sobre lo que se dibuja: la tabla con IER (un año) o el cometa (comparar)
        "{n} de los {total} hospitales de la tabla usan más días de cama de los esperados para sus casos en {foco} "
        "(IER sobre 1). El más alto es {hospital}, con {ier}.",
        "{n} de los {total} hospitales del gráfico bajaron su IER entre {base} y {foco}, o sea, hoy usan relativamente "
        "menos días de cama. La mayor baja fue la de {hospital}, de {ier_base} a {ier_foco}.",
    ),
    "hospitales_sin_mejora": (
        "Ninguno de los {total} hospitales de la tabla bajó su IER en {foco} frente a {base}.",
        "Ninguno de los {total} hospitales del gráfico bajó su IER entre {base} y {foco}.",
    ),
    "territorio": (
        "La región {region} reúne el {pct} % de los egresos de {foco}.",
        "{region} es la región donde más cambiaron los egresos entre {base} y {foco}: {pct} % {sentido}.",
    ),
    "actividad": (
        "Si 2019 es 100, la actividad de {foco} está en {indice}.",
        "Si 2019 es 100, la actividad de {foco} está en {indice}.",
    ),
    "pareto": (
        "{n_grd} GRD suman el {pct} % del peso GRD de {foco}.",
        "Para sumar el {pct} % del peso GRD hacían falta {n_base} GRD en {base} y {n_grd} en {foco}.",
    ),
    "cuadrante": (
        "{capitulo} suma {dif} puntos {sentido} del peso GRD que de los egresos en {foco}.",
        "La distancia entre el peso GRD y los egresos de {capitulo} {sentido} {dif} puntos entre {base} y {foco}.",
    ),
    "cronicas": (
        "{capitulo} es el {pct} % de los egresos por causas crónicas en {foco}.",
        "{capitulo} pesa {pct} puntos {sentido} entre las causas crónicas de {foco} que en {base}.",
    ),
    "fuera_region": (
        "En {foco}, el {pct} % de los egresos fue en un hospital de otra región que la del paciente.",
        "En {foco}, el {pct} % de los egresos fue en un hospital de otra región que la del paciente.",
    ),
    "cronicas_edad": (
        "En el grupo de {grupo} años, el {pct} % de los egresos de {foco} tiene {condicion}: es la proporción más alta del gráfico.",
        "En el grupo de {grupo} años, el {pct} % de los egresos de {foco} tiene {condicion}: es la proporción más alta del gráfico.",
    ),
    "mortalidad_cronicas": (
        "Con severidad mayor, el {mortalidad} % de los egresos con {combinacion} termina en fallecimiento, frente al {ninguna} % "
        "de los egresos sin ninguna de las enfermedades elegidas ({foco}), sin ajustar por edad.",
        "Con severidad mayor, el {mortalidad} % de los egresos con {combinacion} termina en fallecimiento, frente al {ninguna} % "
        "de los egresos sin ninguna de las enfermedades elegidas ({foco}), sin ajustar por edad.",
    ),
    "pares": (
        "El par más frecuente es {combinacion}: el {pct} % de las hospitalizaciones de {foco} tiene las dos.",
        "El par más frecuente es {combinacion}: el {pct} % de las hospitalizaciones de {foco} tiene las dos.",
    ),
    "region_paciente": (
        "{region} es la región de residencia del {pct} % de los egresos de {foco}.",
        "{region} es la región de residencia que más cambió: pesa {pct} puntos {sentido} en los egresos de {foco} "
        "que en los de {base}.",
    ),
    "flujos": (
        "El mayor movimiento entre regiones en {foco} va de {origen} a {destino}: {valor} egresos.",
        "El mayor movimiento entre regiones en {foco} va de {origen} a {destino}: {valor} egresos.",
    ),
    "calendario": (
        "Entre 2019 y {foco}, el mes más bajo fue {mes_bajo}, con {bajo} egresos por día; el más alto, {mes_alto}, con {alto}.",
        "Entre 2019 y {foco}, el mes más bajo fue {mes_bajo}, con {bajo} egresos por día; el más alto, {mes_alto}, con {alto}.",
    ),
    "pictograma": (
        "De cada 100 hospitalizaciones de {foco}, {una} tienen una enfermedad crónica y {varias}, dos o más.",
        "De cada 100 hospitalizaciones de {foco}, {una} tienen una enfermedad crónica y {varias}, dos o más.",
    ),
}


def capitulo_corto(etiqueta: str) -> str:
    """Etiqueta del capítulo sin el número romano y en minúscula, para ir dentro de una frase («XV. Embarazo…» → «embarazo…»)."""
    cabeza, _, resto = etiqueta.partition(". ")
    if not resto or cabeza.strip("IVXL") != "":
        return etiqueta
    return resto[0].lower() + resto[1:]


def cronicas_en_palabras(combinacion: str) -> str:
    """Combinación de crónicas en palabras: «DM+HTA+ERC» → «diabetes, hipertensión y ERC»."""
    nombres = [_CRONICAS.get(c, c) for c in combinacion.split("+")]
    if len(nombres) == 1:
        return nombres[0]
    ultimo = nombres[-1]
    y = "e" if ultimo.lower().startswith(("i", "hi")) and not ultimo.lower().startswith("hie") else "y"  # «diabetes e hipertensión»
    return ", ".join(nombres[:-1]) + f" {y} " + ultimo


def _en_frase(clave: str, x):
    """Ajusta un valor de texto para ir dentro de una frase."""
    if clave == "capitulo":
        return capitulo_corto(x)
    if clave == "combinacion":
        return cronicas_en_palabras(x)
    if clave == "condicion" and not x.isupper():
        return x.lower()
    return x


def lectura(clave: str, p: "Periodo", **v) -> str:
    """Arma la frase de lectura rápida de un gráfico según el modo del período."""
    plantilla = _PLANTILLAS[clave]
    if v.get("pocos_casos"):
        return POCOS_CASOS
    texto = plantilla[0] if p.modo == "un_anio" else plantilla[1]
    if clave in _SENTIDO and p.modo in _SENTIDO[clave][1]:
        k, (sube, baja) = _SENTIDO[clave][0], _SENTIDO[clave][1][p.modo]
        v = v | {k: abs(v[k]), "sentido": sube if v[k] >= 0 else baja}
    dec = _DEC | _DEC_LECTURA.get(clave, {})
    datos = {k: numero(x, dec.get(k, 1)) if k in NUMERICAS else _en_frase(k, x) for k, x in v.items()}
    texto = texto.format(foco=p.foco, base=p.base, **datos)
    return texto[0].upper() + texto[1:]
