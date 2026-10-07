# Pandora 88S · Buscador de juegos

Web estática (HTML + CSS + JS, sin dependencias) para encontrar el ID de un juego de la
Pandora 88S R15 escribiendo parte de su nombre en español o en inglés.

## Archivos

| Archivo | Qué es |
| --- | --- |
| `index.html` | La página |
| `style.css` | Estilo retro 80s |
| `app.js` | Buscador, ordenación, copiar ID al portapapeles |
| `games.js` | Los datos (`id`, nombre `es`, nombre `en`) que usa la página |
| `images.js` | Qué pantalla de título se muestra para cada juego |
| `tools/fill_images.py` | Script que rellena `images.js` automáticamente |
| `pandora88s_juegos.csv` | Los mismos datos en CSV (`id,es,en`), descargables desde la web |

## Publicar en GitHub Pages

1. Crea un repositorio nuevo en GitHub y sube estos archivos a la raíz.
2. En el repo: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   rama `main`, carpeta `/ (root)`.
3. En un par de minutos estará en `https://<tu-usuario>.github.io/<repo>/`.

También funciona abriendo `index.html` directamente en el navegador.

## Uso

- Escribe cualquier trozo del nombre, en español o en inglés: busca en las dos columnas y
  muestra ambas. Se ignoran mayúsculas, acentos, espacios y signos, así que tanto
  `rey de los luchadores` como `king of fighters` encuentran `Elreydelosluchadores'97`
  (`TheKingofFighters'97`).
- Varias palabras sueltas también funcionan: `metal 3` encuentra `MetalSlug3`.
- Si escribes solo un número, el juego con ese ID aparece el primero (etiqueta «ID EXACTO»).
- Pulsa un juego (o Enter sobre él) para copiar su ID. `/` enfoca el buscador, `Esc` lo borra.
- Ordena por ID o alfabéticamente por el nombre en español o en inglés.
- La búsqueda queda en la URL (`?q=...`), así que puedes compartir enlaces.

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
