(function () {
  "use strict";

  var PAGE = 150; // rows rendered per batch
  var KEEP = /[\p{L}\p{N}]/u;
  var MARKS = /\p{M}/gu;

  var $q = document.getElementById("q");
  var $clear = document.getElementById("clear");
  var $status = document.getElementById("status");
  var $results = document.getElementById("results");
  var $sentinel = document.getElementById("sentinel");
  var $empty = document.getElementById("empty");
  var $toast = document.getElementById("toast");
  var $sortBtns = document.querySelectorAll("[data-sort]");

  var fmt = new Intl.NumberFormat("es-ES");

  // Lowercase, strip accents and drop anything that isn't a letter or digit.
  // The source names often have no spaces ("Elreydelosluchadores'97"),
  // so matching on this compact form makes "rey de los" find them.
  function foldChar(ch) {
    var out = ch.normalize("NFD").replace(MARKS, "").toLowerCase();
    var kept = "";
    for (var c of out) if (KEEP.test(c)) kept += c;
    return kept;
  }

  function fold(str) {
    var s = "";
    for (var ch of str) s += foldChar(ch);
    return s;
  }

  // window.GAMES rows are [id, nombre es, nombre en, id de la versión principal (0 = es la principal), popularidad]
  var games = (window.GAMES || []).map(function (g) {
    return { id: g[0], es: g[1], en: g[2], kes: fold(g[1]), ken: fold(g[2]), parent: g[3] || 0, pop: g[4] || 0,
             versions: 0 };
  });
  var byId = new Map(games.map(function (g) { return [g.id, g]; }));
  // Every version points at its main game; main games count their versions.
  games.forEach(function (g) {
    g.main = (g.parent && byId.get(g.parent)) || g;
    if (g.main !== g) g.main.versions++;
  });
  var mains = games.filter(function (g) { return g.main === g; });
  var images = window.GAME_IMAGES || { games: {} };
  var collators = {
    es: new Intl.Collator("es", { sensitivity: "base", numeric: true }),
    en: new Intl.Collator("en", { sensitivity: "base", numeric: true })
  };
  var compare = {
    // Most popular games first; each version right after its main game
    popular: function (a, b) {
      return (b.main.pop - a.main.pop) || (a.main.id - b.main.id) ||
        ((a.main === a ? 0 : 1) - (b.main === b ? 0 : 1)) || (a.id - b.id);
    },
    id: function (a, b) { return a.id - b.id; },
    es: function (a, b) { return collators.es.compare(a.es, b.es) || a.id - b.id; },
    en: function (a, b) { return collators.en.compare(a.en, b.en) || a.id - b.id; }
  };
  var sorted = {}; // built on first use: "popular:main", "id:all"…

  function sortedList(mode, onlyMain) {
    var key = mode + (onlyMain ? ":main" : ":all");
    return sorted[key] || (sorted[key] = (onlyMain ? mains : games).slice().sort(compare[mode]));
  }

  var state = { q: "", sort: "popular", list: [], shown: 0, compact: "", tokens: [], exactId: null };

  // ---------- search ----------
  function search(raw) {
    var q = raw.trim();
    var compact = fold(q);
    var tokens = q.split(/\s+/).map(fold).filter(Boolean);
    state.compact = compact;
    state.tokens = tokens.length > 1 ? tokens : [];
    state.exactId = null;

    // Without a search only the main version of each game is listed
    var base = sortedList(state.sort, !compact);
    if (!compact) return base;

    // A main game that matches brings all its versions (so "cadillacs" also lists its
    // "DinosaurKombat…" hacks); a version that matches on its own is listed by itself.
    var hits = new Set();
    games.forEach(function (g) {
      if (matchTerms(g.kes) !== null || matchTerms(g.ken) !== null) hits.add(g);
    });
    var out = base.filter(function (g) { return hits.has(g) || hits.has(g.main); });

    // A purely numeric query also jumps straight to that ID.
    if (/^\d+$/.test(q)) {
      var hit = byId.get(parseInt(q, 10));
      if (hit) {
        state.exactId = hit.id;
        out = [hit].concat(out.filter(function (g) { return g !== hit; }));
      }
    }
    return out;
  }

  // Which terms of the current query a folded name matches: the whole query
  // as one run, or else every separate word. null = no match.
  function matchTerms(key) {
    if (key.indexOf(state.compact) !== -1) return [state.compact];
    if (state.tokens.length < 2) return null;
    for (var i = 0; i < state.tokens.length; i++) {
      if (key.indexOf(state.tokens[i]) === -1) return null;
    }
    return state.tokens;
  }

  // ---------- highlight ----------
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function highlight(name) {
    if (!state.compact) return escapeHtml(name);

    // Fold char by char, remembering which original char each folded char came from.
    var chars = Array.from(name);
    var key = "";
    var map = [];
    chars.forEach(function (ch, i) {
      var f = foldChar(ch);
      for (var j = 0; j < f.length; j++) { key += f[j]; map.push(i); }
    });

    // Only mark a name that matches by itself, so the other language stays clean.
    var terms = matchTerms(key);
    if (!terms) return escapeHtml(name);
    var hit = new Array(chars.length).fill(false);
    terms.forEach(function (t) {
      var from = 0, at;
      while (t && (at = key.indexOf(t, from)) !== -1) {
        for (var k = at; k < at + t.length; k++) hit[map[k]] = true;
        from = at + t.length;
      }
    });

    var html = "", open = false;
    chars.forEach(function (ch, i) {
      if (hit[i] && !open) { html += "<mark>"; open = true; }
      if (!hit[i] && open) { html += "</mark>"; open = false; }
      html += escapeHtml(ch);
    });
    if (open) html += "</mark>";
    return html;
  }

  // ---------- render ----------
  // Title screen for the games listed in images.js; empty cell for the rest.
  function shotHtml(g) {
    var img = images.games[g.id];
    if (!img) return '<span class="shot"></span>';
    var src = images.base + images.systems[img[0]] + "/master/Named_Titles/" +
      encodeURIComponent(img[1] + ".png");
    var orig = img[2] === 1;
    var title = orig
      ? "Imagen del juego original (" + img[1] + "): este hack no tiene imagen propia"
      : "Pantalla de título · " + img[1];
    return '<span class="shot' + (orig ? " is-orig" : "") + '">' +
      '<img src="' + escapeHtml(src) + '" alt="" title="' + escapeHtml(title) + '" ' +
      'width="96" height="72" loading="lazy" decoding="async" referrerpolicy="no-referrer">' +
      "</span>";
  }

  function renderMore() {
    var end = Math.min(state.shown + PAGE, state.list.length);
    if (end <= state.shown) return;
    var html = "";
    for (var i = state.shown; i < end; i++) {
      var g = state.list[i];
      var tag = g.id === state.exactId ? ' <span class="tag">ID EXACTO</span>' : "";
      if (g.main !== g) {
        tag += ' <span class="tag tag-version" title="Versión de: ' + escapeHtml(g.main.es) +
          '">VERSIÓN DE #' + g.main.id + "</span>";
      } else if (g.versions) {
        tag += ' <span class="tag tag-count" title="Busca su nombre para ver todas las versiones">+' +
          fmt.format(g.versions) + (g.versions === 1 ? " VERSIÓN" : " VERSIONES") + "</span>";
      }
      var hasShot = images.games[g.id] ? " has-shot" : "";
      html +=
        '<li><button type="button" class="row' + hasShot + (g.main !== g ? " is-version" : "") +
        '" data-id="' + g.id + '">' +
        '<span class="id">' + g.id + "</span>" +
        '<span class="name es" lang="es">' + highlight(g.es) + tag + "</span>" +
        '<span class="name en" lang="en">' + highlight(g.en) + "</span>" +
        shotHtml(g) +
        "</button></li>";
    }
    $results.insertAdjacentHTML("beforeend", html);
    state.shown = end;
  }

  function update() {
    state.list = search(state.q);
    state.shown = 0;
    $results.innerHTML = "";
    renderMore();
    fillViewport();

    var n = state.list.length;
    $empty.hidden = n !== 0 || !state.q.trim();
    $clear.hidden = !state.q;

    if (!state.q.trim()) {
      $status.innerHTML = "<b>" + fmt.format(mains.length) + "</b> JUEGOS · <b>" +
        fmt.format(games.length) + "</b> CON SUS VERSIONES";
    } else {
      var groups = new Set(state.list.map(function (g) { return g.main; })).size;
      $status.innerHTML = "<b>" + fmt.format(n) + "</b> " + (n === 1 ? "COINCIDENCIA" : "COINCIDENCIAS") +
        (n ? " · <b>" + fmt.format(groups) + "</b> " + (groups === 1 ? "JUEGO" : "JUEGOS") : "");
    }
  }

  // ---------- URL sync (?q=...) ----------
  function syncUrl() {
    var url = new URL(location.href);
    if (state.q.trim()) url.searchParams.set("q", state.q.trim());
    else url.searchParams.delete("q");
    if (state.sort !== "popular") url.searchParams.set("orden", state.sort);
    else url.searchParams.delete("orden");
    history.replaceState(null, "", url);
  }

  // ---------- copy ID ----------
  var toastTimer;
  function toast(msg) {
    $toast.textContent = msg;
    $toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { $toast.hidden = true; }, 1800);
  }

  function copyId(id) {
    var text = String(id);
    var done = function () { toast("ID " + text + " COPIADO ✓"); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    } else {
      fallbackCopy(text);
      done();
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  // ---------- events ----------
  var debounce;
  $q.addEventListener("input", function () {
    state.q = $q.value;
    clearTimeout(debounce);
    debounce = setTimeout(function () { update(); syncUrl(); window.scrollTo({ top: 0 }); }, 90);
  });

  $q.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && $q.value) { e.preventDefault(); clearSearch(); }
    if (e.key === "Enter") {
      e.preventDefault();
      var first = $results.querySelector(".row");
      if (first) first.focus();
    }
  });

  function clearSearch() {
    $q.value = "";
    state.q = "";
    update();
    syncUrl();
    $q.focus();
  }
  $clear.addEventListener("click", clearSearch);

  // If an image can't be loaded, drop it instead of showing a broken icon.
  $results.addEventListener("error", function (e) {
    if (e.target.tagName !== "IMG") return;
    var row = e.target.closest(".row");
    e.target.parentNode.innerHTML = "";
    if (row) row.classList.remove("has-shot");
  }, true);

  $results.addEventListener("click", function (e) {
    var row = e.target.closest(".row");
    if (row) copyId(row.dataset.id);
  });

  // Arrow keys move between rows like a menu.
  $results.addEventListener("keydown", function (e) {
    var row = e.target.closest(".row");
    if (!row) return;
    var li = row.parentElement;
    var next = null;
    if (e.key === "ArrowDown") next = li.nextElementSibling;
    if (e.key === "ArrowUp") next = li.previousElementSibling;
    if (e.key === "ArrowDown" && !next) { renderMore(); next = li.nextElementSibling; }
    if (e.key === "ArrowUp" && !next) { e.preventDefault(); $q.focus(); return; }
    if (next) { e.preventDefault(); next.firstElementChild.focus(); }
  });

  $sortBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      state.sort = btn.dataset.sort;
      $sortBtns.forEach(function (b) {
        var on = b === btn;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", String(on));
      });
      update();
      syncUrl();
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== $q) {
      e.preventDefault();
      $q.focus();
      $q.select();
    }
  });

  // Infinite scroll: keep rendering while the end of the list is near the viewport
  function fillViewport() {
    while (state.shown < state.list.length &&
           $sentinel.getBoundingClientRect().top < window.innerHeight + 800) {
      renderMore();
    }
  }
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { ticking = false; fillViewport(); });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);

  // ---------- boot ----------
  var params = new URLSearchParams(location.search);
  state.q = params.get("q") || "";
  var orden = params.get("orden") === "az" ? "es" : params.get("orden");
  if (orden && compare[orden]) {
    state.sort = orden;
    $sortBtns.forEach(function (b) {
      var on = b.dataset.sort === orden;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }
  $q.value = state.q;
  update();
  if (!games.length) $status.textContent = "ERROR: NO SE PUDO CARGAR games.js";
})();
