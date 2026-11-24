# NexoViewer: Observatorio GRD Chile

Dashboard para explorar los egresos hospitalarios codificados en GRD (Grupos Relacionados por el Diagnóstico) de los hospitales públicos de Chile entre 2019 y 2025, a partir de los datos abiertos de FONASA. Está pensado para investigadores y analistas de salud pública que no programan: se filtran los datos, se miran indicadores ya calculados y se descargan las tablas. La herramienta muestra los datos y no saca conclusiones.

## Qué tiene

- **Inicio**: resumen de lo elegido: egresos, estancia, casemix y mortalidad; serie mensual, capítulos de diagnóstico, edad y sexo, mapa por región de residencia, tabla de hospitales con el índice de estancia relativa y mapa de los hospitales.
- **Análisis**: cuatro preguntas, una por pestaña: evolución de las hospitalizaciones, perfil de los egresos (con la comorbilidad que elige quien explora), cómo se reparte el peso GRD y qué regiones tienen más egresos atendidos fuera de su región.
- **Hospitales**: un hospital a elección, con su ficha del catálogo del DEIS, sus cifras y un mapa del origen de sus egresos, y cinco pestañas: Actividad (frente al país, su región u otra región), Edad y origen, Casos y estancia, Comorbilidad y Camas (REM20).
- **Descargas**: las tablas agregadas en Excel (con hojas de filtros y de cita) y CSV, y el diccionario de datos.
- **Metodología**: fuentes, cobertura, tratamiento de los datos, cómo se calcula cada indicador, definición de comorbilidad, límites, cómo citar y glosario.

Los filtros están en la barra lateral y cambian los números al pulsar «Aplicar». Las plantillas guardan un conjunto de filtros y se pueden exportar e importar como JSON. Inicio, Análisis, Hospitales y Descargas tienen un recorrido guiado que se abre la primera vez y se repite con «Ver recorrido».

## Instalación

Necesitas **Python 3.12 o superior** (https://www.python.org/downloads/; en Windows, marca «Add python.exe to PATH») y Git. Las tablas del dashboard (unos 24 MB) vienen en el repositorio: no hay que descargar nada de FONASA.

1. Clona el repositorio:

   ```bash
   git clone https://github.com/RoqueLafuente/NexoViewer-Observatorio-GRD-Chile.git NexoViewer
   cd NexoViewer
   ```

2. Crea un entorno e instala lo necesario (una sola vez, 1 o 2 minutos):

   ```bash
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements-app.txt
   ```

   En macOS o Linux: `python3 -m venv .venv` y `.venv/bin/python -m pip install -r requirements-app.txt`.

3. Abre el dashboard:

   ```bash
   .venv\Scripts\python.exe -m streamlit run app/app.py --server.fileWatcherType none
   ```

   Se abre en http://localhost:8501 (en macOS o Linux, `.venv/bin/python -m streamlit run ...`). Se cierra con `Ctrl + C` en la terminal. Si el puerto 8501 está ocupado, agrega `--server.port 8601`.

### Para que vaya rápido

- La primera visita a cada página lee los datos y tarda unos segundos; las siguientes son casi instantáneas. Antes de mostrarlo a alguien, recorre una vez Inicio, Análisis, Hospitales (con sus pestañas) y Descargas.
- No reinicies el servidor después de recorrerlo: la caché vive en memoria.
- En un computador lento, desactiva las animaciones del sistema (en Windows: Configuración › Accesibilidad › Efectos visuales › Efectos de animación).

## Estructura

```
app/                        código del dashboard (app.py es la entrada; paginas/ tiene una página por archivo)
app/recursos/               mapa de regiones, diccionario de datos, logo y recorrido guiado (Driver.js)
datos_procesados/agregados/ tablas agregadas en Parquet que lee la app
GLOSARIO.md                 términos, indicadores y gráficos (también se ve en Metodología)
requirements-app.txt        dependencias
```

## Fuentes y cómo citar

- **Egresos GRD**: FONASA, Datos Abiertos (https://datosabiertos.fonasa.cl), 2019–2025.
- **Camas y ocupación**: REM20, DEIS-MINSAL (https://deis.minsal.cl).
- **Ficha y ubicación de los hospitales**: catálogo de establecimientos de salud del DEIS-MINSAL (https://datos.gob.cl/dataset/3bf4cf7c-f638-4735-9a01-f65faae4beca).
- **Mapa de regiones**: Biblioteca del Congreso Nacional, vía geoBoundaries (https://www.geoboundaries.org, CHL ADM1).

Cita sugerida: «Fuente: FONASA, Datos Abiertos (https://datosabiertos.fonasa.cl). NexoViewer: Observatorio GRD Chile, fecha de consulta». Cada Excel de Descargas trae esta cita y los filtros usados.

## Licencia y datos

El código está bajo la licencia **PolyForm Noncommercial 1.0.0** (archivo `LICENSE`): se puede usar, modificar y compartir sin fines comerciales, dando crédito. El uso comercial requiere permiso del autor.

Required Notice: Copyright (c) 2026 Roque Lafuente

Los textos de documentación (este README y `GLOSARIO.md`) están bajo **CC BY-NC 4.0**. Los datos conservan sus propias condiciones:

- FONASA, Datos Abiertos: hay que citar la fuente en toda difusión («Fuente: FONASA, Datos Abiertos»).
- Catálogo de establecimientos del DEIS-MINSAL: Creative Commons CCZero (CC0).
- REM20 del DEIS-MINSAL: datos públicos; se cita la fuente.
- Mapa de regiones (geoBoundaries, origen BCN): Creative Commons Attribution 3.0 IGO (CC BY 3.0 IGO).
- Driver.js 1.10.2, incluido en `app/recursos/driver/`: licencia MIT.
