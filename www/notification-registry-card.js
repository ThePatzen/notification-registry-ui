const SEVERITIES = ["info", "hinweis", "warnung", "kritisch"];
const TARGET_GROUPS = ["alle", "david", "isabella", "anwesende"];
const CHANNELS = ["mobil", "persistent", "durchsage", "durchsage_alle"];
const KEY_PATTERN = /^[a-z0-9_]+::[a-z0-9_]+$/;

const labels = {
  info: "Info",
  hinweis: "Hinweis",
  warnung: "Warnung",
  kritisch: "Kritisch",
  alle: "Alle",
  david: "David",
  isabella: "Isabella",
  anwesende: "Anwesende",
  mobil: "Mobil",
  persistent: "Persistent",
  durchsage: "Durchsage",
  durchsage_alle: "Durchsage (alle)",
};

const css = `
  :host { display: block; color: var(--primary-text-color, #202124); }
  * { box-sizing: border-box; }
  .card { border: 1px solid var(--divider-color, #ddd); border-radius: 12px; background: var(--card-background-color, #fff); padding: 16px; }
  .toolbar { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin-bottom: 14px; }
  .toolbar label, .field { display: flex; flex-direction: column; gap: 4px; min-width: 150px; flex: 1; }
  label span, .field-label { font-size: .8rem; color: var(--secondary-text-color, #5f6368); }
  input, select, textarea, button { font: inherit; }
  input, select, textarea { border: 1px solid var(--input-ink-color, #777); border-radius: 6px; padding: 7px 8px; color: inherit; background: var(--input-fill-color, transparent); }
  textarea { min-height: 82px; resize: vertical; }
  button { border: 0; border-radius: 6px; padding: 8px 12px; cursor: pointer; color: var(--text-primary-color, inherit); background: var(--primary-color, #1976d2); }
  button.secondary { background: var(--secondary-background-color, #eee); }
  button.danger { background: var(--error-color, #c62828); color: white; }
  button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid var(--focus-color, #1565c0); outline-offset: 2px; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; min-width: 680px; }
  th, td { text-align: left; vertical-align: top; padding: 10px 8px; border-bottom: 1px solid var(--divider-color, #ddd); }
  th { font-size: .8rem; color: var(--secondary-text-color, #5f6368); }
  .actions { display: flex; gap: 4px; flex-wrap: wrap; }
  .actions button { padding: 5px 7px; background: var(--secondary-background-color, #eee); }
  .entry-key { font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
  .tag { color: var(--secondary-text-color, #5f6368); }
  .mobile-list { display: none; }
  .mobile-entry { border: 1px solid var(--divider-color, #ddd); border-radius: 8px; padding: 12px; margin-bottom: 10px; }
  .mobile-entry dl { display: grid; grid-template-columns: max-content 1fr; gap: 5px 10px; margin: 10px 0; }
  .mobile-entry dt { color: var(--secondary-text-color, #5f6368); font-size: .8rem; }
  dialog { color: inherit; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #aaa); border-radius: 10px; width: min(620px, calc(100vw - 28px)); max-height: calc(100vh - 28px); overflow: auto; }
  dialog::backdrop { background: rgb(0 0 0 / 45%); }
  dialog form { display: grid; gap: 12px; }
  .channel-list { display: flex; flex-wrap: wrap; gap: 10px; }
  .channel-list label { display: inline-flex; align-items: center; gap: 5px; }
  .dialog-actions { display: flex; justify-content: end; gap: 8px; }
  [role="alert"] { color: var(--error-color, #c62828); margin: 0; }
  .status { color: var(--secondary-text-color, #5f6368); min-height: 1.3em; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  @media (max-width: 699px) {
    .desktop-list { display: none; }
    .mobile-list { display: block; }
    .card { padding: 12px; }
    .toolbar > * { min-width: min(100%, 220px); }
  }
`;

function display(value) {
  return labels[value] || value || "—";
}

function errorDetails(error) {
  const detail = error?.error || error?.response?.error || error || {};
  const code = detail.code || "unknown";
  const messages = {
    revision_conflict: "Revision conflict: Der Eintrag wurde inzwischen auf dem Server geändert.",
    key_in_use: "Der Eintrag wird noch verwendet und kann nicht gelöscht werden.",
    references_require_confirmation: "Referenzen müssen vor dem Umbenennen bestätigt werden.",
  };
  return {
    code,
    message: messages[code] || detail.message || error?.message || "Die Änderung konnte nicht gespeichert werden.",
    issues: detail.issues || [],
    current: detail.current,
    references: detail.references || [],
  };
}

export class NotificationRegistryCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._entries = [];
    this._dataRevision = null;
    this._schemaVersion = null;
    this._search = "";
    this._severity = "";
    this._error = null;
    this._editorEntry = null;
    this._loading = false;
    this._loadedForHass = null;
    this._updateComplete = Promise.resolve();
    this._renderQueued = false;
  }

  set hass(value) {
    this._hass = value;
    if (value && value !== this._loadedForHass) {
      this._loadedForHass = value;
      this._loadEntries();
    }
  }

  get hass() {
    return this._hass;
  }

  setConfig(config) {
    this._config = config || {};
    this.requestUpdate();
  }

  connectedCallback() {
    this.requestUpdate();
  }

  getCardSize() {
    return 6;
  }

  get updateComplete() {
    return this._updateComplete;
  }

  requestUpdate() {
    if (this._renderQueued) return this._updateComplete;
    this._renderQueued = true;
    let resolve;
    this._updateComplete = new Promise((done) => { resolve = done; });
    queueMicrotask(() => {
      this._renderQueued = false;
      this._render();
      resolve();
    });
    return this._updateComplete;
  }

  async _loadEntries() {
    if (!this._hass?.callWS) return;
    this._loading = true;
    this._error = null;
    this.requestUpdate();
    try {
      const response = await this._hass.callWS({ type: "notification_registry/list" });
      const result = response?.result || response || {};
      this._entries = Array.isArray(result.entries) ? result.entries.map((entry) => ({ ...entry })) : [];
      this._dataRevision = result.data_revision ?? null;
      this._schemaVersion = result.schema_version ?? null;
    } catch (error) {
      this._error = errorDetails(error);
    } finally {
      this._loading = false;
      this.requestUpdate();
    }
  }

  _render() {
    const filtered = this._filteredEntries();
    const title = this._config?.title || "Benachrichtigungs-Registry";
    this.shadowRoot.innerHTML = `<style>${css}</style>
      <section class="card" aria-labelledby="registry-title">
        <h2 id="registry-title">${title}</h2>
        <div class="toolbar" role="toolbar" aria-label="Registry-Werkzeuge">
          <label><span>Suche</span><input name="search" type="search" placeholder="Key, Titel oder Text" value="${this._escape(this._search)}"></label>
          <label><span>Schweregrad</span><select name="severity" aria-label="Schweregrad filtern"><option value="">Alle Schweregrade</option>${SEVERITIES.map((value) => `<option value="${value}" ${this._severity === value ? "selected" : ""}>${display(value)}</option>`).join("")}</select></label>
          <button type="button" data-action="create">Neue Meldung</button>
        </div>
        <p class="status" aria-live="polite">${this._loading ? "Lade Meldungen …" : `${filtered.length} von ${this._entries.length} Einträgen`}</p>
        ${this._errorMarkup()}
        <div class="desktop-list table-wrap">
          <table>
            <caption class="sr-only">Benachrichtigungs-Registry</caption>
            <thead><tr><th scope="col">Key</th><th scope="col">Titel</th><th scope="col">Schweregrad</th><th scope="col">Zielgruppe</th><th scope="col">Kanäle</th><th scope="col">Tag</th><th scope="col">Aktionen</th></tr></thead>
            <tbody>${filtered.map((entry) => this._tableRow(entry)).join("")}</tbody>
          </table>
        </div>
        <div class="mobile-list" aria-label="Einträge">${filtered.map((entry) => this._mobileEntry(entry)).join("") || "<p>Keine Einträge gefunden.</p>"}</div>
        ${this._editorEntry ? this._editorTemplate(this._editorEntry) : ""}
      </section>`;
    this._bindEvents();
  }

  _filteredEntries() {
    const term = this._search.trim().toLocaleLowerCase();
    return this._entries.filter((entry) => {
      if (this._severity && entry.schweregrad !== this._severity) return false;
      if (!term) return true;
      return [entry.key, entry.titel, entry.text].some((value) => String(value || "").toLocaleLowerCase().includes(term));
    });
  }

  _tableRow(entry) {
    return `<tr data-entry-key="${this._escape(entry.key)}"><td class="entry-key">${this._escape(entry.key)}</td><td>${this._escape(entry.titel)}</td><td>${display(entry.schweregrad)}</td><td>${display(entry.zielgruppe)}</td><td>${(entry.kanaele || []).map(display).join(", ")}</td><td class="tag">${this._escape(entry.tag || "—")}</td><td>${this._actions(entry)}</td></tr>`;
  }

  _mobileEntry(entry) {
    return `<article class="mobile-entry" data-mobile-entry data-entry-key="${this._escape(entry.key)}"><strong class="entry-key">${this._escape(entry.key)}</strong><dl><dt>Titel</dt><dd>${this._escape(entry.titel)}</dd><dt>Text</dt><dd>${this._escape(entry.text)}</dd><dt>Schweregrad</dt><dd>${display(entry.schweregrad)}</dd><dt>Zielgruppe</dt><dd>${display(entry.zielgruppe)}</dd><dt>Kanäle</dt><dd>${(entry.kanaele || []).map(display).join(", ")}</dd><dt>Tag</dt><dd>${this._escape(entry.tag || "—")}</dd></dl>${this._actions(entry)}</article>`;
  }

  _actions(entry) {
    const key = this._escape(entry.key);
    return `<div class="actions" aria-label="Aktionen für ${key}"><button type="button" data-action="edit" data-key="${key}">Bearbeiten</button><button type="button" data-action="duplicate" data-key="${key}">Duplizieren</button><button type="button" data-action="rename" data-key="${key}">Umbenennen</button><button type="button" class="danger" data-action="delete" data-key="${key}">Löschen</button></div>`;
  }

  _editorTemplate(entry) {
    const editing = Boolean(entry.revision);
    const checked = new Set(entry.kanaele || []);
    const issue = (field) => this._fieldIssue(field);
    const field = (name, value, label, type = "text") => `<label class="field"><span>${label}</span>${type === "textarea" ? `<textarea name="${name}" ${name === "key" && editing ? "readonly" : ""} aria-invalid="${issue(name) ? "true" : "false"}">${this._escape(value || "")}</textarea>` : `<input name="${name}" type="${type}" value="${this._escape(value || "")}" ${name === "key" && editing ? "readonly" : ""} aria-invalid="${issue(name) ? "true" : "false"}>`}${issue(name) ? `<small role="alert">${this._escape(issue(name))}</small>` : ""}</label>`;
    return `<dialog open aria-labelledby="editor-title"><form method="dialog" novalidate><h3 id="editor-title">${editing ? "Meldung bearbeiten" : "Neue Meldung"}</h3>${this._errorMarkup()}${field("key", entry.key, "Key")}${field("titel", entry.titel, "Titel")}${field("text", entry.text, "Text", "textarea")}<label class="field"><span>Schweregrad</span><select name="schweregrad">${SEVERITIES.map((value) => `<option value="${value}" ${entry.schweregrad === value ? "selected" : ""}>${display(value)}</option>`).join("")}</select></label><label class="field"><span>Zielgruppe</span><select name="zielgruppe">${TARGET_GROUPS.map((value) => `<option value="${value}" ${entry.zielgruppe === value ? "selected" : ""}>${display(value)}</option>`).join("")}</select></label><fieldset><legend>Kanäle</legend><div class="channel-list">${CHANNELS.map((value) => `<label><input type="checkbox" name="kanaele" value="${value}" ${checked.has(value) ? "checked" : ""}>${display(value)}</label>`).join("")}</div>${this._fieldIssue("kanaele") ? `<small role="alert">${this._escape(this._fieldIssue("kanaele"))}</small>` : ""}</fieldset>${field("tag", entry.tag || "", "Tag")}<div class="dialog-actions"><button type="button" class="secondary" data-action="cancel-editor">Abbrechen</button><button type="submit">Speichern</button></div></form></dialog>`;
  }

  _bindEvents() {
    const search = this.shadowRoot.querySelector("input[name=search]");
    const severity = this.shadowRoot.querySelector("select[name=severity]");
    search?.addEventListener("input", (event) => { this._search = event.target.value; this.requestUpdate(); });
    severity?.addEventListener("change", (event) => { this._severity = event.target.value; this.requestUpdate(); });
    this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => this._handleAction(button.dataset.action, button.dataset.key)));
    this.shadowRoot.querySelector("form")?.addEventListener("submit", (event) => this._submitEditor(event));
    this.shadowRoot.querySelector("[data-action=cancel-editor]")?.addEventListener("click", () => this.closeEditor());
    this.shadowRoot.querySelector("dialog")?.addEventListener("cancel", (event) => { event.preventDefault(); this.closeEditor(); });
  }

  _handleAction(action, key) {
    if (action === "create") return this.openEditor();
    const entry = this._entries.find((candidate) => candidate.key === key);
    if (!entry) return;
    if (action === "edit") return this.openEditor(entry);
    if (action === "duplicate") return this._duplicate(entry);
    if (action === "rename") return this._rename(entry);
    if (action === "delete") return this._delete(entry);
  }

  openEditor(entry = null) {
    this._editorEntry = entry ? { ...entry, kanaele: [...(entry.kanaele || [])] } : { key: "", titel: "", text: "", schweregrad: "info", zielgruppe: "alle", kanaele: ["persistent"], tag: "" };
    this._error = null;
    this._formIssues = {};
    this.requestUpdate();
  }

  closeEditor() {
    this._editorEntry = null;
    this._error = null;
    this._formIssues = {};
    this.requestUpdate();
  }

  _fieldIssue(field) {
    return this._formIssues?.[field] || "";
  }

  _errorMarkup() {
    if (!this._error) return "";
    const references = this._error.references || [];
    return `<div role="alert"><p>${this._escape(this._error.message)}</p>${references.length ? `<ul data-error-references>${references.map((reference) => `<li>${this._escape(reference.friendly_name || "Referenz")} ${reference.entity_id ? `<code>${this._escape(reference.entity_id)}</code>` : ""} <span class="tag">(${this._escape(reference.path || "")})</span></li>`).join("")}</ul>` : ""}</div>`;
  }

  _validateForm(form) {
    const value = Object.fromEntries(new FormData(form).entries());
    value.kanaele = [...form.querySelectorAll('input[name="kanaele"]:checked')].map((input) => input.value);
    const issues = {};
    if (!value.key?.trim()) issues.key = "Key darf nicht leer sein.";
    else if (!KEY_PATTERN.test(value.key.trim())) issues.key = "Key muss bereich::name entsprechen.";
    if (!value.titel?.trim()) issues.titel = "Titel darf nicht leer sein.";
    if (!value.text?.trim()) issues.text = "Text darf nicht leer sein.";
    if (!value.kanaele.length) issues.kanaele = "Mindestens ein Kanal ist erforderlich.";
    if (value.schweregrad === "kritisch" && !(value.kanaele.includes("mobil") && value.kanaele.includes("persistent"))) issues.kanaele = "Kritische Einträge benötigen mobil und persistent.";
    return { value: { ...value, key: value.key?.trim(), titel: value.titel?.trim(), text: value.text?.trim(), tag: value.tag?.trim() || null }, issues };
  }

  async _submitEditor(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const { value, issues } = this._validateForm(form);
    this._formIssues = issues;
    if (Object.keys(issues).length) { this.requestUpdate(); return; }
    const editing = Boolean(this._editorEntry?.revision);
    const oldEntry = this._editorEntry;
    const message = editing
      ? { type: "notification_registry/update", key: oldEntry.key, expected_revision: oldEntry.revision, entry: { ...oldEntry, ...value, revision: oldEntry.revision } }
      : { type: "notification_registry/create", entry: value };
    try {
      const response = await this._hass.callWS(message);
      const result = response?.result || response || {};
      if (result.entry) this._replaceEntry(result.entry);
      if (result.data_revision !== undefined) this._dataRevision = result.data_revision;
      this._error = null;
      this.closeEditor();
    } catch (error) {
      const details = errorDetails(error);
      this._error = details;
      if (details.code === "revision_conflict" && details.current) {
        this._replaceEntry(details.current);
        this._editorEntry = { ...details.current, kanaele: [...(details.current.kanaele || [])] };
      }
      for (const issue of details.issues) this._formIssues[issue.field] = issue.message;
      this.requestUpdate();
    }
  }

  _replaceEntry(entry) {
    const index = this._entries.findIndex((candidate) => candidate.key === entry.key);
    if (index < 0) this._entries = [...this._entries, { ...entry }];
    else this._entries = this._entries.map((candidate, position) => position === index ? { ...entry } : candidate);
    this.requestUpdate();
  }

  async _duplicate(entry) {
    const newKey = window.prompt("Neuer Key", `${entry.key}_kopie`);
    if (!newKey) return;
    try {
      const response = await this._hass.callWS({ type: "notification_registry/duplicate", source_key: entry.key, new_key: newKey });
      const result = response?.result || response || {};
      if (result.entry) this._replaceEntry(result.entry);
      if (result.data_revision !== undefined) this._dataRevision = result.data_revision;
      this.requestUpdate();
    } catch (error) { this._error = errorDetails(error); this.requestUpdate(); }
  }

  async _rename(entry) {
    const newKey = window.prompt("Neuer Key", entry.key);
    if (!newKey || newKey === entry.key) return;
    let references;
    try {
      const response = await this._hass.callWS({ type: "notification_registry/references", key: entry.key });
      references = (response?.result || response || {}).references || [];
    } catch (error) { this._error = errorDetails(error); this.requestUpdate(); return; }
    const confirmed = !references.length || window.confirm(`Dieser Key wird ${references.length} Mal verwendet. Trotzdem umbenennen?`);
    if (!confirmed) return;
    try {
      const response = await this._hass.callWS({ type: "notification_registry/rename", key: entry.key, new_key: newKey, expected_revision: entry.revision, ...(references.length ? { confirm_references: true } : {}) });
      const result = response?.result || response || {};
      this._entries = this._entries.filter((candidate) => candidate.key !== entry.key);
      if (result.entry) this._replaceEntry(result.entry);
      if (result.data_revision !== undefined) this._dataRevision = result.data_revision;
      this.requestUpdate();
    } catch (error) { this._error = errorDetails(error); this.requestUpdate(); }
  }

  async _delete(entry) {
    if (!window.confirm(`Meldung ${entry.key} wirklich löschen?`)) return;
    try {
      const response = await this._hass.callWS({ type: "notification_registry/delete", key: entry.key, expected_revision: entry.revision });
      const result = response?.result || response || {};
      if (result.deleted) this._entries = this._entries.filter((candidate) => candidate.key !== entry.key);
      if (result.data_revision !== undefined) this._dataRevision = result.data_revision;
      this.requestUpdate();
    } catch (error) { this._error = errorDetails(error); this.requestUpdate(); }
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
  }
}

if (!customElements.get("notification-registry-card")) customElements.define("notification-registry-card", NotificationRegistryCard);
