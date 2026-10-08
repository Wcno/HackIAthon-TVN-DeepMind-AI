// Shared behaviour for the G6 visual prototypes. Each world styles the same markup.
(() => {
  const D = window.DEMO;

  const TOPIC_LABELS = {
    economia: "Economía",
    logistica_canal: "Logística/Canal",
    turismo: "Turismo",
    servicios_publicos: "Servicios públicos",
    eventos_naturales: "Eventos naturales",
    regulacion: "Regulación",
    sin_tema: "Sin tema",
  };
  const EVIDENCE = {
    suficiente_para_borrador: { label: "Suficiente para borrador", icon: "full" },
    parcial: { label: "Evidencia parcial", icon: "half" },
    insuficiente: { label: "Evidencia insuficiente", icon: "empty" },
  };
  const REVIEW = {
    nuevo: "Nuevo",
    en_revision: "En revisión",
    requiere_evidencia: "Requiere evidencia",
    aprobado_como_borrador: "Aprobado como borrador",
    descartado: "Descartado",
  };
  const TRANSITIONS = {
    nuevo: ["en_revision", "requiere_evidencia", "descartado"],
    en_revision: ["requiere_evidencia", "aprobado_como_borrador", "descartado"],
    requiere_evidencia: ["en_revision", "descartado"],
    aprobado_como_borrador: ["en_revision", "descartado"],
    descartado: ["en_revision"],
  };
  const ACTION_LABEL = {
    en_revision: "Enviar a revisión",
    requiere_evidencia: "Pedir más evidencia",
    aprobado_como_borrador: "Aprobar como borrador",
    descartado: "Descartar",
  };
  const COMPONENTS = [
    ["R", "Relevancia", 30],
    ["I", "Impacto potencial", 25],
    ["U", "Urgencia", 20],
    ["N", "Novedad", 15],
    ["E", "Evidencia disponible", 10],
  ];
  const CLAIM_TYPES = [
    ["hecho", "Hechos", "Hecho"],
    ["declaracion", "Declaraciones", "Declaración"],
    ["inferencia", "Inferencias", "Inferencia"],
    ["hipotesis", "Hipótesis", "Hipótesis"],
  ];
  const TABS = [
    ["historia", "Historia"],
    ["cobertura", "Cobertura"],
    ["contexto", "Contexto"],
    ["borrador", "Borrador"],
    ["revision", "Revisión"],
  ];
  const COUNTRY = { PAN: "Panamá" };
  const SPOKEN_WORDS_PER_SECOND = 2.5;

  const ICONS = {
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    full: '<circle cx="12" cy="12" r="8"/><path d="m8.5 12.2 2.4 2.4 4.6-5"/>',
    half: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none"/>',
    empty: '<circle cx="12" cy="12" r="8"/><path d="m6.5 17.5 11-11"/>',
    external: '<path d="M14 5h5v5"/><path d="m19 5-8 8"/><path d="M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    copy: '<rect x="8" y="8" width="11" height="11" rx="1.5"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
    back: '<path d="M19 12H5m6-6-6 6 6 6"/>',
    alert: '<path d="M12 4 3 19h18Z"/><path d="M12 10v4m0 2.5v.5"/>',
    lock: '<rect x="6" y="11" width="12" height="9" rx="1.5"/><path d="M9 11V8a3 3 0 0 1 6 0v3"/>',
    chevron: '<path d="m7 10 5 5 5-5"/>',
  };
  const icon = (name, cls = "icon") =>
    `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const panama = (iso, opts) =>
    iso ? new Intl.DateTimeFormat("es-PA", { timeZone: "America/Panama", ...opts }).format(new Date(iso)) : "";
  const shortDate = (iso) => panama(iso, { day: "numeric", month: "short" }).replace(".", "");
  const dateTime = (iso) =>
    panama(iso, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).replace(".", "");
  // Decimal comma to match the figures quoted in the data ("44,36 %").
  const number = (n, digits = 0) => n.toLocaleString("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const words = (s) => (s || "").trim().split(/\s+/).filter(Boolean).length;

  const fichaByCase = Object.fromEntries(D.fichas.map((f) => [f.id_caso, f]));
  const state = {
    groupId: null,
    tab: "historia",
    topic: "todos",
    review: "todos",
    query: null,
    reviews: D.revisiones.slice(),
  };

  const ranked = D.grupos.slice().sort(
    (a, b) =>
      b.puntaje.valor - a.puntaje.valor ||
      b.puntaje.componentes.U - a.puntaje.componentes.U ||
      a.id_grupo.localeCompare(b.id_grupo),
  );
  const rankOf = Object.fromEntries(ranked.map((g, i) => [g.id_grupo, i + 1]));

  const reviewHistory = (caso) =>
    state.reviews
      .map((r, i) => ({ ...r, order: i }))
      .filter((r) => r.id_caso === caso)
      .sort((a, b) => a.fecha.localeCompare(b.fecha) || a.order - b.order);
  const reviewState = (caso) => (caso ? reviewHistory(caso).at(-1)?.estado ?? "nuevo" : null);

  const latestDate = (g) => g.miembros.map((m) => m.recirculada_en || m.fecha_publicacion).sort().at(-1);
  const coverage = (g) => {
    const outlets = new Set(g.miembros.map((m) => m.medio)).size;
    const origins = new Set(g.miembros.map((m) => m.procedencia)).size;
    return { news: g.miembros.length, outlets, origins };
  };
  const plural = (n, one, many) => `${number(n)} ${n === 1 ? one : many}`;
  const coverageLine = (g) => {
    const c = coverage(g);
    return `${plural(c.news, "noticia", "noticias")} · ${plural(c.outlets, "medio", "medios")} · ${plural(c.origins, "origen independiente", "orígenes independientes")}`;
  };
  const needsInvestigation = (g) => g.puntaje.rango === "alto" && g.estado_evidencia === "insuficiente";

  // ---------- small components ----------

  const evidenceBadge = (key) =>
    `<span class="badge evidence evidence--${key}">${icon(EVIDENCE[key].icon)}${EVIDENCE[key].label}</span>`;
  const reviewBadge = (key) =>
    key ? `<span class="badge review review--${key}">${REVIEW[key]}</span>` : `<span class="badge review review--none">Sin ficha</span>`;
  const priorityCode = (rango) => `<span class="priority priority--${rango}">${rango.toUpperCase()}</span>`;

  const scoreBar = (p) =>
    `<span class="scorebar" aria-hidden="true">${COMPONENTS.map(
      ([k, , w]) => `<span class="scorebar__seg scorebar__seg--${k}" style="width:${w * p.componentes[k]}%"></span>`,
    ).join("")}</span>`;

  const scoreButton = (g, size = "") =>
    `<button type="button" class="score ${size}" data-score="${g.id_grupo}" aria-haspopup="dialog" title="Ver cómo se calcula">
      <span class="score__value">${number(g.puntaje.valor)}</span>
      <span class="score__range">${g.puntaje.rango}</span>
      ${scoreBar(g.puntaje)}
    </button>`;

  // ---------- inbox ----------

  const filtered = () =>
    ranked.filter(
      (g) =>
        (state.topic === "todos" || g.tema === state.topic) &&
        (state.review === "todos" || reviewState(g.id_caso) === state.review),
    );

  function renderInbox() {
    const lead = ranked[0];
    const unfiltered = state.topic === "todos" && state.review === "todos";
    // The lead already shows the top topic; repeat it in the list only when filtering.
    const list = filtered().filter((g) => !(unfiltered && g === lead));
    const topics = [...new Set(ranked.map((g) => g.tema))];
    const q = D.calidad;
    const el = document.getElementById("inbox");
    const band = document.getElementById("lead-band");
    const leadHtml = `<article class="lead ${state.groupId === lead.id_grupo ? "is-selected" : ""}" data-open="${lead.id_grupo}">
        <span class="lead__rank" aria-label="Puesto 1">1</span>
        <div class="lead__body">
          <h2 class="lead__title">${esc(lead.titulo)}</h2>
          <p class="meta">
            ${priorityCode(lead.puntaje.rango)}
            <span class="topic topic--${lead.tema}">${TOPIC_LABELS[lead.tema]}</span>
            <span class="dateline">Panamá, ${shortDate(latestDate(lead))}</span>
          </p>
          <p class="lead__why">${esc(lead.puntaje.justificaciones.R)} ${esc(lead.puntaje.justificaciones.E)}</p>
          <div class="lead__facts">
            ${scoreButton(lead, "score--large")}
            <div class="lead__badges">${evidenceBadge(lead.estado_evidencia)}${reviewBadge(reviewState(lead.id_caso))}</div>
          </div>
          <button type="button" class="btn btn--primary" data-open="${lead.id_grupo}">Abrir caso</button>
        </div>
      </article>`;
    const snapshot = `<p class="snapshot">
        <span>${number(q.leidos)} noticias leídas · ${number(q.incluidas)} en la ventana de 30 días · ${number(q.excluidas)} excluidas</span>
        <a href="#calidad" class="link">Ver calidad de datos</a>
      </p>`;
    if (band) band.innerHTML = snapshot + leadHtml;
    el.innerHTML = `${band ? "" : snapshot + leadHtml}

      <div class="filters" role="group" aria-label="Filtrar temas">
        <label class="select">
          <span class="select__label">Tema</span>
          <select id="topic-filter">
            <option value="todos">Todos los temas</option>
            ${topics.map((t) => `<option value="${t}" ${state.topic === t ? "selected" : ""}>${TOPIC_LABELS[t]}</option>`).join("")}
          </select>
          ${icon("chevron", "icon select__chevron")}
        </label>
        <label class="select">
          <span class="select__label">Estado</span>
          <select id="review-filter">
            <option value="todos">Todos los estados</option>
            ${Object.entries(REVIEW)
              .map(([k, v]) => `<option value="${k}" ${state.review === k ? "selected" : ""}>${v}</option>`)
              .join("")}
          </select>
          ${icon("chevron", "icon select__chevron")}
        </label>
        <span class="count">${unfiltered ? `${plural(list.length, "tema más", "temas más")}` : plural(list.length, "tema", "temas")}</span>
      </div>

      ${
        list.length
          ? `<ol class="rows">${list.map(row).join("")}</ol>`
          : `<div class="empty"><p>No hay temas con estos filtros.</p><button type="button" class="btn" data-clear>Quitar filtros</button></div>`
      }`;
  }

  function row(g) {
    const selected = state.groupId === g.id_grupo;
    return `<li class="row ${selected ? "is-selected" : ""}">
      <button type="button" class="row__hit" data-open="${g.id_grupo}" aria-current="${selected}">
        <span class="row__rank">${rankOf[g.id_grupo]}</span>
        <span class="row__main">
          <span class="row__title">${esc(g.titulo)}</span>
          <span class="meta">
            <span class="topic topic--${g.tema}">${TOPIC_LABELS[g.tema]}</span>
            <span class="dateline">${shortDate(latestDate(g))}</span>
            <span class="row__coverage">${plural(coverage(g).origins, "origen", "orígenes")}</span>
          </span>
          <span class="row__badges">
            ${evidenceBadge(g.estado_evidencia)}${reviewBadge(reviewState(g.id_caso))}
            ${needsInvestigation(g) ? `<span class="flag">${icon("alert")}Requiere investigación</span>` : ""}
          </span>
        </span>
        <span class="row__score">
          <span class="score__value">${number(g.puntaje.valor)}</span>
          <span class="score__range">${g.puntaje.rango}</span>
        </span>
      </button>
    </li>`;
  }

  // ---------- case ----------

  function citeIndex(ids) {
    const map = new Map();
    ids.forEach((id) => map.has(id) || map.set(id, map.size + 1));
    return map;
  }
  const chip = (index, c) =>
    `<button type="button" class="cite" data-ev="${c.id_evidencia}" data-passage="${esc(c.pasaje)}" data-field="${c.campo}" aria-label="Ver fuente ${index.get(c.id_evidencia)}">${index.get(c.id_evidencia)}</button>`;

  function renderCase() {
    const el = document.getElementById("case");
    if (state.query) return renderQuery(el);
    const g = D.grupos.find((x) => x.id_grupo === state.groupId);
    const f = g.id_caso && fichaByCase[g.id_caso];
    const ids = f ? f.afirmaciones.flatMap((a) => a.citas.map((c) => c.id_evidencia)) : [];
    g.contexto.forEach((c) => ids.push(c.id_evidencia));
    g.miembros.forEach((m) => ids.push(m.id_noticia));
    const index = citeIndex(ids);

    el.innerHTML = `
      <button type="button" class="back" data-back>${icon("back")}Volver a temas</button>
      <header class="case__head">
        <h1 class="case__title">${esc(g.titulo)}</h1>
        <p class="meta">
          ${priorityCode(g.puntaje.rango)}
          <span class="topic topic--${g.tema}">${TOPIC_LABELS[g.tema]}</span>
          <span class="dateline">Panamá, ${shortDate(latestDate(g))}</span>
          <span class="rules">Reglas ${g.puntaje.version_reglas}</span>
        </p>
        <div class="case__facts">
          ${scoreButton(g, "score--large")}
          <div class="case__badges">${evidenceBadge(g.estado_evidencia)}${reviewBadge(reviewState(g.id_caso))}</div>
        </div>
      </header>
      <nav class="tabs" role="tablist" aria-label="Secciones del caso">
        ${TABS.map(
          ([k, label]) =>
            `<button type="button" role="tab" class="tab" data-tab="${k}" aria-selected="${state.tab === k}">${label}</button>`,
        ).join("")}
      </nav>
      <div class="panel" role="tabpanel">${PANELS[state.tab](g, f, index)}</div>
      ${f ? sources(index) : ""}`;
    el.classList.remove("is-entering");
    void el.offsetWidth;
    el.classList.add("is-entering");
  }

  function sources(index) {
    return `<section class="sources">
      <h2 class="h2">Fuentes del caso</h2>
      <ol class="sources__list">
        ${[...index.entries()]
          .map(([id, n]) => {
            const e = D.evidencias[id];
            if (!e) return "";
            return `<li><button type="button" class="source-line" data-ev="${id}">
              <span class="source-line__n">${n}</span>
              <span class="source-line__t">${esc(e.titulo)}</span>
              <span class="source-line__d">${e.tipo === "noticia" ? shortDate(e.fecha) : esc(e.campos.periodo || "")}</span>
            </button></li>`;
          })
          .join("")}
      </ol>
    </section>`;
  }

  const noFicha = () =>
    `<div class="empty"><p>Este tema aún no tiene ficha de evidencia.</p><p class="muted">Su cobertura y contexto oficial están disponibles en las otras pestañas.</p></div>`;

  const PANELS = {
    historia(g, f, index) {
      if (!f) return noFicha();
      const scope =
        f.alcance_texto === "titular_metadatos"
          ? `<p class="notice">${icon("alert")}Basado únicamente en titular/metadatos.</p>`
          : "";
      const groups = CLAIM_TYPES.map(([type, title]) => {
        const claims = f.afirmaciones.filter((a) => a.tipo === type);
        if (!claims.length) return "";
        return `<section class="claims claims--${type}">
          <h2 class="h2">${title}</h2>
          <ul>${claims
            .map(
              (a) => `<li class="claim">
                <p>${esc(a.texto)} <span class="cites">${a.citas.map((c) => chip(index, c)).join("")}</span></p>
                ${a.atribuida_a ? `<p class="claim__by">Según ${esc(a.atribuida_a)}</p>` : ""}
              </li>`,
            )
            .join("")}</ul>
        </section>`;
      }).join("");
      const contradictions = f.contradicciones
        .map(
          (c) => `<section class="contradiction">
            <h2 class="h2">Contradicción</h2>
            <p>${esc(c.descripcion)}</p>
            <div class="versions">
              ${c.versiones
                .map(
                  (v) => `<div class="version">
                    <p class="version__value">${esc(v.valor)}</p>
                    <p class="version__scope">${esc(v.alcance)}</p>
                    ${chip(index, { id_evidencia: v.id_evidencia, campo: "titulo", pasaje: v.valor })}
                  </div>`,
                )
                .join("")}
            </div>
            <p class="muted">Verificación pendiente: el sistema no elige una versión.</p>
          </section>`,
        )
        .join("");
      return `${scope}${groups}${contradictions}
        <section class="gaps">
          <h2 class="h2">Qué falta comprobar</h2>
          <ul>${f.vacios.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>
        </section>
        <section class="action">
          <h2 class="h2">Acción recomendada</h2>
          <p>${esc(f.accion_recomendada)}</p>
        </section>`;
    },

    cobertura(g, f, index) {
      const c = coverage(g);
      const byOrigin = {};
      g.miembros.forEach((m) => (byOrigin[m.procedencia] ||= []).push(m));
      const replicated = Object.entries(byOrigin).filter(([, ms]) => ms.length > 1);
      const note = replicated.length
        ? replicated
            .map(([o, ms]) => `${plural(ms.length, "medio publica", "medios publican")} la misma nota de ${esc(o)}: cuentan como un solo origen.`)
            .join(" ")
        : "Cada noticia tiene un origen distinto.";
      return `<div class="tally">
          <p><strong>${number(c.news)}</strong> ${c.news === 1 ? "noticia" : "noticias"}</p>
          <p><strong>${number(c.outlets)}</strong> ${c.outlets === 1 ? "medio" : "medios"}</p>
          <p><strong>${number(c.origins)}</strong> ${c.origins === 1 ? "origen independiente" : "orígenes independientes"}</p>
        </div>
        <p class="lede">${note}</p>
        ${Object.entries(byOrigin)
          .map(
            ([origin, ms]) => `<section class="origin">
              <h2 class="h2">Origen: ${esc(origin)}</h2>
              <ul>${ms
                .map(
                  (m) => `<li class="member">
                    <button type="button" class="member__hit" data-ev="${m.id_noticia}">
                      <span class="member__title">${esc(m.titulo)}</span>
                      <span class="meta">
                        <span>${esc(m.medio)}</span>
                        <span class="dateline">${dateTime(m.fecha_publicacion)}</span>
                        ${m.alcance_texto === "titular_metadatos" ? `<span class="tag">Solo titular</span>` : ""}
                      </span>
                      ${
                        m.recirculada_en
                          ? `<span class="recirculated">${icon("alert")}Publicada originalmente el ${dateTime(m.fecha_publicacion)}; recirculada el ${dateTime(m.recirculada_en)}. No es un evento nuevo.</span>`
                          : ""
                      }
                    </button>
                  </li>`,
                )
                .join("")}</ul>
            </section>`,
          )
          .join("")}`;
    },

    contexto(g, f, index) {
      if (!g.contexto.length)
        return `<div class="empty"><p>Sin contexto oficial vinculado.</p><p class="muted">${esc(g.sin_contexto_motivo)}</p></div>`;
      return g.contexto
        .map((link) => {
          const e = D.evidencias[link.id_evidencia];
          const k = e.campos;
          const country = COUNTRY[link.pais] || link.pais;
          const wb = link.id_evidencia.match(/^WB-([A-Z]{3})-(.+)-(\d{4})$/);
          const series = wb && D.series[wb[2]];
          return `<section class="context">
            <h2 class="h2">${esc(link.etiqueta)}</h2>
            <p class="lede">${esc(link.razon)}</p>
            <dl class="facts">
              <div><dt>País</dt><dd>${esc(country)}</dd></div>
              <div><dt>Período</dt><dd>${esc(k.periodo || shortDate(e.fecha))}</dd></div>
              <div><dt>Unidad</dt><dd>${esc(k.unidad || "n/d")}</dd></div>
              <div><dt>Valor</dt><dd>${k.valor ? esc(k.valor) : "Sin dato"} ${chip(index, { id_evidencia: link.id_evidencia, campo: "valor", pasaje: k.valor })}</dd></div>
            </dl>
            ${series ? chart(series, Number(wb[3]), k.unidad) : ""}
            <p class="notice">${icon("alert")}${esc(link.limitaciones)}</p>
          </section>`;
        })
        .join("");
    },

    borrador(g, f, index) {
      if (!f) return noFicha();
      const b = f.borrador;
      if (!b)
        return `<div class="empty"><p>No hay evidencia suficiente para redactar.</p>
          <ul class="muted">${f.vacios.map((v) => `<li>${esc(v)}</li>`).join("")}</ul></div>`;
      const briefWords = words(b.brief);
      const copyWords = words(b.copy_digital);
      const seconds = Math.round(words(b.guion) / SPOKEN_WORDS_PER_SECOND);
      return `${b.leyenda ? `<p class="notice">${icon("alert")}${esc(b.leyenda)}</p>` : ""}
        <section class="block">
          <div class="block__head"><h2 class="h2">Título propuesto</h2>${copyBtn(b.titulo)}</div>
          <p class="block__title">${esc(b.titulo)}</p>
        </section>
        <section class="block">
          <div class="block__head"><h2 class="h2">Brief</h2>${budget(briefWords, 250, "palabras")}${copyBtn(b.brief)}</div>
          ${annotated(b.brief, f, index)}
        </section>
        <section class="block">
          <h2 class="h2">Enfoque de interés público</h2>
          <p>${esc(b.enfoque_interes_publico)}</p>
        </section>
        <section class="block">
          <h2 class="h2">Preguntas de investigación</h2>
          <ol class="questions">${b.preguntas.map((p) => `<li>${esc(p)}</li>`).join("")}</ol>
        </section>
        <section class="block">
          <h2 class="h2">Fuentes y verificaciones pendientes</h2>
          <ul>${b.fuentes_y_verificaciones.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
        </section>
        <section class="block">
          <div class="block__head"><h2 class="h2">Guion</h2>${budget(seconds, 60, "s", 45)}${copyBtn(b.guion)}</div>
          ${annotated(b.guion, f, index)}
        </section>
        <section class="block">
          <div class="block__head"><h2 class="h2">Copy digital</h2>${budget(copyWords, 80, "palabras")}${copyBtn(b.copy_digital)}</div>
          ${annotated(b.copy_digital, f, index)}
        </section>`;
    },

    revision(g, f) {
      if (!f) return noFicha();
      const current = reviewState(g.id_caso);
      const history = reviewHistory(g.id_caso).slice().reverse();
      const blockApproval =
        g.estado_evidencia === "insuficiente"
          ? "Evidencia insuficiente: no se puede aprobar."
          : !f.borrador
            ? "No hay borrador: no se puede aprobar."
            : null;
      const actions = TRANSITIONS[current];
      return `<section class="current">
          <p class="current__label">Estado actual</p>
          <p class="current__state">${REVIEW[current]}</p>
          ${history[0] ? `<p class="muted">${esc(history[0].responsable)} · ${dateTime(history[0].fecha)}</p>` : `<p class="muted">Sin decisiones todavía.</p>`}
        </section>
        <form class="decide" data-decide="${g.id_caso}">
          <label class="field"><span>Responsable</span><input name="actor" required autocomplete="name" placeholder="Nombre de quien decide"></label>
          <label class="field"><span>Nota <em>(opcional)</em></span><textarea name="note" rows="2" placeholder="Motivo de la decisión"></textarea></label>
          <div class="decide__actions">
            ${actions
              .map((s) => {
                const blocked = s === "aprobado_como_borrador" && blockApproval;
                const primary = s === "aprobado_como_borrador" || (s === "en_revision" && current === "nuevo");
                return `<div class="decide__action">
                  <button type="submit" class="btn ${primary ? "btn--primary" : ""}" name="state" value="${s}" ${blocked ? "disabled" : ""}>${blocked ? icon("lock") : ""}${ACTION_LABEL[s]}</button>
                  ${s === "aprobado_como_borrador" ? `<p class="hint">${blocked ? esc(blocked) : "Aprobar no publica el contenido."}</p>` : ""}
                </div>`;
              })
              .join("")}
          </div>
          <p class="form-error" hidden>Escribe el nombre del responsable para registrar la decisión.</p>
        </form>
        <section class="history">
          <h2 class="h2">Historial</h2>
          ${
            history.length
              ? `<ol>${history
                  .map(
                    (r) => `<li><span class="history__state">${REVIEW[r.estado]}</span>
                      <span class="muted">${esc(r.responsable)} · ${dateTime(r.fecha)}</span>
                      ${r.nota ? `<span class="history__note">${esc(r.nota)}</span>` : ""}</li>`,
                  )
                  .join("")}</ol>`
              : `<p class="muted">Este caso todavía no tiene decisiones.</p>`
          }
        </section>`;
    },
  };

  const copyBtn = (text) =>
    `<button type="button" class="btn btn--quiet btn--small" data-copy="${esc(text)}">${icon("copy")}Copiar</button>`;
  function budget(value, max, unit, min) {
    const over = value > max;
    const under = min && value < min;
    const range = min ? `${min}-${max}` : number(max);
    return `<span class="budget ${over ? "is-over" : under ? "is-under" : ""}">
      <span class="budget__track"><span class="budget__fill" style="width:${Math.min(100, (value / max) * 100)}%"></span></span>
      <span class="budget__text">${number(value)} / ${range} ${unit}</span>
    </span>`;
  }

  // The contract has no per-sentence citations yet; the prototype matches each sentence to its closest claim.
  function annotated(text, f, index) {
    const tokens = (s) => new Set(s.toLowerCase().match(/[\p{L}\d]{4,}/gu) || []);
    const sentences = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) || [text];
    return `<div class="annotated">${sentences
      .map((s) => {
        const st = tokens(s);
        let best = null;
        let bestScore = 0;
        f.afirmaciones.forEach((a) => {
          const at = tokens(a.texto);
          const overlap = [...st].filter((t) => at.has(t)).length / Math.max(1, Math.min(st.size, at.size));
          if (overlap > bestScore) [best, bestScore] = [a, overlap];
        });
        const claim = bestScore >= 0.4 ? best : null;
        const type = claim ? CLAIM_TYPES.find(([t]) => t === claim.tipo) : null;
        return `<p class="sentence ${claim ? `sentence--${claim.tipo}` : "sentence--unsourced"}">
          <span class="sentence__type">${type ? type[2] : "Sin cita"}</span>
          <span class="sentence__text">${esc(s.trim())} ${claim ? `<span class="cites">${claim.citas.map((c) => chip(index, c)).join("")}</span>` : ""}</span>
        </p>`;
      })
      .join("")}</div>`;
  }

  function chart(series, year, unit) {
    const pts = series.filter(([, v]) => v !== null);
    const w = 560, h = 180, padL = 40, padR = 16, padT = 18, padB = 28;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const lo = Math.floor(Math.min(...ys) / 10) * 10, hi = Math.ceil(Math.max(...ys) / 10) * 10;
    const X = (x) => padL + ((x - x0) / (x1 - x0)) * (w - padL - padR);
    const Y = (y) => padT + (1 - (y - lo) / (hi - lo)) * (h - padT - padB);
    const ticks = [lo, (lo + hi) / 2, hi];
    const sel = pts.find((p) => p[0] === year);
    const path = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join("");
    return `<figure class="chart">
      <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Serie anual ${x0}-${x1}, ${esc(unit)}">
        ${ticks.map((t) => `<line class="chart__grid" x1="${padL}" x2="${w - padR}" y1="${Y(t)}" y2="${Y(t)}"/><text class="chart__tick" x="${padL - 8}" y="${Y(t) + 4}" text-anchor="end">${number(t)}</text>`).join("")}
        <path class="chart__line" d="${path}"/>
        ${sel ? `<line class="chart__mark" x1="${X(sel[0])}" x2="${X(sel[0])}" y1="${padT}" y2="${h - padB}"/><circle class="chart__dot" cx="${X(sel[0])}" cy="${Y(sel[1])}" r="5"/>
        <text class="chart__label" x="${X(sel[0]) - 8}" y="${Y(sel[1]) - 10}" text-anchor="end">${sel[0]}: ${number(sel[1], 2)}</text>` : ""}
        <text class="chart__tick" x="${X(x0)}" y="${h - 8}" text-anchor="start">${x0}</text>
        <text class="chart__tick" x="${X(x1)}" y="${h - 8}" text-anchor="end">${x1}</text>
      </svg>
      <figcaption>Dato anual ${year} · ${esc(unit)} · Banco Mundial. No es una medición actual.</figcaption>
    </figure>`;
  }

  // ---------- query box ----------

  function renderQuery(el) {
    const q = state.query;
    const back = `<button type="button" class="back back--always" data-close-query>${icon("back")}Volver al caso</button>`;
    if (q.offline) {
      el.innerHTML = `${back}<header class="case__head"><h1 class="case__title">“${esc(q.text)}”</h1></header>
        <div class="answer answer--offline">
          <p class="answer__state">Sin conexión: solo están disponibles las consultas precalculadas.</p>
          <ul class="suggest-list">${D.consultas.map((c) => `<li><button type="button" class="link" data-query="${c.id_consulta}">${esc(c.consulta)}</button></li>`).join("")}</ul>
        </div>`;
      return;
    }
    const index = citeIndex([...q.citas.map((c) => c.id_evidencia), ...q.versiones.map((v) => v.id_evidencia)]);
    let body = "";
    if (q.estado === "respondida")
      body = `<div class="answer"><p class="answer__state">Respuesta con evidencia</p>
        <p class="answer__text">${esc(q.respuesta)} <span class="cites">${q.citas.map((c) => chip(index, c)).join("")}</span></p></div>`;
    if (q.estado === "abstencion")
      body = `<div class="answer answer--abstain"><p class="answer__state">No hay evidencia suficiente para responder</p>
        <p>${esc(q.motivo_abstencion)}</p><h2 class="h2">Qué se necesitaría</h2><p>${esc(q.faltante)}</p></div>`;
    if (q.estado === "contradiccion")
      body = `<div class="answer answer--contradiction"><p class="answer__state">Las fuentes no coinciden</p>
        <div class="versions">${q.versiones
          .map((v) => `<div class="version"><p class="version__value">${esc(v.valor)}</p><p class="version__scope">${esc(v.alcance)}</p>${chip(index, { id_evidencia: v.id_evidencia, campo: "titulo", pasaje: v.valor })}</div>`)
          .join("")}</div><p class="muted">Verificación pendiente: el sistema no elige una versión.</p></div>`;
    el.innerHTML = `${back}<header class="case__head"><h1 class="case__title">${esc(q.consulta)}</h1></header>${body}${index.size ? sources(index) : ""}`;
  }

  // ---------- source drawer ----------

  function openDrawer(id, passage, field) {
    const e = D.evidencias[id];
    const drawer = document.getElementById("drawer");
    const member = D.grupos.flatMap((g) => g.miembros).find((m) => m.id_noticia === id);
    const mark = (text, f) =>
      passage && (!field || field === f) && text.includes(passage)
        ? esc(text).replace(esc(passage), `<mark>${esc(passage)}</mark>`)
        : esc(text);
    const kind = { noticia: "Noticia", indicador: "Indicador oficial", sismo: "Evento USGS" }[e.tipo] || "Fuente";
    let body;
    if (e.tipo === "noticia") {
      body = `<dl class="facts">
          <div><dt>Medio</dt><dd>${esc(member?.medio || "")}</dd></div>
          <div><dt>Origen</dt><dd>${esc(member?.procedencia || "")}</dd></div>
          <div><dt>Publicada</dt><dd>${dateTime(e.fecha)}</dd></div>
        </dl>
        ${Object.entries(e.campos)
          .map(([f, t]) => `<div class="passage"><p class="passage__field">${f === "titulo" ? "Titular" : "Descripción"}</p><p>${mark(t, f)}</p></div>`)
          .join("")}`;
    } else {
      const k = e.campos;
      const country = COUNTRY[(id.match(/^WB-([A-Z]{3})/) || [])[1]] || "Panamá";
      body = `<dl class="facts">
          <div><dt>País</dt><dd>${esc(country)}</dd></div>
          ${Object.entries(k)
            .map(([f, v]) => `<div><dt>${esc(f[0].toUpperCase() + f.slice(1))}</dt><dd>${v ? mark(String(v), f) : "Sin dato"}</dd></div>`)
            .join("")}
        </dl>`;
    }
    drawer.innerHTML = `<div class="drawer__head">
        <p class="drawer__kind">${kind}</p>
        <button type="button" class="icon-btn" data-close-drawer aria-label="Cerrar fuente">${icon("close")}</button>
      </div>
      <h2 class="drawer__title">${esc(e.titulo)}</h2>
      ${body}
      <a class="link link--external" href="${esc(e.url)}" target="_blank" rel="noopener">Abrir fuente original${icon("external")}</a>
      ${D.grupos.some((g) => g.sintetico) && e.tipo === "noticia" ? `<p class="muted">Noticia sintética de demostración: el enlace no lleva a un sitio real.</p>` : ""}`;
    drawer.hidden = false;
    requestAnimationFrame(() => drawer.classList.add("is-open"));
    drawer.querySelector("[data-close-drawer]").focus();
  }
  function closeDrawer() {
    const drawer = document.getElementById("drawer");
    drawer.classList.remove("is-open");
    setTimeout(() => (drawer.hidden = true), 200);
  }

  // ---------- score popover ----------

  function openScore(button) {
    const g = D.grupos.find((x) => x.id_grupo === button.dataset.score);
    const pop = document.getElementById("popover");
    const p = g.puntaje;
    pop.innerHTML = `<div class="pop__head"><p class="pop__title">Puntaje de atención: ${number(p.valor)} · ${p.rango}</p>
        <button type="button" class="icon-btn" data-close-pop aria-label="Cerrar">${icon("close")}</button></div>
      <p class="pop__formula">P = 30R + 25I + 20U + 15N + 10E · Reglas ${p.version_reglas}</p>
      <table class="pop__table"><tbody>${COMPONENTS.map(
        ([k, name, w]) => `<tr>
          <th scope="row"><span class="pop__key pop__key--${k}">${k}</span>${name}</th>
          <td class="pop__pts">${number(w * p.componentes[k], 1)} <span class="muted">/ ${w}</span></td>
          <td class="pop__why">${esc(p.justificaciones[k])}</td></tr>`,
      ).join("")}</tbody></table>
      <p class="muted">Ordena la atención; no mide si una noticia es verdadera.</p>`;
    pop.hidden = false;
    const r = button.getBoundingClientRect();
    const width = Math.min(440, window.innerWidth - 32);
    pop.style.width = `${width}px`;
    pop.style.left = `${Math.max(16, Math.min(r.left, window.innerWidth - width - 16))}px`;
    const below = r.bottom + 8;
    pop.style.top = `${below + pop.offsetHeight > window.innerHeight ? Math.max(16, r.top - pop.offsetHeight - 8) : below}px`;
    pop.querySelector("[data-close-pop]").focus();
  }
  const closeScore = () => (document.getElementById("popover").hidden = true);

  // ---------- search ----------

  function setupSearch() {
    const input = document.getElementById("search");
    const list = document.getElementById("suggestions");
    const show = () => {
      const t = input.value.trim().toLowerCase();
      const matches = D.consultas.filter((c) => !t || c.consulta.toLowerCase().includes(t));
      list.innerHTML = matches.length
        ? `<p class="suggest__head">Consultas disponibles sin conexión</p>${matches
            .map((c) => `<button type="button" class="suggest" data-query="${c.id_consulta}">${icon("search")}${esc(c.consulta)}</button>`)
            .join("")}`
        : `<p class="suggest__head">Pulsa Enter para buscar «${esc(input.value)}»</p>`;
      list.hidden = false;
    };
    input.addEventListener("focus", show);
    input.addEventListener("input", show);
    input.closest("form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const t = input.value.trim();
      if (!t) return;
      const hit = D.consultas.find((c) => c.consulta.toLowerCase() === t.toLowerCase());
      runQuery(hit ? hit : { offline: true, text: t });
    });
    document.addEventListener("click", (ev) => {
      if (!ev.target.closest(".search")) list.hidden = true;
    });
  }
  function runQuery(q) {
    state.query = q;
    document.getElementById("suggestions").hidden = true;
    document.body.classList.add("show-case");
    renderCase();
    document.getElementById("case").scrollTop = 0;
  }

  // ---------- routing and events ----------

  function select(groupId, tab = state.tab) {
    state.groupId = groupId;
    state.tab = tab;
    state.query = null;
    history.replaceState(null, "", `#${groupId}/${tab}`);
    renderInbox();
    renderCase();
  }

  document.addEventListener("click", (ev) => {
    const t = ev.target.closest(
      "[data-open],[data-tab],[data-topic],[data-clear],[data-ev],[data-score],[data-close-drawer],[data-close-pop],[data-copy],[data-back],[data-query],[data-close-query]",
    );
    if (!t) {
      if (!ev.target.closest("#popover")) closeScore();
      if (!ev.target.closest("#drawer") && !document.getElementById("drawer").hidden) closeDrawer();
      return;
    }
    const d = t.dataset;
    if (d.score) return openScore(t);
    if (d.open) {
      document.body.classList.add("show-case");
      select(d.open, "historia");
      document.getElementById("case").scrollTop = 0;
    }
    if (d.tab) select(state.groupId, d.tab);
    if (d.topic) (state.topic = d.topic), renderInbox();
    if (d.clear !== undefined) (state.topic = "todos"), (state.review = "todos"), renderInbox();
    if (d.ev) openDrawer(d.ev, d.passage, d.field);
    if (d.closeDrawer !== undefined) closeDrawer();
    if (d.closePop !== undefined) closeScore();
    if (d.back !== undefined) document.body.classList.remove("show-case");
    if (d.query) runQuery(D.consultas.find((c) => c.id_consulta === d.query));
    if (d.closeQuery !== undefined) (state.query = null), renderCase();
    if (d.copy) {
      navigator.clipboard?.writeText(d.copy);
      const old = t.innerHTML;
      t.textContent = "Copiado";
      setTimeout(() => (t.innerHTML = old), 1400);
    }
  });

  document.addEventListener("change", (ev) => {
    if (ev.target.id === "review-filter") (state.review = ev.target.value), renderInbox();
    if (ev.target.id === "topic-filter") (state.topic = ev.target.value), renderInbox();
  });

  document.addEventListener("submit", (ev) => {
    const form = ev.target.closest("[data-decide]");
    if (!form) return;
    ev.preventDefault();
    const actor = form.actor.value.trim();
    if (!actor) {
      form.querySelector(".form-error").hidden = false;
      form.actor.focus();
      return;
    }
    state.reviews.push({
      id_caso: form.dataset.decide,
      estado: ev.submitter.value,
      responsable: actor,
      fecha: new Date().toISOString(),
      nota: form.note.value.trim() || null,
    });
    renderInbox();
    renderCase();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeScore(), document.getElementById("drawer").hidden || closeDrawer();
  });

  document.getElementById("corte").textContent = `Corte: ${dateTime(D.calidad.corte)}`;
  const [hashGroup, hashTab] = location.hash.slice(1).split("/");
  setupSearch();
  select(
    D.grupos.some((g) => g.id_grupo === hashGroup) ? hashGroup : ranked[0].id_grupo,
    TABS.some(([k]) => k === hashTab) ? hashTab : "historia",
  );
})();
