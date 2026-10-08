#!/usr/bin/env python3
"""
Agrupa las versiones de cada juego y les asigna una popularidad.

El listado de la Pandora repite mucho cada juego: revisiones (rev1, rev2…), lotes
([v1 ARCADE], [ARCADE v2], p.d), regiones, la misma ROM con y sin prefijo de plataforma
(Aladdin / SFCAladdin) y hacks (TheKingofFighters'97Plus, …InvincibleEdition…).
Este script:

1. Agrupa todas las versiones de un mismo juego y elige una versión principal.
2. Da a cada versión principal una popularidad de 1 a 999:
   - si su nombre encaja con tools/popularity.csv (juegos y sagas conocidos), usa ese valor;
   - si no, la estima (1–599) con datos del propio listado: si es un juego comercial
     conocido (tiene pantalla de título en images.js), en cuántas plataformas está,
     cuántos hacks/versiones tiene y si está entre los destacados del principio del listado.
3. Reescribe pandora88s_juegos.csv (columnas id, es, en, version_de, popularidad)
   y games.js, y deja un resumen por juego en tools/catalog_report.csv.

Uso (desde la carpeta del proyecto):
    python3 tools/build_catalog.py

Para cambiar la popularidad de un juego, edita tools/popularity.csv y vuelve a ejecutarlo.
Solo usa la biblioteca estándar de Python 3.8+.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
from fill_images import clean_game, fold, read_images_js  # noqa: E402

CSV_PATH = os.path.join(ROOT, "pandora88s_juegos.csv")
GAMES_JS = os.path.join(ROOT, "games.js")
IMAGES_JS = os.path.join(ROOT, "images.js")
POPULARITY = os.path.join(HERE, "popularity.csv")
REPORT = os.path.join(HERE, "catalog_report.csv")

FEATURED_MAX_ID = 300   # los primeros juegos del listado son los destacados de la Pandora
ARCADE_MAX_ID = 1700    # hasta aquí, el bloque principal de arcade

# Lo que sobra tras el nombre del juego original tiene que sonar a hack/edición para
# considerarlo una versión (así "StreetFighterIIChampionEdition" cuelga de "StreetFighterII",
# pero "StreetFighterIII" o "DonkeyKongCountry" siguen siendo juegos distintos).
HACK_WORDS = re.compile(
    r"invincible|edition|version|plus|hack|boss|enhanced|unlimited|infinite|simplified|"
    r"remix|modified|special|anniversary|evolution|chinese|practice|training|combo|turbo|"
    r"champion|finalbattle|bootleg|translated|translation|english|traditional|cheat|easy")
PLATFORM_PREFIX = re.compile(r"^(GBA|GBC|GB|SFC|FC|MD|PCE|N64|3D)(?=[A-Z0-9'&!(\s:-])")
LANG_TAG = [
    (0, re.compile(r"usa|\bus\b|american|europe|world|english", re.I)),
    (1, re.compile(r"(?i:japan)|(?<=[a-z0-9])JP?(?![A-Za-z])")),
    (2, re.compile(r"chinese|china|korea|taiwan|hong|(?<=[a-z0-9])(CN|cn|HK|KR)(?![A-Za-z])", re.I)),
]
# Marcas de lote/placa/revisión: la versión principal será la que tenga menos
NOISE = re.compile(r"\[|\(|(?i:rev)\s?\d|p\.d|V\d{3}|\d\s?P\b|\d?Players|set\s?\d|v\d+(\.\d+)?\b|"
                   r"[Vv]ersion\s?\d|--|\.n64|bootleg|hack|arcade$", re.I)

# Coletillas pegadas al final que no cambian de juego: jugadores (3P, 4Players), placa (V115, set2),
# revisión (reva, v1), región abreviada (EU, J, US, UK, cn) o "Arcade".
VERSION_TAIL = re.compile(
    r"((?i:rev)\s?\d+|p\.d|--|\.n64|"
    r"\d\s?P(layers)?|\d?Players\s?Ver\.?|V\d{3}[A-Z]{0,2}|set\s?\d+|reva|v\d+(\.\d+)?|Arcade|"
    r"[Vv]ersion\s?\d+|"
    r"(USA|US|American|European|Japanese|Chinese|World|Korean|Asian|Asia)\s?(Version|Edition|version|edition)|"
    r"(?<=[A-Za-z0-9.!'])(USA|US|EU|UK|JP|CN|cn|HK|KR)|(?<=[a-z0-9.!'])(J|E)|:)\s*$")


def group_key(en):
    """Clave del juego sin revisiones, lotes, regiones ni prefijo de plataforma."""
    name = re.sub(r"\([^)]*\)|\[[^\]]*\]|[\[(][^\])]*$", " ", en).strip()
    name = re.sub(r"^3D(?=[A-Z0-9])", "", name)            # sección "3D…" del listado
    three_d = False
    prev = None
    while prev != name:
        prev = name
        name = VERSION_TAIL.sub("", name).strip()
        if re.search(r"3D$", name):                       # "Tekken5 3D", "Sonic3D", "N64… 3D"
            three_d = True
            name = name[:-2].strip()
    name = re.sub(r"^(.*?),\s*The\b", r"The \1", name)
    _, key, _, starts = clean_game(name)
    if three_d:                     # 3D marca otro juego/plataforma: Bomberman 3D ≠ Bomberman
        key += "3d"
    return key, starts


def lang_rank(en):
    """0 = inglés o sin región, 1 = japonés, 2 = chino/coreano…: la principal será la más universal."""
    for rank, rx in LANG_TAG:
        if rx.search(en):
            return rank
    return 0


def load_popularity():
    rules = []
    if not os.path.exists(POPULARITY):
        return rules
    with open(POPULARITY, encoding="utf-8") as fh:
        for row in csv.DictReader(line for line in fh if not line.startswith("#")):
            pat = (row.get("patron") or "").strip()
            if pat:
                force = (row.get("agrupar") or "").strip().lower() in ("si", "sí", "1", "x")
                rules.append((re.compile(pat), int(row["popularidad"]), row.get("juego", "").strip(),
                              force and ((row.get("principal") or "").strip() or True)))
    return rules


def main():
    ap = argparse.ArgumentParser(description="Agrupa versiones y asigna popularidad.")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo escribe tools/catalog_report.csv; no toca el CSV ni games.js")
    ap.add_argument("--report", default=REPORT, help="ruta del informe")
    args = ap.parse_args()

    with open(CSV_PATH, encoding="utf-8-sig") as fh:
        games = [{"id": int(r["id"]), "es": r["es"], "en": r["en"]} for r in csv.DictReader(fh)]
    images, _ = read_images_js(IMAGES_JS)

    # 1) Mismo nombre limpio = mismo juego
    by_key = defaultdict(list)
    starts_of = {}
    for g in games:
        key, starts = group_key(g["en"])
        g["key"] = key or "id%d" % g["id"]
        by_key[g["key"]].append(g)
        starts_of.setdefault(g["key"], starts)

    # 2) Hacks/ediciones: cuelgan del juego más largo cuyo nombre es el comienzo del suyo
    parent = {}
    for key in sorted(by_key, key=len):
        starts = starts_of[key]
        for n in range(len(key) - 1, 4, -1):
            if n < len(key) * 0.4:
                break
            if n not in starts or key[n].isdigit() or not HACK_WORDS.search(key[n:]):
                continue
            if key[:n] in by_key:
                parent[key] = key[:n]
                break

    hack_count = defaultdict(int)       # hacks reconocidos por sus palabras, antes de otras reglas
    for p in parent.values():
        hack_count[p] += 1

    # "DoubleDragon1" es el mismo juego que "DoubleDragon"
    for key in by_key:
        if key not in parent and re.search(r"[a-z]1$", key) and key[:-1] in by_key:
            parent[key] = key[:-1]

    # Grupos forzados desde tools/popularity.csv (columna agrupar): hacks con otro nombre,
    # como "DinosaurKombat…" (恐龙快打) que son Cadillacs & Dinosaurs.
    rules = load_popularity()
    for rx, _, _, force in rules:
        if not force:
            continue
        keys = [k for k in by_key if rx.search(k)]
        if len(keys) > 1:
            canon = force if force in keys else min(keys, key=lambda k: (len(k), min(g["id"] for g in by_key[k])))
            parent.pop(canon, None)
            for k in keys:
                if k != canon:
                    parent[k] = canon

    # Juegos muy hackeados (3+ hacks reconocidos, como KOF '97 o Street Fighter II): cualquier
    # nombre que los prolongue también es una versión ("TheKingofFighters'97TuSnake"), salvo que
    # tenga su propia pantalla de título en libretro: entonces es otro juego conocido.
    def own_titles(k):
        return {tuple(images[g["id"]]) for g in by_key[k] if g["id"] in images and len(images[g["id"]]) == 2}

    hacked = {k for k, n in hack_count.items() if n >= 3}
    for key in sorted(by_key, key=len):
        if key in parent:
            continue
        starts = starts_of[key]
        for n in range(len(key) - 1, 4, -1):
            base = key[:n]
            if base in hacked and n in starts and not key[n].isdigit():
                if own_titles(key) - own_titles(base):
                    break
                parent[key] = base
                break

    def root(k):
        seen = set()
        while k in parent and k not in seen:
            seen.add(k)
            k = parent[k]
        return k

    families = defaultdict(list)   # clave raíz -> claves del grupo
    for key in by_key:
        families[root(key)].append(key)

    # 3) Versión principal, versiones y popularidad
    max_id = max(g["id"] for g in games)
    report = []
    for rkey, keys in families.items():
        members = [g for k in keys for g in by_key[k]]
        base = by_key[rkey]
        main_game = min(base, key=lambda g: (lang_rank(g["en"]), bool(PLATFORM_PREFIX.match(g["en"])),
                                             len(NOISE.findall(g["en"])), g["id"]))
        main_id = main_game["id"]
        for g in members:
            g["parent"] = 0 if g is main_game else main_id

        name_key = fold(main_game["en"])
        rule = next(((score, label) for rx, score, label, _ in rules
                     if rx.search(rkey) or rx.search(name_key)), None)
        exact_sys = {images[g["id"]][0] for g in members
                     if g["id"] in images and len(images[g["id"]]) == 2}
        prefixes = {(PLATFORM_PREFIX.match(g["en"]) or [None])[0] for g in members}
        first_id = min(g["id"] for g in members)
        if rule:
            pop, source = rule[0], "tabla: " + rule[1]
        else:
            score = 60
            score += 170 if exact_sys else 0                               # juego comercial conocido
            score += 45 * min(3, len(exact_sys | (prefixes - {None})))     # varias plataformas
            score += 35 * min(4, math.log2(len(keys)))                     # hacks / ediciones
            score += 90 if first_id <= FEATURED_MAX_ID else 35 if first_id <= ARCADE_MAX_ID else 0
            score += int(40 * (1 - first_id / max_id))                     # antes en la lista
            if re.search(r"chinese|china", " ".join(g["en"].lower() for g in base)):
                score -= 40                                                # traducciones / piratas
            pop, source = max(1, min(599, int(score))), "estimada"
        main_game["pop"] = pop
        report.append([main_id, main_game["es"], main_game["en"], len(members), pop, source, rkey])

    for g in games:
        g.setdefault("pop", 0)

    # 4) Salida
    if not args.dry_run:
        with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "es", "en", "version_de", "popularidad"])
            for g in games:
                w.writerow([g["id"], g["es"], g["en"], g["parent"] or "", g["pop"] or ""])
        with open(GAMES_JS, "w", encoding="utf-8") as fh:
            fh.write("// Pandora 88S R15 · [id, nombre es, nombre en, id de la versión principal (0 = es la principal),"
                     " popularidad 1-999 (solo principales)]. Generado con tools/build_catalog.py.\n")
            fh.write("window.GAMES=")
            json.dump([[g["id"], g["es"], g["en"], g["parent"], g["pop"]] for g in games], fh,
                      ensure_ascii=False, separators=(",", ":"))
            fh.write(";\n")
    report.sort(key=lambda r: (-r[4], r[0]))
    with open(args.report, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id_principal", "es", "en", "versiones", "popularidad", "origen", "clave"])
        w.writerows(report)

    from_table = sum(1 for r in report if r[5] != "estimada")
    print("Juegos: %d filas -> %d juegos distintos (%d con versiones)" %
          (len(games), len(report), sum(1 for r in report if r[3] > 1)))
    print("Popularidad: %d de la tabla, %d estimadas" % (from_table, len(report) - from_table))
    print("Top 15:")
    for r in report[:15]:
        print("  %4d  %-6d %s" % (r[4], r[0], r[2][:60]))
    print("Informe: %s" % os.path.relpath(args.report))
    if args.dry_run:
        print("--dry-run: pandora88s_juegos.csv y games.js sin cambios")
    else:
        print("Actualizados: pandora88s_juegos.csv y games.js")


if __name__ == "__main__":
    main()
