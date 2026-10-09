/* The editor keeps unsaved work locally; only an explicit save writes to SQLite. */
(() => {
  let current = null;
  const clone = value => structuredClone(value);
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const element = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, action, cls = 'btn btn--small') => {
    const node = element('button', cls, text);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  };
  const PANAMA_DAY = new Intl.DateTimeFormat('en-US', {timeZone: 'America/Panama', day: '2-digit', month: '2-digit', year: 'numeric'});
  const panamaDate = value => {
    const part = Object.fromEntries(PANAMA_DAY.formatToParts(new Date(value)).map(({type, value: text}) => [type, text]));
    return `${part.day}/${part.month}/${part.year}`;
  };
  const SEARCH_REQUEST = /busca|buscar|noticias|art[ií]culos/i;
  const QUESTION = /\?\s*$|^\s*¿|^\s*(qu[eé]|cu[aá]l(es)?|c[oó]mo|por qu[eé]|qui[eé]n(es)?|cu[aá]ndo|d[oó]nde|cu[aá]nt[oa]s?|hay|existe|es|son)(?=\s|$)/i;
  // In the whole-draft scope a typed request is an edit unless it is clearly a search or a question.
  const requestAction = (question, field) => field ? 'rewrite' : SEARCH_REQUEST.test(question) ? 'articles' : QUESTION.test(question) ? 'ask' : 'rewrite';
  const pendingLabels = {rewrite: 'Redactando…', headlines: 'Redactando…', shorten: 'Redactando…', neutral: 'Redactando…', articles: 'Buscando noticias…'};
  const BUDGETS = [{key: 'brief', label: 'Brief', max: 250, min: 0, unit: 'palabras'}, {key: 'guion', label: 'Guion', max: 60, min: 45, unit: 's'}, {key: 'copy_digital', label: 'Copy digital', max: 80, min: 0, unit: 'palabras'}];
  const words = text => text.trim().split(/\s+/).filter(Boolean).length;
  const budgetAmount = (key, draft) => key === 'guion' ? Math.round(words(draft[key]) / 2.5) : words(draft[key]);
  const labels = {titulo: 'Título propuesto', brief: 'Brief', guion: 'Guion', copy_digital: 'Copy digital', enfoque_interes_publico: 'Enfoque de interés público'};

  function mount(root) {
    const desk = root.closest('.desk');
    const assistant = root.querySelector('.draft-assistant');
    const source = root.querySelector('.editor-source');
    const toggle = root.querySelector('.sheet-toggle');
    const form = root.querySelector('.draft-form');
    const askForm = assistant.querySelector('.ask');
    const input = assistant.querySelector('.ask__input');
    const replies = assistant.querySelector('.replies');
    const scope = assistant.querySelector('[data-cn-scope]');
    // Co-News: a rewrite targets the chosen field, or lets the assistant pick one when the scope is the whole draft.
    const chosenField = () => scope.value === 'todo' ? null : scope.value;
    const placeholders = {todo: 'Por ejemplo: busca noticias sobre el Canal, o hazlo más neutral'};
    function setScope(key) {
      scope.value = key;
      assistant.dataset.scope = key;
      input.placeholder = placeholders[key] || `Qué hacer con ${labels[key].toLowerCase()}: por ejemplo, hazlo más corto`;
      showPrompts(true);
    }
    const bar = root.querySelector('.savebar');
    const message = root.querySelector('[data-save-message]');
    const abort = new AbortController();
    const caseId = root.dataset.editor;
    const config = JSON.parse(root.querySelector('[data-editor-config]').textContent);
    let saved = config;
    let conflict = null;
    let sources = saved.source_ids.slice();
    let saving = false;
    let asking = false;
    desk.append(assistant, source, toggle);
    const api = `/api/cases/${encodeURIComponent(caseId)}`;

    const notify = (text, error = false) => {
      message.hidden = !text;
      message.textContent = text;
      message.setAttribute('role', error ? 'alert' : 'status');
    };
    async function request(url, options = {}) {
      const response = await fetch(url, {...options, signal: abort.signal, headers: {'Content-Type': 'application/json', ...options.headers}});
      let data;
      try { data = await response.json(); } catch { throw new Error('No se pudo leer la respuesta del servidor. Intenta de nuevo.'); }
      if (!response.ok) throw Object.assign(new Error(data.message || 'No se pudo completar la solicitud.'), {status: response.status, field: data.field, index: data.index});
      return data;
    }
    const collect = () => {
      const draft = clone(saved.draft);
      form.querySelectorAll('textarea[data-key]').forEach(field => {
        if (!field.closest('[data-list]')) draft[field.dataset.key] = field.value;
      });
      form.querySelectorAll('[data-list]').forEach(list => {
        draft[list.dataset.list] = [...list.querySelectorAll('textarea')].map(field => field.value);
      });
      return draft;
    };
    const dirty = () => !equal(collect(), saved.draft) || !equal(sources, saved.source_ids);
    const fit = field => {
      field.style.height = 'auto';
      field.style.height = `${field.scrollHeight + field.offsetHeight - field.clientHeight}px`;
    };
    const listLabel = key => key === 'preguntas' ? 'Pregunta' : 'Verificación';
    function renderList(key, values) {
      const list = root.querySelector(`[data-list="${key}"]`);
      list.replaceChildren();
      values.forEach((value, index) => {
        const row = element('li');
        const number = element('span', 'ed-num', `${index + 1}.`);
        number.setAttribute('aria-hidden', 'true');
        const field = element('textarea', 'ed ed--text');
        field.rows = 1;
        field.maxLength = 2000;
        field.dataset.key = key;
        field.setAttribute('aria-label', `${listLabel(key)} ${index + 1}`);
        field.value = value;
        const remove = element('button', 'btn btn--quiet btn--small', 'Quitar');
        remove.type = 'button';
        remove.dataset.edit = 'remove';
        remove.setAttribute('aria-label', `Quitar ${listLabel(key).toLowerCase()} ${index + 1}`);
        row.append(number, field, remove);
        list.append(row);
        fit(field);
      });
    }
    function renderDraft(draft) {
      form.querySelectorAll('textarea[data-key]').forEach(field => {
        if (!field.closest('[data-list]')) field.value = draft[field.dataset.key];
      });
      for (const key of ['preguntas', 'fuentes_y_verificaciones']) renderList(key, draft[key]);
      form.querySelectorAll('textarea').forEach(fit);
      refresh();
    }
    function refresh() {
      const draft = collect();
      const dirty = !equal(draft, saved.draft) || !equal(sources, saved.source_ids);
      bar.classList.toggle('is-dirty', dirty);
      root.querySelector('[data-save-state]').textContent = saving ? 'Guardando…' : dirty ? 'Cambios sin guardar' : 'Sin cambios';
      root.querySelector('[data-edit="save"]').disabled = saving || !dirty || Boolean(conflict);
      root.querySelector('[data-edit="discard"]').disabled = saving || !dirty;
      for (const {key, max, min, unit} of BUDGETS) {
        const meter = root.querySelector(`[data-meter="${key}"]`);
        const amount = budgetAmount(key, draft);
        meter.classList.toggle('is-over', amount > max);
        meter.classList.toggle('is-under', Boolean(min && amount < min));
        meter.querySelector('.budget__fill').style.width = `${Math.min(100, amount / max * 100)}%`;
        meter.querySelector('.budget__text').textContent = `${amount} / ${min ? `${min}-${max}` : max} ${unit}`;
      }
    }
    const budgetWarnings = draft => BUDGETS.flatMap(({key, label, max, min, unit}) => {
      const amount = budgetAmount(key, draft);
      if (amount > max) return [`${label} supera el límite (${amount} / ${max} ${unit})`];
      return min && amount < min ? [`${label} queda por debajo del mínimo (${amount} / ${min}-${max} ${unit})`] : [];
    });
    const reviewBadges = () => {
      const group = CSS.escape(root.dataset.group);
      return document.querySelectorAll(`.case__badges .review, #review-badge-${group}, #lead-review-badge-${group}`);
    };
    // Saving changes the content, so the previous human decision no longer applies anywhere on the page.
    const showReviewState = state => reviewBadges().forEach(badge => {
      badge.textContent = config.review_labels[state];
      badge.className = `badge review review--${state}`;
    });
    const markInvalid = error => {
      const fields = error.field && (error.index === null || error.index === undefined)
        ? [...form.querySelectorAll(`textarea[data-key="${error.field}"]`)].filter(field => !field.closest('[data-list]'))
        : [...form.querySelectorAll(`[data-list="${error.field}"] textarea`)].slice(error.index, error.index + 1);
      fields.forEach(field => { field.setAttribute('aria-invalid', 'true'); field.setAttribute('aria-describedby', message.id); field.focus(); });
    };
    const clearInvalid = () => form.querySelectorAll('[aria-invalid]').forEach(field => { field.removeAttribute('aria-invalid'); field.removeAttribute('aria-describedby'); });
    const conflictPanel = root.querySelector('[data-conflict]');
    function showConflict(latest) {
      conflict = latest;
      const mine = collect();
      const body = conflictPanel.querySelector('[data-conflict-diff]');
      body.replaceChildren();
      for (const key of Object.keys(latest.draft)) {
        if (equal(mine[key], latest.draft[key])) continue;
        const theirs = Array.isArray(latest.draft[key]) ? latest.draft[key].map((item, index) => `${index + 1}. ${item}`).join('\n') : latest.draft[key];
        const detail = element('details');
        detail.append(element('summary', '', `${labels[key] || (key === 'preguntas' ? 'Preguntas de investigación' : 'Fuentes y verificaciones')}: versión de la otra persona`), element('p', 'conflict__text', theirs));
        body.append(detail);
      }
      if (!body.children.length) body.append(element('p', 'muted', 'El texto es igual; la otra persona cambió las fuentes del caso.'));
      conflictPanel.hidden = false;
      notify('');
      refresh();
      conflictPanel.scrollIntoView({block: 'nearest'});
    }
    function resolveConflict(adopt) {
      saved = conflict;
      conflict = null;
      conflictPanel.hidden = true;
      if (adopt) {
        sources = saved.source_ids.slice();
        renderDraft(saved.draft);
        renderSources();
        notify('Se cargó la versión de la otra persona.');
      } else form.requestSubmit();
      refresh();
    }
    function renderSources() {
      const list = root.querySelector('[data-source-list]');
      list.replaceChildren();
      sources.forEach((id, index) => {
        const node = button(`Ver fuente ${index + 1}${saved.source_ids.includes(id) ? '' : ' · sin guardar'}`, () => openSource(id), 'link');
        list.append(node);
      });
    }
    function setAssistant(open) {
      assistant.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      if (matchMedia('(max-width: 960px)').matches) (open ? assistant.querySelector('[data-assist="close"]') : toggle).focus();
    }
    let sourceOpener = null;
    function closeSource() {
      source.hidden = true;
      setAssistant(true);
      if (sourceOpener?.isConnected) sourceOpener.focus({preventScroll: true});
      sourceOpener = null;
    }
    // The headline and date sit in the drawer header, so the passages list skips them unless a citation points at them.
    const marked = (node, text, citation, field) => {
      const at = citation && citation.campo === field ? text.indexOf(citation.pasaje) : -1;
      if (at < 0) return node.append(document.createTextNode(text));
      node.append(document.createTextNode(text.slice(0, at)), element('mark', '', citation.pasaje), document.createTextNode(text.slice(at + citation.pasaje.length)));
    };
    async function openSource(id, citation) {
      if (source.hidden) sourceOpener = document.activeElement;
      root.classList.remove('cn-closed');
      source.hidden = false;
      const body = source.querySelector('[data-source-body]');
      body.replaceChildren(element('p', 'muted', 'Cargando fuente…'));
      source.querySelector('[data-edit="close-source"]').focus({preventScroll: true});
      try {
        const evidence = await request(`/api/evidence/${encodeURIComponent(id)}`);
        const title = element('h3', 'drawer__title');
        marked(title, evidence.titulo, citation, 'titulo');
        body.replaceChildren(title);
        if (evidence.fecha_texto) body.append(element('p', 'muted', `${evidence.fecha_texto} (Panamá)`));
        for (const [field, value] of Object.entries(evidence.campos)) {
          if (field === 'titulo' || (field === 'fecha_publicacion' && citation?.campo !== field)) continue;
          const section = element('section', 'passage');
          section.append(element('p', 'passage__field', evidence.etiquetas[field] || field));
          const text = element('p');
          marked(text, value, citation, field);
          section.append(text);
          body.append(section);
        }
        if (/^https?:\/\//i.test(evidence.url)) {
          const link = element('a', 'link link--external', 'Abrir fuente original');
          link.href = evidence.url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          body.append(link);
        }
      } catch (error) {
        if (error.name !== 'AbortError') body.replaceChildren(element('p', 'notice', error.message));
      }
    }
    function showPrompts(show) {
      assistant.classList.toggle('has-replies', !show);
    }
    function citations(row, values = []) {
      if (!values.length) return;
      const list = element('div', 'reply__actions');
      values.forEach((citation, index) => list.append(button(`Fuente ${index + 1}`, () => openSource(citation.id_evidencia, citation), 'cite')));
      row.append(list);
    }
    function renderReply(row, result, snapshot) {
      const names = {answer: 'Respuesta con evidencia', suggestion: 'Edición sugerida', articles: 'Artículos relacionados', abstention: 'Abstención', contradiction: 'Contradicción'};
      row.append(element('p', `reply__state reply__state--${result.kind}`, names[result.kind]), element('p', '', result.text));
      row.append(element('p', 'reply__origin', result.origin === 'gemini' ? 'Respondido por Gemini' : 'Respondido con el corpus cargado, sin Gemini'));
      if (result.cached) row.append(element('p', 'reply__state reply__state--cached', 'Respuesta guardada'));
      const warn = text => element('p', 'reply__warn', `⚠ Verifica antes de aplicar: ${text}`);
      if (result.kind !== 'suggestion') for (const warning of result.warnings || []) row.append(warn(warning));
      if (result.missing) row.append(element('p', 'reply__h', 'Qué se necesitaría'), element('p', '', result.missing));
      if (result.kind === 'suggestion') {
        row.append(element('p', 'reply__h', labels[result.field]), element('p', 'diff__label', 'Antes'), element('p', 'diff diff--before', snapshot[result.field]));
        const options = element('div', 'suggestion');
        result.options.forEach((value, index) => {
          const option = element('div', 'option');
          option.append(element('p', 'diff__label', 'Después'), element('p', 'diff diff--after', value));
          for (const warning of (result.option_warnings || [])[index] || []) option.append(warn(warning));
          const actions = element('div', 'reply__actions');
          const apply = button('Aplicar', () => {
            if (collect()[result.field] !== snapshot[result.field]) {
              if (!options.querySelector('.notice')) options.prepend(element('p', 'notice', 'Esta sección cambió desde la consulta. Copia la sugerencia o pide una nueva para no sobrescribir tu edición.'));
              options.querySelectorAll('.option .btn--apply').forEach(node => { node.disabled = true; });
              return;
            }
            const field = form.querySelector(`textarea[data-key="${result.field}"]`);
            field.value = value;
            fit(field);
            refresh();
            options.replaceChildren(element('p', 'reply__done', 'Aplicada. Guarda los cambios para conservarla.'));
            setAssistant(false);
            field.scrollIntoView({block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
            field.focus({preventScroll: true});
          }, 'btn btn--small btn--apply');
          const copy = button('Copiar', async () => {
            try { await navigator.clipboard.writeText(value); copy.textContent = 'Copiado'; }
            catch { copy.textContent = 'Copia el texto de arriba'; }
            setTimeout(() => { copy.textContent = 'Copiar'; }, 1400);
          }, 'btn btn--quiet btn--small');
          actions.append(apply, copy);
          option.append(actions);
          options.append(option);
        });
        options.append(button('Descartar', () => options.replaceChildren(element('p', 'reply__done', 'Sugerencia descartada.')), 'btn btn--quiet btn--small'));
        row.append(options);
      }
      if (result.kind === 'articles') {
        for (const article of result.articles) {
          const card = element('div', 'result');
          card.append(element('p', 'meta', `${article.medio}${article.fecha ? ' · ' + panamaDate(article.fecha) : ''}`), element('p', 'result__title', article.titulo), element('p', 'result__passage', article.passage));
          const actions = element('div', 'reply__actions');
          actions.append(button('Ver fuente', () => openSource(article.id_evidencia)));
          const add = button(sources.includes(article.id_evidencia) ? 'Ya está en la ficha' : 'Añadir a la ficha', () => {
            if (!sources.includes(article.id_evidencia)) {
              sources.push(article.id_evidencia);
              const draft = collect();
              draft.fuentes_y_verificaciones.push(`Revisar fuente añadida: ${article.titulo}`);
              renderList('fuentes_y_verificaciones', draft.fuentes_y_verificaciones);
              renderSources();
              refresh();
            }
            add.disabled = true;
            add.textContent = 'Añadida · sin guardar';
          }, 'btn btn--quiet btn--small');
          add.disabled = sources.includes(article.id_evidencia);
          actions.append(add);
          card.append(actions);
          row.append(card);
        }
      }
      if (result.kind === 'contradiction') {
        for (const conflict of result.contradictions) {
          row.append(element('p', 'reply__h', conflict.descripcion));
          for (const version of conflict.versiones) row.append(button(`${version.valor} · ${version.alcance}`, () => openSource(version.id_evidencia), 'link'));
        }
      }
      citations(row, result.citations);
    }
    const askButton = askForm.querySelector('button');
    let pausedPrompts = [];
    function setBusy(busy) {
      if (busy) {
        pausedPrompts = [...assistant.querySelectorAll('.prompt:not(:disabled)')];
        pausedPrompts.forEach(node => { node.disabled = true; });
      } else pausedPrompts.forEach(node => { node.disabled = false; });
      askButton.disabled = busy || !input.value.trim();
      if (busy) assistant.setAttribute('aria-busy', 'true'); else assistant.removeAttribute('aria-busy');
    }
    function scrollToLatest() {
      const scroller = assistant.querySelector('.assistant__scroll');
      scroller.scrollTo({top: scroller.scrollHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    }
    async function ask(question, action = 'ask', field = action === 'rewrite' ? chosenField() : null) {
      if (asking || !question.trim()) return;
      asking = true;
      setBusy(true);
      showPrompts(false);
      const snapshot = collect();
      const row = element('li', 'reply');
      row.append(element('p', 'reply__q', question));
      const pending = element('p', 'reply__state', pendingLabels[action] || 'Buscando evidencia…');
      row.append(pending);
      replies.append(row);
      scrollToLatest();
      try {
        const result = await request(`${api}/assistant`, {method: 'POST', body: JSON.stringify({question, action, field, draft: snapshot, source_ids: sources.slice()})});
        pending.remove();
        renderReply(row, result, snapshot);
        scrollToLatest();
      } catch (error) {
        if (error.name !== 'AbortError') {
          pending.textContent = error.message;
          pending.setAttribute('role', 'alert');
          row.append(button('Reintentar', () => { row.remove(); ask(question, action, field); }));
        }
      } finally {
        asking = false;
        setBusy(false);
      }
    }

    document.addEventListener('click', event => {
      const link = event.target.closest('a[href]');
      if (!link || link.target === '_blank' || link.getAttribute('href').startsWith('/evidence/')) return;
      if (dirty()) {
        event.preventDefault();
        event.stopPropagation();
        notify('Guarda o descarta los cambios antes de cambiar de pantalla.', true);
      }
    }, {capture: true, signal: abort.signal});
    document.addEventListener('htmx:beforeRequest', event => {
      if (event.detail.requestConfig?.verb === 'get' && dirty()) {
        event.preventDefault();
        notify('Guarda o descarta los cambios antes de cambiar de pantalla.', true);
      }
    }, {signal: abort.signal});
    window.addEventListener('beforeunload', event => {
      if (dirty()) { event.preventDefault(); event.returnValue = ''; }
    }, {signal: abort.signal});
    form.addEventListener('input', event => {
      if (event.target.matches('textarea')) { fit(event.target); event.target.removeAttribute('aria-invalid'); }
      if (!form.querySelector('[aria-invalid]')) notify('');
      refresh();
    }, {signal: abort.signal});
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (saving) return;
      const snapshot = collect();
      const snapshotSources = sources.slice();
      saving = true;
      refresh();
      notify('');
      try {
        const response = await request(`${api}/draft`, {method: 'PUT', body: JSON.stringify({draft: snapshot, source_ids: snapshotSources, expected_version: saved.version})});
        saved = response;
        showReviewState(response.review_state);
        renderSources();
        const warnings = budgetWarnings(snapshot);
        notify(`Cambios guardados. El borrador requiere una nueva revisión humana.${warnings.length ? ` Aviso: ${warnings.join('; ')}. Puedes corregirlo antes de la revisión.` : ''}`);
      } catch (error) {
        if (error.name === 'AbortError') return;
        if (error.status === 409) {
          try { showConflict(await request(`${api}/draft`)); } catch { notify(`${error.message} Copia tus cambios y recarga la página.`, true); }
        } else {
          notify(error.message, true);
          if (error.field) markInvalid(error);
        }
      }
      finally { saving = false; refresh(); }
    }, {signal: abort.signal});
    desk.addEventListener('click', async event => {
      const target = event.target.closest('button, a');
      if (!target) return;
      const evidenceLink = target.closest('a[href^="/evidence/"]');
      if (evidenceLink && root.contains(evidenceLink)) {
        event.preventDefault(); event.stopPropagation();
        openSource(decodeURIComponent(new URL(evidenceLink.href).pathname.slice('/evidence/'.length)));
        return;
      }
      if (target.dataset.source) return openSource(target.dataset.source);
      const edit = target.dataset.edit;
      if (edit === 'close-source') return closeSource();
      if (edit === 'overwrite') return resolveConflict(false);
      if (edit === 'adopt') return resolveConflict(true);
      if (edit === 'discard' && conflict) return resolveConflict(true);
      if (edit === 'discard') { clearInvalid(); sources = saved.source_ids.slice(); renderDraft(saved.draft); renderSources(); notify(''); replies.replaceChildren(); showPrompts(true); }
      if (edit === 'add') {
        const key = target.dataset.key;
        const draft = collect();
        const maximum = key === 'preguntas' ? 50 : 100;
        if (draft[key].length >= maximum) return notify(`Puedes añadir hasta ${maximum} elementos.`, true);
        draft[key].push(''); renderList(key, draft[key]); refresh();
        root.querySelector(`[data-list="${key}"]`).lastElementChild.querySelector('textarea').focus();
      }
      if (edit === 'remove') {
        const list = target.closest('[data-list]');
        const index = [...list.children].indexOf(target.closest('li'));
        const draft = collect(); draft[list.dataset.list].splice(index, 1); renderList(list.dataset.list, draft[list.dataset.list]); refresh();
        (list.children[Math.min(index, list.children.length - 1)]?.querySelector('textarea') || root.querySelector(`[data-edit="add"][data-key="${list.dataset.list}"]`)).focus({preventScroll: true});
      }
      if (edit === 'copy') {
        try { await navigator.clipboard.writeText(collect()[target.dataset.key]); target.textContent = 'Copiado'; }
        catch {
          const field = form.querySelector(`textarea[data-key="${target.dataset.key}"]`);
          field.focus();
          field.select();
          target.textContent = 'Selecciona y copia';
        }
        setTimeout(() => { target.textContent = 'Copiar'; }, 1400);
      }
      const action = target.dataset.assist;
      if (action === 'open') { root.classList.remove('cn-closed'); setAssistant(true); }
      if (action === 'close') { root.classList.add('cn-closed'); setAssistant(false); }
      if (action === 'ask') ask(target.textContent, target.dataset.action);
      if (action === 'scope') { setScope(target.dataset.cnField); root.classList.remove('cn-closed'); setAssistant(true); input.focus({preventScroll: true}); }
    }, {capture: true, signal: abort.signal});
    input.addEventListener('input', () => { askButton.disabled = asking || !input.value.trim(); }, {signal: abort.signal});
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); askForm.requestSubmit(); }
    }, {signal: abort.signal});
    scope.addEventListener('change', () => setScope(scope.value), {signal: abort.signal});
    askForm.addEventListener('submit', event => {
      event.preventDefault();
      if (asking || !input.value.trim()) return;
      const question = input.value.trim();
      ask(question, requestAction(question, chosenField()));
      input.value = '';
    }, {signal: abort.signal});
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      if (!source.hidden) closeSource();
      else if (assistant.classList.contains('is-open')) setAssistant(false);
    }, {signal: abort.signal});
    form.querySelectorAll('textarea').forEach(fit);
    refresh();
    setScope('todo');
    return {root, dispose: () => { abort.abort(); assistant.remove(); source.remove(); toggle.remove(); }};
  }
  function sync() {
    const root = document.querySelector('[data-editor]');
    if (current?.root === root) return;
    current?.dispose();
    current = root ? mount(root) : null;
  }
  new MutationObserver(sync).observe(document.body, {childList: true, subtree: true});
  sync();
})();
