// Co-News: the editable Borrador and its co-writing assistant, shared by the G6 layout prototypes.
// Grown from the page-local scripts of the first Paquete gráfico prototype (source column + draft editor), UI only:
// no model is connected, so rewrites are labelled examples and saving stays in this screen.

// Page-local until app.js supports an in-layout source panel (see report).
// app.js still fills #drawer; this keeps it in the layout instead of floating.
(() => {
  const drawer = document.getElementById("drawer");
  const desk = document.querySelector(".desk");
  const caseEl = document.getElementById("case");
  const desktop = matchMedia("(min-width: 961px)");
  const TARGETS =
    "[data-open],[data-tab],[data-topic],[data-clear],[data-ev],[data-score],[data-close-drawer],[data-close-pop],[data-copy],[data-back],[data-query],[data-close-query]";
  const BLOCK = ".claim, .version, .context, .member, .sentence, .sources__list li, .answer, .reply";

  const dock = () => drawer.parentElement !== desk && desk.appendChild(drawer);
  const clearTargets = () => document.querySelectorAll(".is-target").forEach((el) => el.classList.remove("is-target"));

  // app.js closes the source on any click outside it; an in-layout column stays until "Cerrar".
  document.addEventListener("click", (ev) => {
    if (drawer.hidden || ev.target.closest(TARGETS) || ev.target.closest("#drawer")) return;
    if (!ev.target.closest("#popover")) document.getElementById("popover").hidden = true;
    if (!ev.target.closest(".search")) document.getElementById("suggestions").hidden = true;
    ev.stopPropagation();
  }, true);

  // Runs after app.js has filled the drawer for the clicked citation.
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("[data-ev]");
    if (ev.target.closest("[data-close-drawer]")) return clearTargets();
    if (!t) return;
    clearTargets();
    t.classList.add("is-target");
    const close = drawer.querySelector("[data-close-drawer]");
    const drafting = document.body.classList.contains("is-drafting") && desktop.matches;
    if (close) close.insertAdjacentHTML("beforeend", drafting ? "Volver a Co-News" : "Cerrar");
    if (desktop.matches) return dock(), drawer.scrollTo({ top: 0 });
    const block = t.closest(BLOCK);
    block && block.tagName !== "P" ? block.append(drawer) : (block || t).after(drawer);
    drawer.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });

  // Re-rendering the case removes an inline drawer from the DOM; return it closed to the desk.
  new MutationObserver(() => {
    if (drawer.isConnected) return;
    drawer.hidden = true;
    drawer.classList.remove("is-open");
    dock();
  }).observe(caseEl, { childList: true });

  desktop.addEventListener("change", () => desktop.matches && dock());
})();

// Page-local Borrador editor and draft assistant: UI only, a stand-in until the backend endpoints exist (see report).
// Replaces the panel that app.js renders for the Borrador tab; app.js still owns tabs, sources and the drawer.
(() => {
  const D = window.DEMO;
  const caseEl = document.getElementById("case");
  const desk = document.querySelector(".desk");
  const drawer = document.getElementById("drawer");
  const assistant = document.getElementById("assistant");
  const replies = document.getElementById("replies");
  const repliesEmpty = document.getElementById("replies-empty");
  const toggle = document.getElementById("assistant-toggle");
  const askForm = document.getElementById("ask");
  const askInput = document.getElementById("ask-input");
  const askButton = askForm.querySelector("button");
  const mobile = matchMedia("(max-width: 960px)");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const autosize = !CSS.supports("field-sizing", "content");

  const ICONS = {
    alert: '<path d="M12 4 3 19h18Z"/><path d="M12 10v4m0 2.5v.5"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    copy: '<rect x="8" y="8" width="11" height="11" rx="1.5"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    spark: '<path d="M12 4.5c.6 3.9 2.6 5.9 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5 3.9-.6 5.9-2.6 6.5-6.5Z"/>',
  };
  const icon = (name) =>
    `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const number = (n) => n.toLocaleString("es-CO");
  const plural = (n, one, many) => `${number(n)} ${n === 1 ? one : many}`;
  const words = (s) => (s || "").trim().split(/\s+/).filter(Boolean).length;
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const textOf = (v) => (Array.isArray(v) ? v.join("\n") : v);
  const panamaDate = (iso) =>
    new Intl.DateTimeFormat("es-PA", { timeZone: "America/Panama", day: "numeric", month: "short", year: "numeric" }).format(new Date(iso)).replace(".", "");

  const SECTIONS = [
    { key: "titulo", label: "Título propuesto", copy: true },
    { key: "brief", label: "Brief", copy: true },
    { key: "enfoque_interes_publico", label: "Enfoque de interés público" },
    { key: "preguntas", label: "Preguntas de investigación" },
    { key: "fuentes_y_verificaciones", label: "Fuentes y verificaciones pendientes" },
    { key: "guion", label: "Guion", copy: true },
    { key: "copy_digital", label: "Copy digital", copy: true },
  ];
  const labelOf = (key) => SECTIONS.find((s) => s.key === key).label;
  const PROMPTS = [
    ["cifras", "¿Qué cifras de mi borrador no tienen respaldo?"],
    ["relacionados", "Busca otras noticias sobre este tema"],
    ["titulares", "Propón 3 titulares alternativos"],
    ["acortar", "Acorta el copy digital a 80 palabras"],
    ["neutral", "Hazlo más neutral"],
    ["falta", "¿Qué falta verificar antes de publicar?"],
    ["contradicciones", "¿Hay contradicciones entre las fuentes?"],
  ];

  // ---------- Co-News: what to ask, for the whole draft or one section ----------

  const SECTION_PROMPTS = {
    titulo: [["titulares", "Propón 3 titulares alternativos"], ["neutral", "Hazlo más neutral"]],
    brief: [["neutral", "Hazlo más neutral"], ["acortar", "Hazlo más corto"], ["claro", "Hazlo más claro"], ["cifras", "¿Qué cifras de esta sección no tienen respaldo?"]],
    enfoque_interes_publico: [["enfoque", "Propón otro enfoque"], ["neutral", "Hazlo más neutral"]],
    preguntas: [["pregunta", "Sugiere otra pregunta de investigación"]],
    fuentes_y_verificaciones: [["falta", "¿Qué falta verificar antes de publicar?"], ["relacionados", "Busca otras noticias sobre este tema"]],
    guion: [["tv", "Hazlo más fácil de leer al aire"], ["acortar", "Ajústalo a 45-60 segundos"], ["cifras", "¿Qué cifras de esta sección no tienen respaldo?"]],
    copy_digital: [["acortar", "Acórtalo a 80 palabras"], ["neutral", "Hazlo más neutral"], ["cifras", "¿Qué cifras de esta sección no tienen respaldo?"]],
  };
  // A rewrite asked for the whole draft lands on the section it usually means.
  const DEFAULT_SECTION = { neutral: "brief", claro: "brief", tv: "guion", enfoque: "enfoque_interes_publico", pregunta: "preguntas" };
  const INTENTS = [
    [/neutr|imparcial|objetiv/i, "neutral"],
    [/titular/i, "titulares"],
    [/cort|resum|breve|segundos|palabras/i, "acortar"],
    [/al aire|televis|\btv\b|leer|locuci/i, "tv"],
    [/claro|sencill|simple/i, "claro"],
    [/cifra|n[uú]mero/i, "cifras"],
    [/enfoque|[aá]ngulo/i, "enfoque"],
    [/pregunta/i, "pregunta"],
    [/falta|verificar/i, "falta"],
    [/contradic/i, "contradicciones"],
    [/busca|noticias|art[ií]culos|fuentes|datos oficiales|relacionad/i, "relacionados"],
  ];
  // Hand-written demonstration rewrites for the lead case: they reuse only facts already in its draft and file.
  // Any other request answers honestly that it needs the model.
  const EXAMPLES = {
    "CASO-001": {
      brief: {
        neutral: "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios a partir del 12 de octubre, debido al bajo nivel del lago Gatún. La nota de EFE que publican tres medios reproduce ese comunicado, que es la fuente primaria. Como contexto anual, las exportaciones de bienes y servicios representaron el 44,36 % del PIB en 2024; no es una medición actual.",
        acortar: "La Autoridad del Canal de Panamá limitará a 32 los tránsitos diarios desde el 12 de octubre por el bajo nivel del lago Gatún. El comunicado del Canal es la fuente primaria; tres medios replican la misma nota de EFE.",
        claro: "Desde el 12 de octubre pasarán como máximo 32 barcos al día por el Canal de Panamá. Lo informó la Autoridad del Canal: el lago Gatún tiene poca agua. Tres medios publicaron la misma nota de EFE, así que cuentan como una sola fuente. Para dar contexto: en 2024 las exportaciones de bienes y servicios fueron el 44,36 % del PIB (dato anual, no actual).",
      },
      titulo: { neutral: "El Canal de Panamá limitará a 32 los tránsitos diarios desde el 12 de octubre" },
      enfoque_interes_publico: {
        enfoque: "Cómo la restricción cambia la planificación de las navieras que usan el Canal y qué costos logísticos podría mover.",
        neutral: "Efecto de la restricción en el tránsito marítimo y en los costos logísticos.",
      },
      preguntas: { pregunta: "¿Con qué nivel del lago Gatún volvería el Canal a ampliar los tránsitos diarios?" },
      guion: {
        tv: "Desde el 12 de octubre, el Canal de Panamá permitirá solo 32 tránsitos al día. La razón, según la Autoridad del Canal: el bajo nivel del lago Gatún.",
      },
      copy_digital: { neutral: "La Autoridad del Canal de Panamá limitará a 32 los tránsitos diarios desde el 12 de octubre por el bajo nivel del lago Gatún." },
    },
  };
  let scope = "todo";
  const promptsFor = (key) => (key === "todo" ? PROMPTS : SECTION_PROMPTS[key] || []);

  function budget(value, max, unit, min) {
    const over = value > max;
    const under = min && value < min;
    const range = min ? `${min}-${max}` : number(max);
    return `<span class="budget ${over ? "is-over" : under ? "is-under" : ""}">
      <span class="budget__track"><span class="budget__fill" style="width:${Math.min(100, (value / max) * 100)}%"></span></span>
      <span class="budget__text">${number(value)} / ${range} ${unit}</span>
    </span>`;
  }
  const METERS = {
    brief: (v) => budget(words(v), 250, "palabras"),
    guion: (v) => budget(Math.round(words(v) / 2.5), 60, "s", 45),
    copy_digital: (v) => budget(words(v), 80, "palabras"),
  };

  const drafts = {};
  const suggestions = new Map();
  let ctx = null;
  let assistantCase = null;
  let seq = 0;

  // ---------- evidence: numbers and corpus search ----------

  const NUMBER = /\d+(?:[.,:]\d+)*/g;
  const caseIds = (g, f) =>
    new Set([
      ...f.ids_fuente,
      ...g.miembros.map((m) => m.id_noticia),
      ...g.contexto.map((c) => c.id_evidencia),
      ...f.afirmaciones.flatMap((a) => a.citas.map((c) => c.id_evidencia)),
    ]);

  function evidenceNumbers(ids) {
    const index = new Map();
    const add = (n, hit) => {
      if (!index.has(n)) index.set(n, []);
      if (!index.get(n).some((h) => h.id === hit.id)) index.get(n).push(hit);
    };
    ids.forEach((id) => {
      const e = D.evidencias[id];
      if (!e) return;
      Object.entries(e.campos).forEach(([field, text]) =>
        (String(text).match(NUMBER) || []).forEach((n) => {
          add(n, { id, field, passage: n });
          if (n.includes(":")) add(n.split(":")[0], { id, field, passage: n });
        }),
      );
    });
    return index;
  }
  const missingIn = (text) => [...new Set(textOf(text).match(NUMBER) || [])].filter((n) => !ctx.d.numbers.has(n));
  const audit = () =>
    SECTIONS.map((s) => {
      const found = [...new Set(textOf(ctx.d.current[s.key]).match(NUMBER) || [])];
      return { s, unsupported: found.filter((n) => !ctx.d.numbers.has(n)), supported: found.filter((n) => ctx.d.numbers.has(n)) };
    });
  const unsupportedCount = () => audit().reduce((n, r) => n + r.unsupported.length, 0);

  const STOP = new Set("busca buscar otras otros noticias noticia sobre datos dato oficiales oficial fuentes fuente articulos articulo relacionados este esta esto tema para como cual cuales donde desde hasta entre tiene tienen".split(" "));
  const tokens = (s) =>
    new Set(
      (s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").match(/[a-z\d]{4,}/g) || [])
        .filter((t) => !STOP.has(t))
        .map((t) => t.replace(/s$/, "")),
    );
  const memberOf = Object.fromEntries(D.grupos.flatMap((g) => g.miembros.map((m) => [m.id_noticia, m])));
  const KIND = { noticia: "Noticia", indicador: "Indicador oficial", serie_inec: "Serie del INEC", sismo: "Evento USGS" };

  // Searches the whole corpus, outside this case. "esto" or "este tema" falls back to the case title.
  function searchCorpus(query) {
    let q = tokens(query);
    if (!q.size || /\b(esto|este tema)\b/i.test(query)) q = new Set([...q, ...tokens(ctx.g.titulo)]);
    const officialOnly = /oficial/i.test(query);
    const own = caseIds(ctx.g, ctx.f);
    return Object.values(D.evidencias)
      .filter((e) => !own.has(e.id_evidencia) && (!officialOnly || e.tipo !== "noticia"))
      .map((e) => {
        let best = null;
        Object.entries(e.campos).forEach(([field, text]) => {
          const hits = [...tokens(String(text))].filter((t) => q.has(t)).length;
          if (hits && (!best || hits > best.hits)) best = { field, text: String(text), hits };
        });
        return { e, best };
      })
      .filter((r) => r.best && r.best.hits >= 1)
      .sort((a, b) => b.best.hits - a.best.hits)
      .slice(0, 4);
  }

  // ---------- citations ----------

  const sourceNumber = (id) => caseEl.querySelector(`.source-line[data-ev="${CSS.escape(id)}"] .source-line__n`)?.textContent;
  const cite = (hit) => {
    const n = sourceNumber(hit.id);
    if (!n) return "";
    const passage = hit.passage ? `data-passage="${esc(hit.passage)}" data-field="${esc(hit.field)}"` : "";
    return `<button type="button" class="cite" data-ev="${esc(hit.id)}" ${passage} aria-label="Ver fuente ${n}">${n}</button>`;
  };
  const cites = (hits) => `<span class="cites">${hits.map(cite).join("")}</span>`;

  // ---------- editor ----------

  const isDirty = (key) => !same(ctx.d.current[key], ctx.d.saved[key]);
  const fit = (t) => {
    if (!autosize || !t.scrollHeight) return;
    t.style.height = "auto";
    t.style.height = `${t.scrollHeight}px`;
  };

  function fieldHtml(key) {
    const v = ctx.d.current[key];
    if (key === "preguntas")
      return `<ol class="ed-questions">${v
        .map((q, i) => `<li><span class="ed-num" aria-hidden="true">${i + 1}.</span><textarea class="ed ed--text" rows="1" data-key="${key}" data-i="${i}" aria-label="Pregunta ${i + 1}">${esc(q)}</textarea></li>`)
        .join("")}</ol>`;
    if (key === "fuentes_y_verificaciones")
      return `<ul class="ed-list">${v
        .map(
          (item, i) => `<li><span class="ed-bullet" aria-hidden="true"></span><textarea class="ed ed--text" rows="1" data-key="${key}" data-i="${i}" aria-label="Verificación ${i + 1}">${esc(item)}</textarea>
            <button type="button" class="btn btn--quiet btn--small" data-ed="remove" data-i="${i}" aria-label="Quitar verificación ${i + 1}">${icon("close")}Quitar</button></li>`,
        )
        .join("")}</ul>
        <button type="button" class="btn btn--quiet btn--small ed-add" data-ed="add">Añadir verificación</button>`;
    const cls = key === "titulo" ? "ed ed--title" : "ed ed--text";
    return `<textarea class="${cls}" rows="1" data-key="${key}" aria-labelledby="h-${key}">${esc(v)}</textarea>`;
  }

  const sectionHtml = (s) => `<section class="block" data-section="${s.key}">
      <div class="block__head">
        <h2 class="h2" id="h-${s.key}">${s.label}<span class="edited" data-edited hidden>Sin guardar</span></h2>
        ${METERS[s.key] ? `<span data-meter></span>` : ""}
        ${s.copy ? `<button type="button" class="btn btn--quiet btn--small" data-ed="copy" data-key="${s.key}">${icon("copy")}Copiar</button>` : ""}
        <button type="button" class="icon-btn cn-section" data-as="scope" data-key="${s.key}" title="Pedir a Co-News sobre ${s.label}" aria-label="Pedir a Co-News sobre ${s.label}">${icon("spark")}</button>
      </div>
      <div data-body>${fieldHtml(s.key)}</div>
      <p class="unsupported" data-warn hidden></p>
    </section>`;

  const editorHtml = () => `${ctx.f.borrador.leyenda ? `<p class="notice">${icon("alert")}${esc(ctx.f.borrador.leyenda)}</p>` : ""}
    <div class="savebar" id="savebar">
      <p class="savebar__state"><span class="savebar__dot" aria-hidden="true"></span><span data-state></span></p>
      <div class="savebar__actions">
        <button type="button" class="btn btn--quiet btn--small" data-ed="discard">Descartar cambios</button>
        <button type="button" class="btn btn--primary btn--small" data-ed="save">Guardar cambios</button>
      </div>
      <p class="savebar__msg" data-msg role="status" hidden>${icon("alert")}<span>Pendiente de conexión con el backend: los cambios siguen solo en esta pantalla.</span></p>
    </div>
    <div class="ed-hint">
      <span>Haz clic en cualquier texto para editarlo.</span>
      <button type="button" class="link" data-ed="restore">Restaurar borrador de la IA</button>
    </div>
    <div class="ed-confirm" data-confirm hidden>
      <span>Se reemplazará todo el borrador por el texto que generó la IA.</span>
      <button type="button" class="btn btn--small" data-ed="restore-yes">Restaurar</button>
      <button type="button" class="btn btn--quiet btn--small" data-ed="restore-no">Cancelar</button>
    </div>
    ${SECTIONS.map(sectionHtml).join("")}`;

  function refreshSection(key) {
    const el = caseEl.querySelector(`[data-section="${key}"]`);
    if (!el) return;
    const v = ctx.d.current[key];
    el.querySelector("[data-edited]").hidden = !isDirty(key);
    if (METERS[key]) el.querySelector("[data-meter]").innerHTML = METERS[key](v);
    const missing = missingIn(v);
    const warn = el.querySelector("[data-warn]");
    warn.hidden = !missing.length;
    warn.innerHTML = missing.length
      ? `${icon("alert")}<span>${missing.length === 1 ? "Cifra sin respaldo" : "Cifras sin respaldo"}: ${missing
          .map((n) => `<strong>${esc(n)}</strong>`)
          .join(", ")} no ${missing.length === 1 ? "aparece" : "aparecen"} en la evidencia del caso.</span>`
      : "";
  }

  function refreshStatus() {
    const dirty = SECTIONS.filter((s) => isDirty(s.key)).length;
    const unsupported = unsupportedCount();
    const bar = document.getElementById("savebar");
    bar.classList.toggle("is-dirty", dirty > 0);
    bar.querySelector("[data-state]").innerHTML =
      (dirty ? `Cambios sin guardar en ${plural(dirty, "sección", "secciones")}` : "Sin cambios") +
      (unsupported ? ` <span class="savebar__extra">· ${plural(unsupported, "cifra sin respaldo", "cifras sin respaldo")}</span>` : "");
    bar.querySelector('[data-ed="save"]').disabled = !dirty;
    bar.querySelector('[data-ed="discard"]').disabled = !dirty;
    caseEl.querySelector('[data-ed="restore"]').disabled = same(ctx.d.current, ctx.d.ai);
  }

  function mountEditor() {
    const panel = caseEl.querySelector(".panel");
    panel.innerHTML = editorHtml();
    panel.querySelectorAll("textarea").forEach(fit);
    SECTIONS.forEach((s) => refreshSection(s.key));
    refreshStatus();
  }

  function renderBody(key) {
    const body = caseEl.querySelector(`[data-section="${key}"] [data-body]`);
    body.innerHTML = fieldHtml(key);
    body.querySelectorAll("textarea").forEach(fit);
    refreshSection(key);
    refreshStatus();
  }

  const showMsg = (on) => {
    const msg = caseEl.querySelector("[data-msg]");
    if (msg) msg.hidden = !on;
  };

  function goTo(key, focusLast) {
    if (mobile.matches) setSheet(false);
    const section = caseEl.querySelector(`[data-section="${key}"]`);
    if (!section) return;
    section.scrollIntoView({ block: "center", behavior: reduced.matches ? "auto" : "smooth" });
    const fields = section.querySelectorAll("textarea");
    const field = focusLast ? fields[fields.length - 1] : fields[0];
    if (!field) return;
    field.classList.remove("is-flash");
    void field.offsetWidth;
    field.classList.add("is-flash");
    field.focus({ preventScroll: true });
  }

  function editAction(btn) {
    const d = ctx.d;
    const action = btn.dataset.ed;
    const confirm = caseEl.querySelector("[data-confirm]");
    if (action === "copy") {
      navigator.clipboard?.writeText(textOf(d.current[btn.dataset.key]));
      const old = btn.innerHTML;
      btn.textContent = "Copiado";
      setTimeout(() => (btn.innerHTML = old), 1400);
    }
    if (action === "save") showMsg(true);
    if (action === "discard") (d.current = structuredClone(d.saved)), mountEditor();
    if (action === "restore") confirm.hidden = false;
    if (action === "restore-no") confirm.hidden = true;
    if (action === "restore-yes") (d.current = structuredClone(d.ai)), mountEditor();
    if (action === "add") d.current.fuentes_y_verificaciones.push(""), renderBody("fuentes_y_verificaciones"), goTo("fuentes_y_verificaciones", true);
    if (action === "remove") d.current.fuentes_y_verificaciones.splice(Number(btn.dataset.i), 1), renderBody("fuentes_y_verificaciones");
  }

  caseEl.addEventListener("input", (ev) => {
    const t = ev.target.closest("textarea[data-key]");
    if (!t || !ctx) return;
    const key = t.dataset.key;
    if (t.dataset.i !== undefined) ctx.d.current[key][Number(t.dataset.i)] = t.value;
    else ctx.d.current[key] = t.value;
    fit(t);
    showMsg(false);
    refreshSection(key);
    refreshStatus();
  });

  // ---------- assistant ----------

  const STATE = (variant, text) => `<p class="reply__state reply__state--${variant}">${text}</p>`;
  const SAMPLE = STATE("sample", "Propuesta de ejemplo: Co-News aún no tiene un modelo conectado");
  const suggest = (payload) => {
    const id = `s${++seq}`;
    suggestions.set(id, payload);
    return id;
  };
  const suggestion = (key, before, after, note, value = after) => `<div class="suggestion">
      <p class="reply__h">Edición sugerida · ${labelOf(key)}</p>
      ${note ? `<p class="reply__foot">${note}</p>` : ""}
      <p class="diff__label">Antes</p><p class="diff diff--before">${esc(before)}</p>
      <p class="diff__label">Después</p><p class="diff diff--after">${esc(after)}</p>
      <div class="reply__actions">
        <button type="button" class="btn btn--small" data-as="apply" data-s="${suggest({ key, value })}">Aplicar</button>
        <button type="button" class="btn btn--quiet btn--small" data-as="dismiss">Descartar</button>
      </div>
    </div>`;
  const modelOnly = () => `${STATE("sample", "Necesita el modelo: Co-News aún no está conectado")}
    <p>Cuando Co-News esté conectado, propondrá una edición que podrás aplicar o descartar, citará las fuentes del caso o dirá «No hay evidencia suficiente» si no puede hacerlo.</p>`;

  function rewrite(kind, key) {
    const example = EXAMPLES[ctx.f.id_caso]?.[key]?.[kind];
    const current = ctx.d.current[key];
    if (!example) return modelOnly();
    if (key === "preguntas")
      return `${SAMPLE}${suggestion(key, current.join("\n"), [...current, example].join("\n"), "Propuesta de ejemplo para la demostración: añade una pregunta y no agrega hechos nuevos.", [...current, example])}`;
    if (example === current) return `${STATE("ok", "Sin cambios que proponer")}<p>${labelOf(key)} ya está escrito así.</p>`;
    return `${SAMPLE}${suggestion(key, current, example, "Propuesta de ejemplo para la demostración: usa solo hechos que ya están en la ficha.")}`;
  }

  const ANSWERS = {
    cifras(question, key) {
      const rows = audit().filter((r) => !key || r.s.key === key);
      const missing = rows.flatMap((r) => r.unsupported.map((n) => ({ n, s: r.s })));
      const backed = new Map();
      rows.forEach((r) => r.supported.forEach((n) => backed.set(n, ctx.d.numbers.get(n))));
      if (!missing.length && !backed.size) return `${STATE("ok", "Sin cifras")}<p>Tu borrador no contiene cifras.</p>`;
      return `${missing.length ? STATE("warn", plural(missing.length, "cifra sin respaldo", "cifras sin respaldo")) : STATE("ok", "Respuesta con evidencia")}
        ${missing.length ? `<p>No aparecen en la evidencia del caso:</p><ul>${missing
          .map((m) => `<li><strong>${esc(m.n)}</strong> en ${m.s.label} · <button type="button" class="link" data-as="goto" data-key="${m.s.key}">Ir a la sección</button></li>`)
          .join("")}</ul>` : ""}
        ${backed.size ? `<p>${missing.length ? "Sí tienen respaldo:" : "Todas las cifras aparecen en la evidencia del caso:"}</p><ul>${[...backed]
          .map(([n, hits]) => `<li><strong>${esc(n)}</strong> ${cites(hits)}</li>`)
          .join("")}</ul>` : ""}
        <p class="reply__foot">Comprobación local: busca cada cifra del borrador en las fuentes del caso. No reemplaza al verificador.</p>`;
    },

    falta() {
      const f = ctx.f;
      const pending = ctx.d.current.fuentes_y_verificaciones.filter((v) => v.trim());
      const missing = unsupportedCount();
      return `${STATE("info", "Según la ficha del caso")}
        ${f.alcance_texto === "titular_metadatos" ? `<p class="notice">${icon("alert")}Basado únicamente en titular/metadatos.</p>` : ""}
        <p class="reply__h">Verificaciones pendientes en tu borrador</p>
        ${pending.length ? `<ul>${pending.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>` : `<p>Tu borrador no tiene verificaciones anotadas.</p>`}
        ${f.vacios.length ? `<p class="reply__h">Lo que la ficha marca como faltante</p><ul>${f.vacios.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>` : ""}
        ${f.contradicciones.length ? `<p class="reply__h">Contradicciones sin resolver</p><ul>${f.contradicciones.map((c) => `<li>${esc(c.descripcion)}</li>`).join("")}</ul>` : ""}
        ${missing ? `<p class="reply__h">Cifras sin respaldo</p><p>${plural(missing, "cifra", "cifras")} del borrador no ${missing === 1 ? "aparece" : "aparecen"} en la evidencia. <button type="button" class="link" data-as="prompt" data-p="cifras">Ver cuáles</button></p>` : ""}
        <p class="reply__h">Acción recomendada</p><p>${esc(f.accion_recomendada)}</p>`;
    },

    contradicciones() {
      const { g, f } = ctx;
      if (f.contradicciones.length)
        return `${STATE("contra", "Las fuentes no coinciden")}
          ${f.contradicciones
            .map(
              (c) => `<p>${esc(c.descripcion)}</p><div class="versions">${c.versiones
                .map((v) => `<div class="version"><p class="version__value">${esc(v.valor)}</p><p class="version__scope">${esc(v.alcance)}</p>${cite({ id: v.id_evidencia, field: "titulo", passage: v.valor })}</div>`)
                .join("")}</div>`,
            )
            .join("")}
          <p class="reply__foot">Verificación pendiente: el sistema no elige una versión.</p>`;
      const origins = new Map();
      g.miembros.forEach((m) => origins.has(m.procedencia) || origins.set(m.procedencia, m.id_noticia));
      if (origins.size >= 2)
        return `${STATE("ok", "Respuesta con evidencia")}
          <p>La ficha no registra contradicciones entre las ${number(origins.size)} procedencias del caso:</p>
          <ul>${[...origins].map(([o, id]) => `<li>${esc(o)} ${cites([{ id }])}</li>`).join("")}</ul>`;
      return `${STATE("abstain", "No hay evidencia suficiente")}
        <p>Este caso tiene una sola procedencia (${esc([...origins.keys()][0])}): no hay otra fuente con la cual comparar.</p>
        <p class="reply__h">Qué se necesitaría</p><p>Una segunda fuente independiente sobre el mismo hecho.</p>`;
    },

    relacionados(question) {
      const results = searchCorpus(question);
      if (!results.length)
        return `${STATE("abstain", "No hay evidencia suficiente")}
          <p>No encontré otras noticias ni datos del corpus que traten este tema fuera de las fuentes del caso.</p>
          <p class="reply__h">Qué se necesitaría</p><p>Una fuente nueva sobre el mismo hecho, cargada en el corpus.</p>`;
      return `${STATE("ok", "Artículos relacionados")}
        <p>${plural(results.length, "resultado", "resultados")} del corpus completo, fuera de las fuentes de este caso:</p>
        <ul class="results">${results
          .map(({ e, best }) => {
            const m = memberOf[e.id_evidencia];
            const outlet = m ? m.medio : KIND[e.tipo] || "Fuente";
            const when = e.fecha ? panamaDate(e.fecha) : e.campos.periodo || "";
            const added = ctx.d.added.has(e.id_evidencia);
            return `<li class="result">
              <p class="meta"><span class="topic">${esc(outlet)}</span>${when ? `<span>${esc(when)}</span>` : ""}</p>
              <p class="result__title">${esc(e.titulo)}</p>
              ${best.text !== e.titulo ? `<p class="result__passage">«${esc(best.text)}»</p>` : ""}
              <div class="reply__actions">
                <button type="button" class="btn btn--small" data-ev="${esc(e.id_evidencia)}">Ver fuente</button>
                <button type="button" class="btn btn--quiet btn--small" data-as="add-source" data-id="${esc(e.id_evidencia)}" ${added ? "disabled" : ""}>${added ? "Añadida a la ficha" : "Añadir a la ficha"}</button>
              </div>
            </li>`;
          })
          .join("")}</ul>
        <p class="reply__foot">Búsqueda local por palabras clave en el corpus de demostración.</p>`;
    },

    titulares() {
      const { g, d } = ctx;
      const strip = (t) => t.replace(/\s*\([^)]*\)\s*$/, "");
      const options = [...new Set([g.titulo, ...g.miembros.map((m) => strip(m.titulo))])].filter((t) => t !== d.current.titulo).slice(0, 3);
      const head = `${SAMPLE}<p>Sin el asistente no se redactan titulares nuevos. Como ejemplo, estos titulares ya existen en las fuentes del caso:</p>`;
      if (!options.length) return `${head}<p>No hay otros titulares en las fuentes del caso.</p>`;
      return `${head}<div class="suggestion">
          <p class="reply__h">Edición sugerida · Título propuesto</p>
          <p class="diff__label">Antes</p><p class="diff diff--before">${esc(d.current.titulo)}</p>
          ${options
            .map(
              (t, i) => `<div class="option"><p class="diff__label">Después, opción ${i + 1}</p><p class="diff diff--after">${esc(t)}</p>
                <div class="reply__actions"><button type="button" class="btn btn--small" data-as="apply" data-s="${suggest({ key: "titulo", value: t })}">Aplicar esta opción</button></div></div>`,
            )
            .join("")}
          <div class="reply__actions"><button type="button" class="btn btn--quiet btn--small" data-as="dismiss">Descartar</button></div>
        </div>`;
    },

    acortar(question, key) {
      if (key && key !== "copy_digital") return rewrite("acortar", key);
      const current = ctx.d.current.copy_digital;
      const n = words(current);
      if (n <= 80) return `${STATE("ok", "Comprobación local")}<p>El copy digital ya tiene ${plural(n, "palabra", "palabras")}: está dentro del límite de 80.</p>`;
      const ai = ctx.d.ai.copy_digital;
      return `${SAMPLE}<p>El copy digital tiene ${plural(n, "palabra", "palabras")}; el límite es 80.</p>
        ${words(ai) <= 80 && ai !== current ? suggestion("copy_digital", current, ai, "Ejemplo con el copy que generó la IA, no una versión nueva.") : ""}`;
    },

    neutral: (question, key) => rewrite("neutral", key),
    claro: (question, key) => rewrite("claro", key),
    tv: (question, key) => rewrite("tv", key),
    enfoque: (question, key) => rewrite("enfoque", key),
    pregunta: (question, key) => rewrite("pregunta", key),
    libre: modelOnly,
  };

  // A whole-draft rewrite request is routed to its usual section; checks and searches stay draft-wide.
  function ask(kind, question, key = null) {
    const section = key || DEFAULT_SECTION[kind] || null;
    repliesEmpty.hidden = true;
    const li = document.createElement("li");
    li.className = "reply";
    const head = `<p class="reply__q">${esc(question)}</p><p class="reply__scope">${section ? `Sección: ${labelOf(section)}` : "Todo el borrador"}</p>`;
    li.innerHTML = `${head}${STATE("pending", "Co-News está revisando…")}<span class="pending-bar" aria-hidden="true"><span></span></span>`;
    replies.prepend(li);
    li.scrollIntoView({ block: "nearest" });
    const forCase = ctx.f.id_caso;
    setTimeout(() => {
      if (!li.isConnected || ctx?.f.id_caso !== forCase) return;
      li.innerHTML = `${head}${ANSWERS[kind](question, section)}`;
    }, 700);
  }

  function askFree(text) {
    const key = scope === "todo" ? null : scope;
    const prompt = promptsFor(scope).find(([, t]) => t.toLowerCase() === text.toLowerCase());
    const intent = INTENTS.find(([re]) => re.test(text));
    ask(prompt ? prompt[0] : intent ? intent[1] : "libre", text, key);
  }

  function renderPrompts() {
    document.getElementById("prompts").innerHTML = promptsFor(scope)
      .map(([k, t]) => `<button type="button" class="prompt" data-as="prompt" data-p="${k}">${esc(t)}</button>`)
      .join("");
    askInput.placeholder = scope === "todo" ? "Por ejemplo: hazlo más neutral, o ¿hay datos oficiales sobre esto?" : `Qué hacer con ${labelOf(scope).toLowerCase()}: por ejemplo, hazlo más corto`;
  }
  function setScope(key) {
    scope = key;
    scopeSelect.value = key;
    renderPrompts();
  }

  function settle(btn, html) {
    const reply = btn.closest(".reply");
    reply.querySelectorAll(".suggestion .reply__actions").forEach((a) => a.remove());
    reply.querySelector(".suggestion").insertAdjacentHTML("beforeend", `<p class="reply__done">${html}</p>`);
  }

  function assistantAction(btn) {
    const action = btn.dataset.as;
    if (action === "open") return setSheet(true);
    if (action === "close") return setSheet(false);
    if (!ctx) return;
    if (action === "prompt") {
      const list = btn.closest("#prompts") ? promptsFor(scope) : PROMPTS;
      const key = btn.closest("#prompts") && scope !== "todo" ? scope : null;
      return ask(btn.dataset.p, list.find(([k]) => k === btn.dataset.p)[1], key);
    }
    if (action === "scope") {
      setScope(btn.dataset.key);
      setSheet(true);
      return askInput.focus({ preventScroll: true });
    }
    if (action === "goto") return goTo(btn.dataset.key);
    if (action === "dismiss") return settle(btn, "Sugerencia descartada.");
    if (action === "apply") {
      const s = suggestions.get(btn.dataset.s);
      ctx.d.current[s.key] = s.value;
      settle(btn, `${icon("check")}Aplicada a ${labelOf(s.key)}. Queda sin guardar.`);
      showMsg(false);
      renderBody(s.key);
      return goTo(s.key);
    }
    if (action === "add-source") {
      const e = D.evidencias[btn.dataset.id];
      const m = memberOf[e.id_evidencia];
      const when = e.fecha ? panamaDate(e.fecha) : e.campos.periodo;
      ctx.d.added.add(e.id_evidencia);
      ctx.d.current.fuentes_y_verificaciones.push(`Revisar fuente añadida: «${e.titulo}» (${m ? m.medio : KIND[e.tipo]}, ${when}).`);
      btn.disabled = true;
      btn.textContent = "Añadida a la ficha";
      showMsg(false);
      renderBody("fuentes_y_verificaciones");
      return goTo("fuentes_y_verificaciones", true);
    }
  }

  function setSheet(open) {
    assistant.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    if (!mobile.matches) return;
    (open ? assistant.querySelector('[data-as="close"]') : document.body.classList.contains("is-drafting") && toggle)?.focus?.();
  }

  function resetAssistant(id) {
    if (assistantCase === id) return;
    if (assistant.contains(drawer)) {
      drawer.hidden = true;
      drawer.classList.remove("is-open");
      desk.appendChild(drawer);
    }
    replies.innerHTML = "";
    setScope("todo");
    suggestions.clear();
    repliesEmpty.hidden = false;
    askInput.value = "";
    askButton.disabled = true;
    assistantCase = id;
  }

  const scopeSelect = document.getElementById("cn-scope");
  scopeSelect.innerHTML = `<option value="todo">Todo el borrador</option>${SECTIONS.map((s) => `<option value="${s.key}">${s.label}</option>`).join("")}`;
  scopeSelect.addEventListener("change", () => setScope(scopeSelect.value));
  renderPrompts();
  askInput.addEventListener("input", () => (askButton.disabled = !askInput.value.trim()));
  askForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = askInput.value.trim();
    if (!text || !ctx) return;
    askFree(text);
    askInput.value = "";
    askButton.disabled = true;
  });

  // Capture phase: the in-layout drawer script stops propagation of outside clicks while a source is open.
  document.addEventListener(
    "click",
    (ev) => {
      const ed = ev.target.closest("[data-ed]");
      if (ed && ctx) return editAction(ed);
      const as = ev.target.closest("[data-as]");
      if (as) assistantAction(as);
    },
    true,
  );

  // ---------- mount on the Borrador tab ----------

  function sync() {
    const tab = caseEl.querySelector('.tab[aria-selected="true"]')?.dataset.tab;
    const g = D.grupos.find((x) => x.id_grupo === location.hash.slice(1).split("/")[0]);
    const f = g?.id_caso && D.fichas.find((x) => x.id_caso === g.id_caso);
    const on = tab === "borrador" && !!f?.borrador;
    document.body.classList.toggle("is-drafting", on);
    if (!on) {
      ctx = null;
      return setSheet(false);
    }
    const d = (drafts[f.id_caso] ||= {
      ai: structuredClone(f.borrador),
      saved: structuredClone(f.borrador),
      current: structuredClone(f.borrador),
      numbers: evidenceNumbers(caseIds(g, f)),
      added: new Set(),
    });
    ctx = { g, f, d };
    mountEditor();
    resetAssistant(f.id_caso);
  }

  new MutationObserver(sync).observe(caseEl, { childList: true });
  if (autosize) new ResizeObserver(() => caseEl.querySelectorAll("textarea.ed").forEach(fit)).observe(caseEl);
  addEventListener("beforeunload", (ev) => {
    if (Object.values(drafts).some((d) => !same(d.current, d.saved))) ev.preventDefault();
  });
  sync();
})();
