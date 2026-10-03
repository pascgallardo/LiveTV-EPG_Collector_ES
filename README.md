# LiveTV y EPG Collector ES

Repositorio de GitHub que recopila, filtra y exporta automáticamente enlaces de emisión de TV en vivo por país usando GitHub Actions. Este proyecto descarga listas M3U de múltiples fuentes, elimina duplicados y las exporta a varios formatos en el directorio `LiveTV/Country Name/`.

Fork de [bugsfreeweb/LiveTVCollector](https://github.com/bugsfreeweb/LiveTVCollector), actualmente centrado en **Spain**.

# 📊 Estadísticas del proyecto
[![GitHub forks](https://img.shields.io/github/forks/pascgallardo/LiveTV-EPG_Collector_ES?logo=forks&style=plastic)](https://github.com/pascgallardo/LiveTV-EPG_Collector_ES/network) [![GitHub stars](https://img.shields.io/github/stars/pascgallardo/LiveTV-EPG_Collector_ES)](https://github.com/pascgallardo/LiveTV-EPG_Collector_ES/stargazers) [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)  [![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](https://lbesson.mit-license.org/)
![GitHub issues](https://img.shields.io/github/issues/pascgallardo/LiveTV-EPG_Collector_ES)
![GitHub pull requests](https://img.shields.io/github/issues-pr/pascgallardo/LiveTV-EPG_Collector_ES)

## Herramientas utilizables online:
<a href="https://gmtv.netlify.app" target="_blank"><img src="https://gmtv.netlify.app/img/gmtv.png" style="width:auto; height:60px" alt="GM TV Player"></a>
<a href="https://lolstream.netlify.app" target="_blank"><img src="https://lolstream.netlify.app/img/logo.png" style="width:auto; height:60px" alt="Stream Player"></a>
<a href="https://pismarttv.netlify.app" target="_blank"><img src="https://pismarttv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="IPTV Player"></a>
<a href="https://hodliptv.netlify.app" target="_blank"><img src="https://hodliptv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="IPTV Player"></a>
<a href="https://pixstream.netlify.app" target="_blank"><img src="https://pixstream.netlify.app/img/logo.png" style="width:auto; height:60px" alt="IPTV Player"></a>
<a href="https://buddytv.netlify.app" target="_blank"><img src="https://buddytv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="BuddyTv"></a>
<a href="https://m3uchecker.netlify.app" target="_blank"><img src="https://m3uchecker.netlify.app/img/logo.png" style="width:auto; height:60px" alt="M3U Checker"></a>
<a href="https://birdseyetv.netlify.app" target="_blank"><img src="https://birdseyetv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="BirdseyeTV player"></a>
<a href="https://circletv.netlify.app" target="_blank"><img src="https://circletv.netlify.app/img/logo.png" style="width:auto; height:60px" alt="CircleTV player"></a>
<a href="https://bugsfreeweb.github.io/iptv" target="_blank"><img src="https://bugsfreeweb.github.io/iptv/img/logo.png" style="width:auto; height:60px" alt="IPTV player"></a>
<a href="https://m3ueditor.netlify.app" target="_blank"><img src="https://m3ueditor.netlify.app/img/logo.png" style="width:auto; height:60px" alt="M3U Editor"></a>
<a href="https://bugsfreeweb.github.io/WebIPTV" target="_blank"><img src="https://bugsfreeweb.github.io/iptv/img/logo.png" style="width:auto; height:60px" alt="Web IPTV"></a>
<a href="https://bugsfreetv.vercel.app" target="_blank"><img src="https://bugsfreetv.vercel.app/img/logo.png" style="width:auto; height:60px" alt="Web IPTV Player"></a>


## Características

- **Actualizaciones automáticas**: Se ejecuta una vez al día mediante GitHub Actions, programada para **08:00 UTC**. GitHub evalúa el cron en UTC y trata `schedule` como «best effort», así que la ejecución empieza realmente más tarde: medido sobre las 978 ejecuciones programadas que generó este repositorio entre abril y septiembre de 2026, el retraso mediano fue de 171 min a las 00:00 UTC, **154 min a las 08:00 UTC** y 103 min a las 16:00 UTC, y ninguna ejecución llegó a empezar antes de los 28 minutos. Las 16:00 UTC eran la franja menos saturada en el registro, pero después el cron se adelantó 8 h hasta las 08:00 UTC para publicar a media tarde española: el retraso es una cola que hay que pagar de todos modos, así que desplazar el cron desplaza la publicación en la misma medida, y los ~50 min de cola adicionales compensan de sobra las 8 h. En la práctica las playlists se republican aproximadamente entre las **11:30 y las 15:30 hora peninsular española**. No hay a propósito ninguna puerta horaria: una puerta nunca podría pasar, y lo único que habría conseguido es impedir que el workflow llegara a ejecutarse alguna vez. Véase [Programación](#programación) para las cifras completas.
- **Manejo de fuentes grandes**: Procesa las respuestas M3U línea a línea en lugar de cargar los ficheros enteros, y solo materializa el texto unido para las fuentes HTML que necesitan análisis.
- **Verificación opcional de enlaces activos**: Desactivada por defecto por velocidad. Ejecuta `python BugsfreeMain/TV-Spain.py --check-links` para sondear cada stream con 10 workers concurrentes (HEAD, con repliegue a GET y luego al protocolo alternativo). Los resultados se cachean por URL.
- **Eliminación de duplicados**: Garantiza que no se incluyan streams duplicados (según la URL). Cuando la misma URL llega desde varias playlists, la primera fuente conserva la propiedad, pero un `tvg-id` o `tvg-name` que a esa primera le faltara se completa desde una fuente posterior.
- **Metadatos tvg-***: `tvg-id` y `tvg-name` se leen de las líneas `#EXTINF` de la fuente y se arrastran a todos los formatos de exportación. Los atributos que una fuente no aporta se omiten simplemente de la línea `#EXTINF` generada.
- **Análisis de fuentes HTML**: Una fuente terminada en `.html` se explora en busca de playlists anidadas, descartando los enlaces que no son de emisión (p. ej., Telegram, GitHub).
- **Guías EPG fusionadas**: Las URLs de EPG (XMLTV) declaradas por cada playlist de origen se leen de su atributo `#EXTM3U url-tvg`, se registran en orden de origen en `epg-sources.json`, y `BugsfreeMain/TV-Spain-EPG.py` las fusiona en un único `LiveTV.xml` más su `LiveTV.xml.gz`. La playlist generada apunta a esa guía fusionada. Véase [EPG](#epg).
- **Orden de las fuentes preservado**: La playlist fusionada conserva el orden de sus entradas. Un canal se queda donde lo tenía su playlist de origen, los canales de la primera fuente van primero, y un grupo aparece donde apareció su primer canal. No se ordena alfabéticamente nada, así que el fichero se lee como las playlists con las que se construyó.
- **Canales duplicados por `tvg-name`**: Cuando varias entradas comparten el mismo `tvg-name`, solo sobrevive una: la primera en orden de playlist **cuyo stream responde de verdad**. El resto se descarta, de modo que un canal nunca aparece dos veces solo porque varios proveedores lo ofrezcan. Los canales sin `tvg-name` nunca se comparan entre sí.
- **Exportaciones deterministas**: El orden no está aleatorizado: las fuentes se consumen en una secuencia fija y la verificación de enlaces nunca reordena el resultado, así que volver a ejecutar sin cambios en las fuentes produce ficheros idénticos y ningún commit espurio. La única excepción es la deduplicación por `tvg-name`, que consulta el estado real de los streams por diseño: si un stream cae, la siguiente ejecución publica su copia de reserva operativa y ese commit es justamente la novedad.
- **Marcas de tiempo honestas**: El campo `date` de `LiveTV.json` es el momento en que el colector se ejecutó realmente, expresado en `Europe/Madrid` y escrito como ISO 8601 con un desfase UTC explícito (p. ej. `2026-09-30T21:14:07+02:00`). Como el cron de GitHub nunca se dispara a tiempo, este es el único instante de publicación fiable, y el desfase permite al navegador resolver el instante correctamente sea cual sea la zona horaria del visitante, así que el banner «actualizado hace N min» de `index.html` es exacto.
- **Web hub (`index.html`)**: Interfaz estática de navegador para explorar las playlists generadas, buscar canales, copiar o descargar enlaces y llevar estadísticas de descarga localmente.
- **Múltiples formatos de exportación**:
  - `LiveTV.m3u`: Playlist M3U estándar.
  - `LiveTV.txt`: Formato de texto legible con información detallada de cada canal.
  - `LiveTV.json`: JSON estructurado con metadatos de los canales.
  - `LiveTV`: Formato JSON personalizado sin extensión, pensado para integrarse con facilidad.

## Formatos de fichero exportados

### `LiveTV.m3u`
Formato de playlist M3U estándar. La línea `#EXTM3U` lleva en `url-tvg` las guías EPG de las fuentes fusionadas, de modo que la playlist generada conserva los datos de guía que traían sus fuentes:
```
#EXTM3U url-tvg="https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml, https://www.tdtchannels.com/epg/TV.xml.gz, https://live.s2l.workers.dev/epg.xml"
#EXTINF:-1 tvg-id="AdventureTV.us" tvg-name="Adventure TV" tvg-logo="https://i.imgur.com/VQVr4Nk.png" group-title="Entertainment",Adventure TV
http://109.233.89.170/Adventure_HD/index.m3u8
```

Se lee el atributo `#EXTM3U url-tvg` de cada fuente y las URLs se fusionan en orden de origen, descartando las guías que varias fuentes comparten. Las fuentes que no declaran ninguna EPG simplemente no aportan nada, y cuando ninguna fuente tiene una la línea se queda desnuda, como `#EXTM3U`.

`url-tvg` solo contiene URLs de guías XMLTV (`.xml` / `.xml.gz`); las playlists M3U nunca se listan ahí, ya que ese atributo es el puntero convencional a los datos EPG.

`tvg-id` y `tvg-name` en las líneas `#EXTINF` solo se emiten cuando la playlist de origen los proporcionó.

### `LiveTV.txt`
Formato de texto legible. `TvgID` y `TvgName` solo se escriben cuando existen:
```
Group: Entertainment
Name: Adventure TV
TvgID: AdventureTV.us
TvgName: Adventure TV
URL: http://109.233.89.170/Adventure_HD/index.m3u8
Logo: https://i.imgur.com/VQVr4Nk.png
Source: https://example.com/source.m3u
--------------------------------------------------
```

### `LiveTV.json`
JSON estructurado con marca de tiempo:
```json
{
  "date": "2026-09-30T21:14:07+02:00",
  "channels": {
    "Entertainment": [
      {
        "name": "Adventure TV",
        "tvg_id": "AdventureTV.us",
        "tvg_name": "Adventure TV",
        "logo": "https://i.imgur.com/VQVr4Nk.png",
        "group": "Entertainment",
        "source": "https://example.com/source.m3u",
        "url": "http://109.233.89.170/Adventure_HD/index.m3u8"
      }
    ]
  }
}
```

### `LiveTV` (formato personalizado)
Lista JSON personalizada sin extensión:
```json
[
  {
    "name": "Adventure TV",
    "tvg_id": "AdventureTV.us",
    "tvg_name": "Adventure TV",
    "type": "Entertainment",
    "url": "http://109.233.89.170/Adventure_HD/index.m3u8",
    "img": "https://i.imgur.com/VQVr4Nk.png"
  }
]
```

## Instrucciones de instalación

### Requisitos
- Una cuenta de GitHub y un repositorio (`pascgallardo/LiveTV-EPG_Collector_ES`).
- No hace falta ningún entorno local; todo se ejecuta mediante GitHub Actions.

### Pasos
1. **Clonar o bifurcar**:
   ```bash
   git clone https://github.com/pascgallardo/LiveTV-EPG_Collector_ES.git
   cd LiveTV-EPG_Collector_ES
   ```

2. **Personalizar las fuentes** (opcional):
   - Edita `BugsfreeMain/TV-Spain.py` para actualizar la lista `source_urls` con fuentes M3U adicionales.

3. **Subir los cambios**:
   ```bash
   git add .
   git commit -m "Initial setup or source update"
   git push origin main
   ```

4. **Verificar el workflow**:
   - Ve a la pestaña «Actions» de tu repositorio de GitHub.
   - El workflow «TV-Spain Update Files» se ejecuta a diario (cron `0 8 * * *`, UTC) o se puede lanzar manualmente.

## Cómo funciona

1. **Descarga de fuentes**:
   - Transmite los ficheros M3U y analiza el HTML en busca de URLs de emisión.
   - Usa `requests` con streaming para poder manejar ficheros grandes.

2. **Procesamiento**:
   - Elimina duplicados según la URL del stream.
   - Colapsa los `tvg-name` duplicados de toda la playlist fusionada, conservando la primera entrada cuyo stream responde (véase [Deduplicación por `tvg-name`](#deduplicación-por-tvg-name)).
   - Opcionalmente verifica la actividad de los enlaces con peticiones HEAD/GET concurrentes (2 segundos de tiempo de espera, 10 workers) cuando se pasa `--check-links`.

3. **Exportación**:
   - Guarda los canales únicos en cuatro ficheros dentro de `LiveTV/Country Name/`, en orden de fuente, para que los diffs sigan siendo pequeños y predecibles.

4. **Automatización**:
   - GitHub Actions ejecuta `BugsfreeMain/TV-Spain.py` una vez al día, programada para las 08:00 UTC.
   - Un segundo job regenera `LiveTV/index.json` y `Movies/index.json` a partir de los directorios presentes.
   - Commitea y sube los cambios automáticamente usando `GITHUB_TOKEN`.

## Uso local

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .       # run the test suite
python BugsfreeMain/TV-Spain.py                # fast: no link verification
python BugsfreeMain/TV-Spain.py --check-links # slower: drop unreachable streams
python generate_indexes.py                     # refresh section indexes
```

`index.html` es una página estática: sirve la raíz del repositorio desde cualquier host estático y leerá los ficheros generados desde la URL raw de GitHub (primero este repositorio, y el repositorio upstream como alternativa).

## Deduplicación por `tvg-name`

Los proveedores se solapan, así que el mismo canal llega muchas veces: `La 1` desde `Generalistas` y otra vez desde `Entretenimiento`, `Runtime` desde tres hosts distintos. Tras la deduplicación por URL (que solo elimina el mismo stream repetido) la playlist fusionada todavía llevaba **82 grupos de `tvg-name` duplicados que cubrían 182 canales**. El colector ahora los colapsa.

**Cómo se elige el ganador.** Los candidatos se ordenan por su posición en la playlist fusionada y se sondean en ese orden; gana el primero cuyo stream responde y el resto se descarta. Si ninguno responde, se conserva el primero igualmente — una sonda que falla por un tirón de red nunca debe hacer desaparecer un canal de la playlist publicada.

**Cómo se comparan los nombres.** La clave es el `tvg-name` recortado, con los espacios internos colapsados y sin distinguir mayúsculas, así que `La 1`, `la 1  ` y `LA 1` son el mismo canal. Comparar cadenas en bruto habría encontrado 72 grupos en vez de 82 y se habría perdido variantes reales como `Pocoyó`/`pocoyó` o `24h`/`24H`.

**Alcance.** La coincidencia es global en toda la playlist, no por categoría, porque 81 de los 82 grupos duplicados abarcan más de una categoría. Una consecuencia que conviene conocer: tras la deduplicación, un canal que antes aparecía tanto en `Generalistas` como en `Entretenimiento` se queda solo en la categoría que venga primero.

**Los canales sin `tvg-name` nunca se comparan.** No hay nada con lo que emparejarlos, así que se conservan los 69. Tratar el valor vacío como una única clave habría borrado 68 canales.

**Coste.** Los grupos se resuelven en paralelo y cada grupo deja de sondear en cuanto encuentra su ganador, así que una ejecución sondea unas 94 URLs en lugar de las 182 implicadas — una fracción de las 929 que necesitaría una pasada completa con `--check-links`. Con `--check-links` las respuestas ya están en la caché de estado de enlaces y la deduplicación no cuesta ninguna petición extra.

**Orden.** No se reordena nada: los canales que sobreviven conservan su posición, y una categoría conserva la posición de su primer canal superviviente. Una categoría que se queda sin canales desaparece. Medido sobre las fuentes reales: 929 → 829 canales, 42 categorías sin cambios, y las 829 entradas supervivientes exactamente en el mismo orden que antes.

**Determinismo.** Este es el único punto donde la exportación depende de algo que no son las fuentes. Un stream que cae hará que la siguiente ejecución publique su copia de reserva, y uno que vuelve hará que cambie de nuevo, así que el commit diario ya no es una función pura de las playlists. Ese es el comportamiento buscado, pero se renuncia a parte de la garantía de exportación determinista descrita arriba.

## EPG

`LiveTV.m3u` lleva un atributo `url-tvg` que apunta a `LiveTV/Spain/LiveTV.xml.gz`, la guía única que construye `BugsfreeMain/TV-Spain-EPG.py`. Se refresca con su propia programación, `0 8 */2 * *`, es decir cada 48 horas a las 08:00 UTC.

### Qué hace la fusión

Las nueve guías de origen que declaran las playlists fusionadas suman **82 MB de XMLTV** que describen 2 267 canales, de los cuales la playlist publicada lista 737 `tvg-id`. Todo se filtra a esos 737 antes de escribirse, y esa es la diferencia entre publicar todo y publicar una guía que encaja con la playlist a la que pertenece: guiatv.xml por sí solo son 33 MB con 644 canales, y solo 72 de ellos están en la playlist.

Tres cosas deciden qué acaba en el fichero:

- **Solo sobreviven los `tvg-id` de la playlist.** Tanto el `<channel id>` de una guía como el atributo `channel` de un `<programme>` tienen que ser uno de ellos. Los 26 canales sin entrada de guía simplemente no tienen programación, y una guía llena de canales que nadie de esta playlist ve es lastre muerto para un reproductor.
- **La primera guía que declara un canal es su propietaria.** guiatv.xml y los workers de s2l se reflejan mutuamente, así que la propiedad debe decidirse una sola vez y siempre igual, o la salida dependería de qué descarga terminara primero.
- **Los programas se deduplican por canal, inicio y fin.** Las guías que cubren rangos horarios distintos aportan todas; las que repiten el mismo rango no. Con los datos actuales esto baja de 36 157 programas coincidentes a 26 915.

Resultado actual: **712 de 737 canales (96.6 %) y 27 067 programas**, como un `LiveTV.xml` de 13.2 MB y un `LiveTV.xml.gz` de 1.7 MB.

### Por qué las fuentes viven en un fichero aparte

Apuntar `url-tvg` a la guía fusionada hace que la playlist deje de decir de dónde salió esa guía, lo que dejaría al fusionador sin forma de encontrar sus propias entradas — leería la cabecera, encontraría su salida anterior y fusionaría eso. Por eso el colector escribe además la lista de fuentes en `LiveTV/Spain/epg-sources.json`, y eso es lo que lee el fusionador. La cabecera `url-tvg` sigue aceptándose como alternativa para una copia de trabajo anterior al manifest, filtrando cualquier entrada que apunte a la propia salida del fusionador.

### Las guías se leen comprimidas

Las nueve se sirven comprimidas con gzip, incluidas `guiatv.xml` y `runtime.xml`, cuyas URLs no terminan en `.gz`. Por eso la descompresión se decide por los bytes mágicos de gzip y nunca por la extensión.

### Reproducibilidad

A diferencia de la playlist, la guía fusionada *no* es una función pura de sus entradas: las guías de origen se regeneran constantemente con marcas de tiempo nuevas, así que una ejecución real produce casi siempre un fichero nuevo y un commit nuevo. Lo que sí se puede fijar, y se fija, es todo lo que este script controla. El flujo gzip se escribe con `mtime=0` y sin nombre de fichero almacenado, de modo que el archivo es una función pura del XML que tiene al lado, y en el documento no se escribe ninguna marca de tiempo — el instante de publicación ya está en el commit y en `LiveTV.json`. Dos ejecuciones sobre guías sin cambios producen por tanto ficheros idénticos byte a byte.

### Cuándo se niega a publicar

Una ejecución que sustituiría una buena guía por otra inservible falla en vez de escribir. Eso cubre tanto que fallen todas las descargas como que el filtro no encuentre nada, y ambos casos se informan como las causas distintas que son: el primero es un problema de red, el segundo significa que la playlist cambió de forma.

Nota sobre el tamaño: la guía fusionada se commitea cada 48 horas y cambia casi por completo cada vez, así que añade del orden de 1.7 MB por ejecución al historial del repositorio. Publicar solo el `.gz` lo reduciría a la mitad.

## Programación

El `schedule` de GitHub Actions es «best effort»: el disparo se respeta, el hora de inicio no. Este repositorio antes usaba tres franjas al día (`0 0,8,16 * * *`), lo que da un conjunto de datos limpio para medir ese comportamiento. A lo largo de las **978 ejecuciones programadas que generó entre abril y septiembre de 2026**, el retraso entre el minuto programado y el momento en que la ejecución arrancó de verdad fue:

| Franja | Ejecuciones | Mediana | Media | p75 | p90 | Arrancaron en +1 h | +2 h |
|---|---|---|---|---|---|---|---|
| `00:00Z` | 326 | 171 min | 180 min | 224 min | 251 min | 0.0 % | 15.3 % |
| `08:00Z` | 326 | 154 min | 170 min | 215 min | 287 min | 6.1 % | 27.6 % |
| **`16:00Z`** | 326 | **103 min** | 107 min | 128 min | 197 min | **19.3 %** | **69.0 %** |

Dos hechos marcaron la configuración:

1. **Las 16:00 UTC eran la franja menos saturada.** Tenía el retraso mediano más bajo en cada uno de los seis meses del registro, no solo en el conjunto. `00:00Z` son las 20:00 en la costa este de EE. UU., la franja más cargada de la plataforma; las 16:00Z son mediodía allí.
2. **En cinco meses ninguna ejecución arrancó antes de los 28 minutos.** Por eso la antigua puerta «ejecutar solo a las 12:00 Europe/Madrid» — que despertaba el workflow dos veces al día y solo lo dejaba pasar dentro de una ventana de ±30 min — nunca podía tener éxito: habría rechazado más del 98 % de las ejecuciones y el workflow no habría publicado nada.

Así que el cron es una sola entrada **sin ninguna puerta**. `workflow_dispatch` sigue ejecutando el colector de inmediato, sea cual sea la hora local. El workflow registra la hora real de inicio en UTC y en `Europe/Madrid` en cada ejecución, y `LiveTV.json` lleva ese mismo instante como su `date`, de modo que `index.html` puede mostrar un honesto «actualizado hace N min».

El [EPG](#epg) fusionado tiene su propio workflow, `TV-Spain-EPG.yml`, en `0 8 */2 * *`. El cron no tiene paso de 48 horas, así que los días pares del mes es lo más cerca que se puede: el intervalo es exactamente de 48 h dentro de un mes y se acorta a 24 h al cruzar la frontera, del 30 al 1. Deliberadamente no comparte franja con el colector de playlists, que reescribe precisamente los ficheros que lee el job de la guía.

### Por qué el cron está a las 08:00 UTC

La franja menos saturada no es lo mismo que la franja que quieres. El retraso es una cola, no un desfase fijo, así que hay que pagarlo en la franja que elijas: adelantar el cron 8 h adelanta la publicación 8 h y no recupera nada. Ejecutar con `0 8 * * *` en lugar de `0 16 * * *` cuesta por tanto unos 50 min de cola adicionales (mediana 154 min frente a 103 min) y devuelve 8 h de luz, dejando las listas refrescadas a media tarde española en lugar de a última hora de la noche.

Ventana prevista de publicación en hora peninsular española: aproximadamente **11:30–15:30**, con una mediana en torno a las 12:35.

### Registro de validación

| Ejecución | Disparador | Inicio (UTC) | Inicio (Madrid) | Retraso frente a 16:00Z | Resultado |
|---|---|---|---|---|---|
| [#660](https://github.com/pascgallardo/LiveTV-EPG_Collector_ES/actions/runs/36719445370) | `workflow_dispatch` | 2026-09-30 13:07:56 | 15:07:56 | — (manual) | ambos jobs en verde, listas commiteadas como `09ebe56` |
| [#661](https://github.com/pascgallardo/LiveTV-EPG_Collector_ES/actions/runs/36772879590) | `schedule` | 2026-09-30 20:28:33 | **22:28:33** | **+4 h 28 min** | ambos jobs en verde, listas commiteadas como `d085833` |

#660 confirmó que el proceso funciona de principio a fin sin puerta. #661 fue la primera ejecución programada y por tanto la primera medición real de la franja: un **retraso de 268 min**, frente a una mediana histórica de 103 min para las 16:00Z y un récord de 28 min. Eso la sitúa en el percentil 98.7 de las 200 ejecuciones programadas más recientes, aunque por debajo del peor caso registrado (325 min), así que por sí sola no prueba nada nuevo — es una sola muestra, y la franja se movió en base al panorama de seis meses y no a esta ejecución.

Desde #661 el retraso se mide frente a `08:00Z`, donde la mediana histórica era de 154 min.

Si alguna vez hacer falta una hora exacta de reloj como requisito duro, la solución es dejar de depender de `schedule` por completo: llamar al endpoint `workflow_dispatch` desde un planificador externo.

## Pruebas

La suite usa solo la biblioteca estándar (`unittest`), así que no hace falta ninguna dependencia extra. Nunca toca la red: todas las llamadas HTTP están simuladas y los ficheros generados se escriben en un directorio temporal.

`tests/test_tv_spain.py` cubre:

- **Análisis de M3U** — atributos `#EXTINF`, `tvg-logo` ausente o vacío (logo por defecto), `group-title` ausente (`Uncategorized`), nombre ausente (`Unnamed Channel`), URLs huérfanas, líneas de directiva como `#EXTVLCOPT`, entradas `#EXTINF` consecutivas, y que los diccionarios de canal no sean mutados por la entrada siguiente.
- **Metadatos tvg** (`TestTvgMetadataParsing`, `TestTvgMetadataMerging`, `TestTvgMetadataExports`) — leer `tvg-id` y `tvg-name` sea cual sea el orden de los atributos, valores con espacios y comas, comillas que no pueden corromper una línea, rellenar los metadatos que falten desde una fuente posterior sin sobrescribir nunca los valores existentes, emitir los atributos en el M3U solo cuando están presentes, y un viaje de ida y vuelta que vuelve a analizar una playlist exportada.
- **Deduplicación por URL** — URLs repetidas dentro de una playlist, entre fuentes distintas (gana la primera), nombres idénticos con URLs distintas (se conservan ambos), y que `seen_urls` se reinicie entre ejecuciones.
- **Filtrado de enlaces** — cada URL única sondeada una sola vez aunque varios canales la compartan, canales muertos descartados, URL resuelta reemplazando a la original, y `check_links=False` saltándose el sondeo por completo.
- **Comprobación de enlaces** — éxito, estado de error devolviendo `(False, url)` en lugar de `None`, repliegue de HEAD a GET, reintento con el protocolo alternativo, y la caché por URL.
- **Extracción de fuentes HTML** — detección de playlists, resolución de enlaces relativos y hosts excluidos.
- **Exportaciones** — los cuatro ficheros de salida, la estructura `#EXTM3U`, y que los cuatro formatos coincidan en el mismo orden de canales.
- **Orden de fuentes** (`TestSourceOrderIsPreserved`) — una única fuente conserva su propio orden, los canales de la primera fuente van antes que los de la segunda, se respeta el orden declarado de las fuentes, un grupo conserva la posición de su primer canal, una segunda ejecución idéntica produce el mismo orden, las cuatro exportaciones coinciden, la verificación de enlaces con `--check-links` no reordena el resultado (futures que terminan en orden inverso siguen exportando en orden de fuente), y los canales descartados no perturban el resto.
- **Marcas de tiempo** (`TestExportTimestamp`) — que el `date` publicado sea hora local de Madrid tanto bajo CET como bajo CEST, que lleve un desfase explícito, y que se convierta de vuelta al mismo instante.
- **Cabecera EPG del M3U** (`TestM3UEpgHeader`) — que el `url-tvg` de cada fuente se lea de su línea de cabecera, que los valores de una y varias URLs se separen y se recorten, que las fuentes sin EPG no aporten nada, que varias fuentes se fusionen en orden, que una guía compartida por dos fuentes se liste una sola vez, que la lista se vacíe entre ejecuciones, que la cabecera quede desnuda sin EPG, que la M3U de origen nunca se filtre a `url-tvg`, y que las entradas de stream sigan a la cabecera.
- **Deduplicación por `tvg-name`** (`TestTvgNameDeduplication`) — que la clave recorte, colapse espacios e ignore mayúsculas, y sea `None` sin un `tvg-name` utilizable; que los canales sin metadatos se conserven todos; que gane la primera copia cuando su stream responde; que la búsqueda recurra a la siguiente copia, y a la primera cuando nada responde; que el sondeo se detenga en el ganador; que la URL resuelta reemplace la del ganador; que los duplicados coincidan entre categorías y entre variantes de mayúsculas y espaciado; que los canales únicos no se sondeen nunca; que los supervivientes y las categorías conserven su orden, que una categoría vaciada desaparezca, que las cuatro exportaciones coincidan, y que una ejecución con `--check-links` reutilice la caché de estado en vez de sondear otra vez.

`tests/test_workflow_schedule.py` protege la configuración de programación: un único cron a las 08:00 UTC, en punto, coincidiendo con el banner que imprime el workflow y con la hora que anuncia el README, ningún job de puerta horaria sobrante, ninguna referencia obsoleta al script de la puerta eliminado y una cadena de jobs bien formada.

`tests/test_tv_spain_epg.py` protege la [fusión del EPG](#epg): el filtro de `tvg-id` tanto en canales como en programas, el desescapado que rescata un id como `Crimen&amp;Historia`, la deduplicación entre guías reflejadas, que la primera guía gane la propiedad, que la entrada malformada se salte en vez de ser fatal, que el contenedor gzip no lleve marca de tiempo ni nombre de fichero, y las dos guardas de «no publicar» — incluido que las dos se informen como las causas distintas que son.

`tests/test_epg_workflow.py` protege el workflow de la guía: la cadencia `0 8 */2 * *` y su deriva en el cambio de mes documentada, que se commiteen los dos ficheros publicados, que la playlist quede intacta, y que los dos cron no choquen.

La fusión del EPG también se comprobó por mutación: 23 defectos deliberados — quitar cualquiera de las dos mitades del filtro de `tvg-id`, desactivar la normalización o el desescapado, eliminar la deduplicación, invertir el orden de descarga, limpiar elementos anidados, copiar elementos por referencia, estampar el gzip o el documento, publicar una fusión vacía, dejar que la alternativa lea su propia salida, y los cambios del manifest y de la cabecera — todos hacen fallar la suite.

## Dependencias

Declaradas en `requirements.txt` e instaladas por el workflow con `pip install -r requirements.txt`:
- `requests`: Para descargar contenido M3U y HTML.
- `beautifulsoup4`: Para el análisis de HTML.

El manejo de zonas horarias usa `zoneinfo` de la biblioteca estándar, así que no hay ninguna dependencia de terceros para eso. La marca de tiempo publicada es el momento en que el colector se ejecutó de verdad: no se puede confiar en que el cron de GitHub inicie un workflow a su hora, así que estampar el minuto programado sería una mentira.

## Resolución de problemas

- **Ficheros vacíos**: Revisa los logs de Actions en busca de errores:
  - `Failed to fetch <url>` o `No content fetched from <url>`: La fuente puede estar caída o ser inaccesible.
  - `No channels parsed from sources`: Verifica el formato de la fuente (`#EXTINF:` seguido de la URL).
  - `No channels exported`: El workflow registra un aviso y la ejecución falla, para que nunca se commitee una exportación rota.

- **Error de permisos**: Asegúrate de que `permissions: contents: write` está en `TV-Spain.yml`.

- **Índices desactualizados**: El job `update-indexes` se ejecuta después del colector y regenera los ficheros `index.json`. Usa el workflow reutilizable propio de este repositorio (`.github/workflows/update-indexes.yml`), así que no le afectan los cambios del upstream.

- **Logs**: Consulta los logs detallados en la pestaña «Actions» para diagnosticar problemas.

## Cómo contribuir

No dudes en:
- Añadir más fuentes a `BugsfreeMain/TV-Spain.py`.
- Proponer mejoras mediante issues o pull requests.

## Licencia

Este proyecto es de código abierto y está disponible bajo la [Licencia MIT](LICENSE) (añade un fichero `LICENSE` si lo deseas).

## Aviso legal

Este proyecto existe únicamente con fines educativos y de investigación. Agrega enlaces de emisión disponibles públicamente en distintas fuentes de internet por comodidad, y no aloja, distribuye ni ofrece por sí mismo ningún contenido de emisión. Quienes mantienen este repositorio no están afiliados a los proveedores de contenido ni a los streams listados en los ficheros exportados.

- **Responsabilidad de uso**: Quien lo usa es responsable de asegurarse de que su uso de los enlaces de emisión cumple la legislación y la normativa local, incluidos los derechos de autor y de propiedad intelectual.
- **Sin garantía**: Los enlaces proporcionados provienen de repositorios de terceros y pueden dejar de estar disponibles o cambiar sin aviso. Este proyecto no ofrece ninguna garantía sobre la disponibilidad, la calidad ni la legalidad de los streams.
- **Propiedad del contenido**: Todo el contenido de emisión pertenece a sus respectivos titulares, y este proyecto no reclama ninguna propiedad ni respalda ningún contenido concreto.

Al usar este repositorio o los ficheros que genera, reconoces y aceptas estas condiciones.

## Política de uso
- Solo uso personal: Estos ficheros están destinados a uso personal y no comercial.
- Sin redistribución con ánimo de lucro: No redistribuyas ni vendas estos ficheros con fines comerciales.
- Respeta los términos de las fuentes: Adhiérete a las condiciones de servicio de los proveedores originales de los streams.
- Atribución: Si compartes o usas estos datos, cita a bugsfreeweb/LiveTVCollector.
- Modificación: Puedes modificar los ficheros para uso personal, pero no los presentes como contenido oficial ni respaldado.

## Donar al proyecto
- DOGE: <b>DEtH2yFUjjUEBUyd3scjs38X7S1Z7ee7zD</b>
- BTC Lightening: <b>bugsfree@speed.app</b>
- SOL: <b>bugsfree.sol</b>
- EVM: <b>bugsfree.bnb</b>
