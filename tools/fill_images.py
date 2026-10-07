#!/usr/bin/env python3
"""
Rellena images.js con la pantalla de título de cada juego del CSV.

No descarga imágenes: consulta el listado de ficheros de los repositorios de
https://github.com/libretro-thumbnails (carpeta Named_Titles) y escribe en
images.js el enlace a la imagen que mejor encaja con el nombre en inglés.

Uso (desde la carpeta del proyecto):
    python3 tools/fill_images.py              # rellena images.js
    python3 tools/fill_images.py --dry-run    # solo genera el informe, no toca images.js
    python3 tools/fill_images.py --help       # todas las opciones

- Las entradas que ya existen en images.js se respetan (no se sobrescriben),
  así que las que corrijas a mano se mantienen. Borra una línea para que se vuelva a buscar.
- Los listados se guardan en tools/.cache/ para no repetir peticiones; usa --refresh para renovarlos.
- Sin token, GitHub permite 60 peticiones por hora y el script hace una por sistema (~20).
  Si te quedas sin cupo, exporta GITHUB_TOKEN con un token personal (sin permisos especiales).
- Genera tools/images_report.csv con lo que ha encontrado para cada juego, para que lo revises.

Solo usa la biblioteca estándar de Python 3.8+.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OWNER = "libretro-thumbnails"
BASE = "https://raw.githubusercontent.com/libretro-thumbnails/"

# Clave corta -> repositorio de libretro-thumbnails. El orden es la prioridad
# cuando un juego sin prefijo de plataforma aparece en varios sistemas.
SYSTEMS = {
    "fbneo": "FBNeo_-_Arcade_Games",
    "mame": "MAME",
    "ps1": "Sony_-_PlayStation",
    "psp": "Sony_-_PlayStation_Portable",
    "n64": "Nintendo_-_Nintendo_64",
    "snes": "Nintendo_-_Super_Nintendo_Entertainment_System",
    "md": "Sega_-_Mega_Drive_-_Genesis",
    "nes": "Nintendo_-_Nintendo_Entertainment_System",
    "fds": "Nintendo_-_Family_Computer_Disk_System",
    "pce": "NEC_-_PC_Engine_-_TurboGrafx_16",
    "sgx": "NEC_-_PC_Engine_SuperGrafx",
    "pcecd": "NEC_-_PC_Engine_CD_-_TurboGrafx-CD",
    "gba": "Nintendo_-_Game_Boy_Advance",
    "gbc": "Nintendo_-_Game_Boy_Color",
    "gb": "Nintendo_-_Game_Boy",
    "sms": "Sega_-_Master_System_-_Mark_III",
    "gg": "Sega_-_Game_Gear",
    "dc": "Sega_-_Dreamcast",
    "ps2": "Sony_-_PlayStation_2",
    "dos": "DOS",
}

# Prefijo del nombre en el CSV -> sistemas donde buscar (solo esos)
PREFIXES = [
    ("GBA", ["gba"]),
    ("GBC", ["gbc", "gb"]),
    ("GB", ["gb", "gbc"]),
    ("SFC", ["snes"]),
    ("FC", ["nes", "fds"]),
    ("MD", ["md"]),
    ("PCE", ["pce", "sgx", "pcecd"]),
    ("N64", ["n64"]),
]

BAD_WORDS = re.compile(
    r"\b(beta|demo|proto|prototype|sample|kiosk|hack|bootleg|pirate|unl|aftermarket|"
    r"virtual console|translated|translation|alt|alternate)\b", re.I)
REGIONS = [("usa", re.compile(r"\b(usa|us)\b", re.I)),
           ("world", re.compile(r"\bworld\b", re.I)),
           ("europe", re.compile(r"\b(europe|eur?o)\b", re.I)),
           ("japan", re.compile(r"\b(japan|jpn)\b", re.I))]
# Lo que sobra del nombre tiene que sonar a hack/edición para usar la imagen del juego original
HACK_WORDS = re.compile(r"invincible|edition|version|plus|hack|boss|enhanced|unlimited|infinite|"
                        r"simplified|remix|modified|special|anniversary|evolution|chinese|practice|"
                        r"training|combo|turbo|champion|ultimate|final|magic|hero")
ROMAN = {"II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10"}


def fold(s):
    """Minúsculas, sin acentos y solo letras/dígitos: 'King of Fighters '97' -> 'kingoffighters97'."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


def strip_tags(name):
    return re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", name)


def the_variants(key):
    out = {key}
    if key.endswith("the") and len(key) > 6:
        out.add("the" + key[:-3])
        out.add(key[:-3])
    if key.startswith("the") and len(key) > 6:
        out.add(key[3:])
        out.add(key[3:] + "the")
    return out


def thumb_keys(filename):
    """Claves de búsqueda de un fichero de libretro: título completo y título principal (antes de ' - ')."""
    title = strip_tags(filename[:-4])
    digit = re.sub(r"\b(II|III|IV|VI{0,3}|IX|X)\b", lambda m: ROMAN[m.group(1)], title)
    full = set()
    for t in {title, digit}:
        full |= the_variants(fold(t))
    main = set()
    if " - " in title:
        for t in {title, digit}:
            main |= the_variants(fold(t.split(" - ")[0]))
    return {k for k in full if k}, {k for k in main if k} - full


def word_starts(name):
    """Posiciones de la clave plegada donde empieza una palabra ('SuperHelicopter' -> {0, 5})."""
    starts, pos, prev = set(), 0, " "
    for c in name:
        f = fold(c)
        if f:
            if (not prev.isalnum() or (c.isupper() and prev.islower()) or
                    (c.isdigit() != prev.isdigit())):
                starts.add(pos)
            pos += len(f)
        prev = c
    return starts


def clean_game(en):
    """Devuelve (sistemas, clave, región preferida, inicios de palabra) para un nombre del CSV."""
    name = en.strip()
    systems = None
    for pre, syst in PREFIXES:
        if re.match(pre + r"(?=[A-Z0-9'&!(\s:-])", name):
            systems, name = syst, name[len(pre):]
            break
    region = None
    for reg, rx in REGIONS:
        if rx.search(" ".join(re.findall(r"\([^)]*\)|\[[^\]]*\]", name))):
            region = reg
            break
    if region is None:
        low = name.lower()
        region = ("usa" if re.search(r"(american|us)(version|edition)|usa$", low) else
                  "europe" if re.search(r"european(version|edition)", low) else
                  "japan" if re.search(r"japanese(version|edition)", low) else None)
    name = strip_tags(name)
    name = re.sub(r"[\[(][^\])]*$", " ", name)  # "[v1 ARC" sin cerrar (nombre recortado en el PDF)
    name = re.sub(r"--|\.n64\b", " ", name)
    name = re.sub(r"^\s*\d{4}-", "", name)  # "0149-Cruis'nWorld"
    # Coletillas pegadas al final: rev2, p.d, 3D, USA, EuropeanVersion...
    tail = re.compile(r"(\s*(rev\s?\d+(\.\d+)?|p\.d|3d|usa|(american|us|european|japanese|chinese|world|korean)"
                      r"(version|edition)))\s*$", re.I)
    prev = None
    while prev != name:
        prev, name = name, tail.sub("", name.strip())
    return systems, fold(name), region, word_starts(name)


def fetch_listing(key, refresh, token):
    """Listado de Named_Titles de un sistema (una petición a la API, con caché)."""
    repo = SYSTEMS[key]
    cache_dir = os.path.join(HERE, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, repo + ".json")
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    url = "https://api.github.com/repos/%s/%s/git/trees/master:Named_Titles" % (OWNER, repo)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "pandora-gamelist-fill-images"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            tree = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            reset = e.headers.get("X-RateLimit-Reset")
            when = time.strftime("%H:%M", time.localtime(int(reset))) if reset else "más tarde"
            sys.exit("GitHub ha limitado las peticiones. Vuelve a probar a las %s o usa GITHUB_TOKEN." % when)
        print("  aviso: no se pudo listar %s (%s)" % (repo, e.code), file=sys.stderr)
        return []
    if tree.get("truncated"):
        print("  aviso: el listado de %s viene truncado" % repo, file=sys.stderr)
    # 120000 = enlace simbólico: raw.githubusercontent devuelve texto, no la imagen
    files = [t["path"] for t in tree.get("tree", [])
             if t.get("type") == "blob" and t.get("mode") != "120000" and t["path"].lower().endswith(".png")]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(files, fh, ensure_ascii=False)
    return files


def build_index(refresh, token):
    full, main = {}, {}
    for key in SYSTEMS:
        files = fetch_listing(key, refresh, token)
        print("  %-6s %6d imágenes" % (key, len(files)))
        for f in files:
            fk, mk = thumb_keys(f)
            for k in fk:
                full.setdefault(k, []).append((key, f))
            for k in mk:
                main.setdefault(k, []).append((key, f))
    return full, main


def pick(cands, systems, region):
    order = list(SYSTEMS)
    allowed = [c for c in cands if systems is None or c[0] in systems]
    if not allowed:
        return None

    def score(c):
        # Menor es mejor: sin hacks/betas, región pedida, prioridad del sistema,
        # USA > World > Europe > Japan y, por último, el nombre más corto.
        sysk, f = c
        tags = " ".join(re.findall(r"\(([^)]*)\)", f) + re.findall(r"\[([^\]]*)\]", f))
        bad = len(BAD_WORDS.findall(tags))
        reg = next((i for i, (_, rx) in enumerate(REGIONS) if rx.search(tags)), len(REGIONS))
        wanted = 0 if region and reg < len(REGIONS) and REGIONS[reg][0] == region else 1
        return (bad, wanted, order.index(sysk), reg, len(f))
    return min(allowed, key=score)


def match(en, full, main, approx):
    systems, key, region, starts = clean_game(en)
    if len(key) < 2:
        return None, None
    for k in the_variants(key):
        hit = pick(full.get(k, []), systems, region)
        if hit:
            return hit, "exacta"
    for k in the_variants(key):
        hit = pick(main.get(k, []), systems, region)
        if hit:
            return hit, "exacta"
    if approx:
        # Juego original: el título más largo que sea el comienzo del nombre (hacks, ediciones...)
        for n in range(len(key) - 1, 7, -1):
            if n < len(key) * 0.5:
                break
            # Cortar entre palabras, nunca justo antes de un número de secuela ("...NorthStar|2...")
            if n not in starts or key[n].isdigit() or not HACK_WORDS.search(key[n:]):
                continue
            sub = key[:n]
            hit = pick(full.get(sub, []) + main.get(sub, []), systems, region)
            if hit:
                return hit, "original"
    return None, None


ENTRY = re.compile(r"^\s*(\d+)\s*:\s*(\[.*\])\s*,?\s*$")


def read_images_js(path):
    entries, systems = {}, {}
    if not os.path.exists(path):
        return entries, systems
    text = open(path, encoding="utf-8").read()
    m = re.search(r"systems:\s*(\{.*?\})", text, re.S)
    if m:
        systems = json.loads(m.group(1))
    for line in text.splitlines():
        m = ENTRY.match(line)
        if m:
            entries[int(m.group(1))] = json.loads(m.group(2))
    return entries, systems


def write_images_js(path, entries, systems):
    used = {e[0] for e in entries.values()}
    systems = {k: v for k, v in systems.items() if k in used}
    lines = ["    %d: %s" % (i, json.dumps(entries[i], ensure_ascii=False)) for i in sorted(entries)]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "// Pantallas de título de los juegos. Las imágenes no se alojan aquí:\n"
            "// se cargan desde https://github.com/libretro-thumbnails (carpeta Named_Titles de cada sistema).\n"
            "// games: { id: [sistema, nombre del fichero sin .png, 1 si es la imagen del juego original] }\n"
            "// El 1 marca hacks o variantes sin imagen propia, que muestran la del juego en el que se basan.\n"
            "// Generado en parte con tools/fill_images.py; las entradas existentes se respetan al volver a ejecutarlo.\n"
            "window.GAME_IMAGES = {\n"
            '  base: "%s",\n'
            "  systems: %s,\n"
            "  games: {\n%s\n  }\n};\n" % (BASE, json.dumps(systems, indent=4).replace("\n}", "\n  }"),
                                          ",\n".join(lines)))


def main():
    ap = argparse.ArgumentParser(description="Rellena images.js con pantallas de título de libretro-thumbnails.")
    ap.add_argument("--csv", default=os.path.join(ROOT, "pandora88s_juegos.csv"),
                    help="CSV con las columnas id, es, en (por defecto pandora88s_juegos.csv)")
    ap.add_argument("--output", default=os.path.join(ROOT, "images.js"),
                    help="fichero a rellenar (por defecto images.js)")
    ap.add_argument("--report", default=os.path.join(HERE, "images_report.csv"),
                    help="informe de coincidencias (por defecto tools/images_report.csv)")
    ap.add_argument("--dry-run", action="store_true", help="no modifica images.js, solo escribe el informe")
    ap.add_argument("--exact-only", action="store_true",
                    help="no usar la imagen del juego original cuando no hay coincidencia exacta")
    ap.add_argument("--refresh", action="store_true", help="vuelve a pedir los listados a GitHub")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    print("Leyendo listados de libretro-thumbnails…")
    full, main_idx = build_index(args.refresh, token)

    entries, systems = read_images_js(args.output)
    systems = dict(systems, **SYSTEMS)
    with open(args.csv, encoding="utf-8-sig") as fh:
        games = list(csv.DictReader(fh))

    stats = {"existente": 0, "exacta": 0, "original": 0, "sin imagen": 0}
    report = []
    for g in games:
        gid = int(g["id"])
        if gid in entries:
            e = entries[gid]
            stats["existente"] += 1
            report.append([gid, g["en"], "existente", e[0], e[1]])
            continue
        hit, how = match(g["en"], full, main_idx, not args.exact_only)
        if not hit:
            stats["sin imagen"] += 1
            report.append([gid, g["en"], "sin imagen", "", ""])
            continue
        stats[how] += 1
        sysk, f = hit
        entries[gid] = [sysk, f[:-4]] + ([1] if how == "original" else [])
        report.append([gid, g["en"], how, sysk, f[:-4]])

    with open(args.report, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "en", "coincidencia", "sistema", "imagen"])
        w.writerows(report)
    if not args.dry_run:
        write_images_js(args.output, entries, systems)

    total = len(games)
    print("\nJuegos: %d" % total)
    for k, v in stats.items():
        print("  %-11s %6d  (%.1f%%)" % (k, v, 100.0 * v / total))
    print("Informe: %s" % os.path.relpath(args.report))
    print("images.js %s" % ("sin cambios (--dry-run)" if args.dry_run else "actualizado: " + os.path.relpath(args.output)))


if __name__ == "__main__":
    main()
