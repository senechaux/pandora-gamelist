# Pandora 88S · Buscador de juegos

Web estática (HTML + CSS + JS, sin dependencias) para encontrar el ID de un juego de la
Pandora 88S R15 escribiendo parte de su nombre en español o en inglés.

## Archivos

| Archivo | Qué es |
| --- | --- |
| `index.html` | La página |
| `style.css` | Estilo retro 80s |
| `app.js` | Buscador, ordenación, copiar ID al portapapeles |
| `games.js` | Los datos que usa la página (`id`, nombre `es`, nombre `en`, versión principal, popularidad) |
| `images.js` | Qué pantalla de título se muestra para cada juego |
| `tools/fill_images.py` | Script que rellena `images.js` automáticamente |
| `tools/build_catalog.py` | Script que agrupa las versiones de cada juego y calcula su popularidad |
| `tools/popularity.csv` | Popularidad de los juegos conocidos (editable) |
| `tools/catalog_report.csv` | Informe: cada juego principal con sus versiones, popularidad y de dónde sale |
| `pandora88s_juegos.csv` | Los mismos datos en CSV (`id,es,en,version_de,popularidad`), descargables desde la web |

## Publicar en GitHub Pages

1. Crea un repositorio nuevo en GitHub y sube estos archivos a la raíz.
2. En el repo: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   rama `main`, carpeta `/ (root)`.
3. En un par de minutos estará en `https://<tu-usuario>.github.io/<repo>/`.

También funciona abriendo `index.html` directamente en el navegador.

## Uso

- Sin buscar, la lista muestra **un juego por título** (su versión principal), ordenado por popularidad.
  La etiqueta «+N VERSIONES» indica cuántas versiones más tiene (revisiones, regiones, hacks…).
- Al buscar aparecen **todas las versiones** que coinciden, cada una debajo de su juego principal
  (marcadas con «↳» y «VERSIÓN DE #id»). Si coincide el juego principal, salen todas sus versiones.
- Escribe cualquier trozo del nombre, en español o en inglés: busca en las dos columnas y
  muestra ambas. Se ignoran mayúsculas, acentos, espacios y signos, así que tanto
  `rey de los luchadores` como `king of fighters` encuentran `Elreydelosluchadores'97`
  (`TheKingofFighters'97`).
- Varias palabras sueltas también funcionan: `metal 3` encuentra `MetalSlug3`.
- Si escribes solo un número, el juego con ese ID aparece el primero (etiqueta «ID EXACTO»).
- Pulsa un juego (o Enter sobre él) para copiar su ID. `/` enfoca el buscador, `Esc` lo borra.
- Ordena por popularidad (por defecto), por ID o alfabéticamente por el nombre en español o en inglés.
- La búsqueda queda en la URL (`?q=...`), así que puedes compartir enlaces.

## Versiones y popularidad

El listado de la Pandora repite mucho cada juego: 36.801 entradas son unos 5.100 juegos distintos.
`tools/build_catalog.py` los agrupa y elige una versión principal para cada uno:

- **Mismo juego**: mismo nombre una vez quitadas revisiones (`rev2`), lotes (`[v1 ARCADE]`, `p.d`),
  regiones, jugadores (`3P`), versiones de placa (`V115`) y el prefijo de plataforma
  (`Aladdin` y `SFCAladdin` son el mismo juego).
- **Hacks y ediciones**: un nombre que prolonga el de otro juego con palabras como Plus, Hack, Boss,
  Invincible, Edition… es una versión suya (`TheKingofFighters'97Plus` → KOF '97). Las secuelas no:
  KOF '98 sigue siendo otro juego. Si un juego tiene muchos hacks, cualquier nombre que lo prolongue
  también cuenta (`TheKingofFighters'97TuSnake`), salvo que tenga su propia pantalla de título.
- **Versión principal**: la de nombre más limpio, en inglés si la hay y sin prefijo de plataforma.
- **Popularidad (1–999)**: los juegos y sagas de `tools/popularity.csv` reciben el valor de la tabla
  (600–999). Al resto se le estima entre 1 y 599 según si es un juego comercial conocido (tiene
  pantalla de título), en cuántas plataformas está, cuántos hacks tiene y si es uno de los destacados
  del principio del listado.

Para corregir algo, edita `tools/popularity.csv` y vuelve a generar los datos:

```bash
python3 tools/build_catalog.py --dry-run   # prueba: solo genera tools/catalog_report.csv
python3 tools/build_catalog.py             # actualiza pandora88s_juegos.csv y games.js
```

- Cada línea de `popularity.csv` es un patrón sobre la **clave** del juego (columna `clave` del informe)
  y gana la primera que encaje.
- Con `agrupar` = `si` se juntan en un solo juego todos los que encajen: sirve para hacks que tienen
  otro nombre, como los `DinosaurKombat…` de *Cadillacs & Dinosaurs*. La columna `principal` elige
  qué nombre se muestra.

## Imágenes

Cada juego con imagen muestra su pantalla de título (pasa el ratón por encima para ampliarla).
Las imágenes **no están en este repositorio**: la página las carga directamente desde
[libretro-thumbnails](https://github.com/libretro-thumbnails), el repositorio de miniaturas de RetroArch.

Los 100 primeros se revisaron a mano: 74 tienen su propia pantalla de título, 20 hacks de KOF '97
muestran la de *The King of Fighters '97* (borde discontinuo) y 6 juegos chinos poco conocidos
(IDs 18–22 y 24) no tienen imagen.

### Rellenar el resto automáticamente

`tools/fill_images.py` busca la pantalla de título de cada juego del CSV comparando su nombre en inglés
con los listados de libretro-thumbnails (arcade, NES, SNES, Mega Drive, PC Engine, Game Boy/Color/Advance,
N64, PlayStation, PSP…), y añade los enlaces a `images.js`. No descarga imágenes.

```bash
python3 tools/fill_images.py --dry-run   # prueba: solo genera tools/images_report.csv
python3 tools/fill_images.py             # rellena images.js
```

- Necesita Python 3.8+ (el de macOS vale) y nada más.
- Respeta las entradas que ya hay en `images.js`: puedes corregir una a mano y volver a ejecutarlo.
  Si borras una línea, se vuelve a buscar.
- Cuando no hay imagen exacta pero el juego es un hack o una edición especial ("…InvincibleEdition",
  "…Plus", "…HACKVersion"), usa la del juego original y la marca con borde discontinuo.
  Con `--exact-only` solo usa coincidencias exactas.
- Revisa `tools/images_report.csv` para ver qué imagen ha elegido para cada juego.
- Los listados se guardan en `tools/.cache/` (ignorada por git). `--refresh` los vuelve a pedir.
  Sin token, GitHub permite 60 peticiones por hora y el script hace unas 20; si hiciera falta,
  exporta `GITHUB_TOKEN` con un token personal.
- Encuentra imagen para ~46% de los juegos. El resto suelen ser nombres traducidos por máquina
  o hacks chinos que no existen en libretro-thumbnails.

### Cambiar una imagen a mano

Edita `images.js`: cada entrada es
`id: [sistema, "nombre del fichero sin .png"]`, con el nombre tal cual aparece en la carpeta
`Named_Titles` del repositorio de ese sistema.
