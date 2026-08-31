import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../www/notification-registry-card.js";

const criticalEntry = {
  key: "technikraum::wasseralarm",
  titel: "Wasseralarm",
  text: "Wasser bei {geraet}",
  schweregrad: "kritisch",
  zielgruppe: "alle",
  kanaele: ["mobil", "persistent"],
  tag: "wasseralarm",
  revision: 3,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-02T00:00:00+00:00",
};

const infoEntry = {
  ...criticalEntry,
  key: "system::info",
  titel: "Systeminfo",
  text: "Alles gut",
  schweregrad: "info",
  kanaele: ["persistent"],
  revision: 1,
};

function fakeHass(entries = [criticalEntry]) {
  return {
    callWS: vi.fn().mockResolvedValue({
      entries,
      data_revision: 3,
      schema_version: 1,
    }),
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function makeCard(entries) {
  const card = document.createElement("notification-registry-card");
  card.hass = fakeHass(entries);
  document.body.append(card);
  return card;
}

async function settle(card) {
  await card.updateComplete;
  await Promise.resolve();
}

describe("notification-registry-card", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    HTMLDialogElement.prototype.showModal = vi.fn();
    HTMLDialogElement.prototype.close = vi.fn();
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      media: "(max-width: 699px)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders confirmed entries as a semantic table and mobile cards", async () => {
    const card = makeCard([criticalEntry]);
    await settle(card);

    expect(card.shadowRoot.querySelector("table")).not.toBeNull();
    expect(card.shadowRoot.querySelector("table thead th").textContent).toContain("Key");
    expect(card.shadowRoot.querySelector("[data-mobile-entry]")).not.toBeNull();
    expect(card.shadowRoot.querySelector("[data-mobile-entry]").textContent).toContain(
      criticalEntry.key,
    );
  });

  it("loads entries through the exact list WebSocket command", async () => {
    const hass = fakeHass([criticalEntry]);
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);

    expect(hass.callWS).toHaveBeenCalledWith({ type: "notification_registry/list" });
  });

  it("does not reload when Home Assistant assigns a routine new object identity", async () => {
    const hass = fakeHass([criticalEntry]);
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.hass = { ...hass, states: {} };
    await settle(card);

    expect(hass.callWS).toHaveBeenCalledTimes(1);
  });

  it("ignores stale list responses after a newer Home Assistant connection load", async () => {
    const first = deferred();
    const second = deferred();
    const firstHass = { connection: {}, callWS: vi.fn().mockReturnValue(first.promise) };
    const secondHass = { connection: {}, callWS: vi.fn().mockReturnValue(second.promise) };
    const card = document.createElement("notification-registry-card");
    card.hass = firstHass;
    document.body.append(card);
    await card.updateComplete;
    card.hass = secondHass;
    second.resolve({ entries: [infoEntry], data_revision: 2, schema_version: 1 });
    await Promise.resolve();
    await settle(card);
    first.resolve({ entries: [criticalEntry], data_revision: 1, schema_version: 1 });
    await Promise.resolve();
    await settle(card);

    expect(card.shadowRoot.textContent).toContain(infoEntry.key);
    expect(card.shadowRoot.textContent).not.toContain(criticalEntry.key);
  });

  it("ignores a stale list failure after a newer connection load succeeds", async () => {
    const first = deferred();
    const second = deferred();
    const firstHass = { connection: {}, callWS: vi.fn().mockReturnValue(first.promise) };
    const secondHass = { connection: {}, callWS: vi.fn().mockReturnValue(second.promise) };
    const card = document.createElement("notification-registry-card");
    card.hass = firstHass;
    document.body.append(card);
    await card.updateComplete;
    card.hass = secondHass;
    second.resolve({ entries: [infoEntry], data_revision: 2, schema_version: 1 });
    await Promise.resolve();
    await settle(card);
    first.reject(new Error("stale connection failed"));
    await Promise.resolve();
    await settle(card);

    expect(card.shadowRoot.textContent).toContain(infoEntry.key);
    expect(card.shadowRoot.querySelector("[role=alert]")).toBeNull();
    expect(card._error).toBeNull();
  });

  it("does not let an older list response overwrite a confirmed CRUD entry", async () => {
    const list = deferred();
    const hass = { callWS: vi.fn().mockReturnValue(list.promise) };
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await card.updateComplete;
    const created = { ...infoEntry, key: "system::new" };
    card._replaceEntry(created);
    await settle(card);
    list.resolve({ entries: [criticalEntry], data_revision: 1, schema_version: 1 });
    await Promise.resolve();
    await settle(card);

    expect(card.shadowRoot.textContent).toContain(created.key);
    expect(card.shadowRoot.textContent).not.toContain(criticalEntry.key);
  });

  it("filters locally by search text and severity", async () => {
    const card = makeCard([criticalEntry, infoEntry]);
    await settle(card);

    const search = card.shadowRoot.querySelector("input[name=search]");
    search.value = "system";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    const filter = card.shadowRoot.querySelector("select[name=severity]");
    filter.value = "info";
    filter.dispatchEvent(new Event("change", { bubbles: true }));
    await settle(card);

    expect(card.shadowRoot.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(card.shadowRoot.querySelector("tbody tr").textContent).toContain("system::info");
  });

  it("keeps updateComplete deterministic across render cycles", async () => {
    const card = makeCard([criticalEntry]);
    const first = card.updateComplete;
    await first;
    card.requestUpdate();
    const second = card.updateComplete;
    expect(second).not.toBe(first);
    await second;
    expect(card.updateComplete).toBe(second);
  });

  it("validates critical channels before sending create", async () => {
    const hass = fakeHass([]);
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.openEditor();
    await settle(card);
    const form = card.shadowRoot.querySelector("form");
    form.elements.key.value = "test::critical";
    form.elements.titel.value = "Alarm";
    form.elements.text.value = "Alarm";
    form.elements.schweregrad.value = "kritisch";
    form.elements.zielgruppe.value = "alle";
    form.querySelector('input[value="persistent"]').checked = true;
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
    await settle(card);

    expect(hass.callWS).toHaveBeenCalledTimes(1);
    expect(card.shadowRoot.querySelector("[role=alert]").textContent).toContain("mobil");
  });

  it("creates and replaces local state with the confirmed server entry", async () => {
    const hass = fakeHass([]);
    const created = { ...criticalEntry, key: "test::new", revision: 1 };
    hass.callWS
      .mockResolvedValueOnce({ entries: [], data_revision: 3, schema_version: 1 })
      .mockResolvedValueOnce({ entry: created, data_revision: 4 });
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.openEditor();
    await settle(card);
    const form = card.shadowRoot.querySelector("form");
    for (const [name, value] of Object.entries({
      key: created.key,
      titel: created.titel,
      text: created.text,
      schweregrad: created.schweregrad,
      zielgruppe: created.zielgruppe,
      tag: created.tag,
    })) form.elements[name].value = value;
    for (const channel of created.kanaele) form.querySelector(`input[value="${channel}"]`).checked = true;
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
    await settle(card);

    expect(hass.callWS).toHaveBeenLastCalledWith({
      type: "notification_registry/create",
      entry: expect.objectContaining({ key: created.key }),
    });
    expect(card.shadowRoot.textContent).toContain(created.key);
  });

  it("shows revision conflict with the server-confirmed current entry", async () => {
    const hass = fakeHass([criticalEntry]);
    const current = { ...criticalEntry, titel: "Server-Version", revision: 4 };
    hass.callWS.mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 });
    hass.callWS.mockRejectedValueOnce(Object.assign(new Error("conflict"), {
      code: "revision_conflict",
      current,
    }));
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.openEditor(criticalEntry);
    await settle(card);
    const form = card.shadowRoot.querySelector("form");
    form.elements.titel.value = "Lokale-Version";
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
    await settle(card);

    expect(card.shadowRoot.querySelector("[role=alert]").textContent).toContain("Revision");
    expect(card.shadowRoot.textContent).toContain("Server-Version");
  });

  it("checks references and sends explicit confirmation before rename", async () => {
    const hass = fakeHass([criticalEntry]);
    const renamed = { ...criticalEntry, key: "technikraum::wasserwarnung", revision: 2 };
    hass.callWS
      .mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 })
      .mockResolvedValueOnce({ references: [{ entity_id: "automation.water", path: "action[0]" }] })
      .mockResolvedValueOnce({ entry: renamed, data_revision: 4 });
    vi.stubGlobal("prompt", vi.fn().mockReturnValue(renamed.key));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);

    card.shadowRoot.querySelector('[data-action="rename"]').click();
    await settle(card);

    expect(hass.callWS).toHaveBeenNthCalledWith(2, {
      type: "notification_registry/references",
      key: criticalEntry.key,
    });
    expect(hass.callWS).toHaveBeenNthCalledWith(3, {
      type: "notification_registry/rename",
      key: criticalEntry.key,
      new_key: renamed.key,
      expected_revision: criticalEntry.revision,
      confirm_references: true,
    });
    expect(card.shadowRoot.textContent).toContain(renamed.key);
  });

  it("renders reference details when deletion is blocked", async () => {
    const hass = fakeHass([criticalEntry]);
    hass.callWS
      .mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 })
      .mockRejectedValueOnce(Object.assign(new Error("blocked"), {
        code: "key_in_use",
        references: [{ entity_id: "automation.water", friendly_name: "Water alarm", path: "action[0]" }],
      }));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.shadowRoot.querySelector('[data-action="delete"]').click();
    await settle(card);

    expect(card.shadowRoot.querySelector("[role=alert]").textContent).toContain("verwendet");
    expect(card.shadowRoot.textContent).toContain("automation.water");
  });

  it("closes the native editor dialog on Escape/cancel", async () => {
    const card = makeCard([]);
    await settle(card);
    card.openEditor();
    await settle(card);
    const dialog = card.shadowRoot.querySelector("dialog");
    dialog.dispatchEvent(new Event("cancel", { bubbles: true, cancelable: true }));
    await settle(card);

    expect(card.shadowRoot.querySelector("dialog")).toBeNull();
  });

  it("uses showModal and close, focuses the first field, and restores focus", async () => {
    const card = makeCard([criticalEntry]);
    await settle(card);
    const open = card.shadowRoot.querySelector('[data-action="edit"]');
    open.focus();
    card.openEditor(criticalEntry);
    await settle(card);
    const dialog = card.shadowRoot.querySelector("dialog");
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
    expect(card.shadowRoot.activeElement).toBe(card.shadowRoot.querySelector("input[name=key]"));
    card.closeEditor();
    await settle(card);
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(card.shadowRoot.activeElement?.dataset.action).toBe("edit");
    expect(card.shadowRoot.activeElement?.dataset.key).toBe(criticalEntry.key);
  });

  it("restores focus to the visible mobile opener on a mobile layout", async () => {
    const listeners = [];
    const media = { matches: true, media: "(max-width: 699px)", addEventListener: (_type, listener) => listeners.push(listener), removeEventListener: vi.fn() };
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(media));
    const card = makeCard([criticalEntry]);
    await settle(card);
    const mobileOpen = card.shadowRoot.querySelector('.mobile-entry [data-action="edit"]');
    card.openEditor(criticalEntry);
    await settle(card);
    card.closeEditor();
    await settle(card);

    expect(card.shadowRoot.activeElement).toBe(card.shadowRoot.querySelector('.mobile-entry [data-action="edit"]'));
    expect(card.shadowRoot.activeElement?.closest(".desktop-list")).toBeNull();
    expect(listeners).toHaveLength(1);
  });

  it("marks the channel checkbox group as required without native checkbox requiredness", async () => {
    const card = makeCard([]);
    await settle(card);
    card.openEditor();
    await settle(card);

    const group = card.shadowRoot.querySelector("fieldset");
    expect(group.getAttribute("aria-required")).toBe("true");
    expect([...group.querySelectorAll('input[name="kanaele"]')].every((input) => !input.required)).toBe(true);
  });

  it("escapes configuration titles and unknown dynamic values", async () => {
    const hostile = { ...criticalEntry, key: "xss::key", schweregrad: "<img src=x onerror=alert(1)>", titel: "<script>alert(1)</script>" };
    const card = document.createElement("notification-registry-card");
    card.setConfig({ title: "<img src=x onerror=alert(1)>" });
    card.hass = fakeHass([hostile]);
    document.body.append(card);
    await settle(card);

    expect(card.shadowRoot.querySelector("script")).toBeNull();
    expect(card.shadowRoot.querySelector("img")).toBeNull();
    expect(card.shadowRoot.textContent).toContain(hostile.titel);
  });

  it("updates an entry using its revision and server-confirmed response", async () => {
    const updated = { ...criticalEntry, titel: "Updated", revision: 4 };
    const hass = fakeHass([criticalEntry]);
    hass.callWS
      .mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 })
      .mockResolvedValueOnce({ entry: updated, data_revision: 4 });
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.openEditor(criticalEntry);
    await settle(card);
    const form = card.shadowRoot.querySelector("form");
    form.elements.titel.value = updated.titel;
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
    await settle(card);

    expect(hass.callWS).toHaveBeenLastCalledWith(expect.objectContaining({ type: "notification_registry/update", key: criticalEntry.key, expected_revision: criticalEntry.revision }));
    expect(card.shadowRoot.textContent).toContain(updated.titel);
  });

  it("duplicates an entry and deletes only after confirmation", async () => {
    const duplicate = { ...criticalEntry, key: "technikraum::kopie", revision: 1 };
    const hass = fakeHass([criticalEntry]);
    hass.callWS
      .mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 })
      .mockResolvedValueOnce({ entry: duplicate, data_revision: 4 })
      .mockResolvedValueOnce({ deleted: true, data_revision: 5 });
    vi.stubGlobal("prompt", vi.fn().mockReturnValue(duplicate.key));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.shadowRoot.querySelector('[data-action="duplicate"]').click();
    await settle(card);
    expect(card.shadowRoot.textContent).toContain(duplicate.key);
    card.shadowRoot.querySelector('[data-action="delete"][data-key="technikraum::wasseralarm"]').click();
    await settle(card);
    expect(hass.callWS).toHaveBeenLastCalledWith({ type: "notification_registry/delete", key: criticalEntry.key, expected_revision: criticalEntry.revision });
    expect(card.shadowRoot.textContent).not.toContain(criticalEntry.key);
  });

  it("shows required-field and invalid-channel validation without sending", async () => {
    const hass = fakeHass([]);
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.openEditor();
    await settle(card);
    const form = card.shadowRoot.querySelector("form");
    form.querySelector('input[value="persistent"]').checked = false;
    form.dispatchEvent(new SubmitEvent("submit", { bubbles: true, cancelable: true }));
    await settle(card);

    expect(hass.callWS).toHaveBeenCalledTimes(1);
    expect(card.shadowRoot.querySelector('input[name="key"]').getAttribute("aria-invalid")).toBe("true");
    expect(card.shadowRoot.querySelector("[role=alert]")).not.toBeNull();
  });

  it("refuses a referenced rename until the user confirms", async () => {
    const hass = fakeHass([criticalEntry]);
    hass.callWS.mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 }).mockResolvedValueOnce({ references: [{ entity_id: "automation.water" }] });
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("technikraum::new"));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.shadowRoot.querySelector('[data-action="rename"]').click();
    await settle(card);

    expect(hass.callWS).toHaveBeenCalledTimes(2);
    expect(card.shadowRoot.textContent).toContain(criticalEntry.key);
  });

  it("applies current entries from rename and delete revision conflicts", async () => {
    const renamedCurrent = { ...criticalEntry, titel: "Rename current", revision: 4 };
    const deletedCurrent = { ...criticalEntry, titel: "Delete current", revision: 5 };
    const hass = fakeHass([criticalEntry]);
    hass.callWS
      .mockResolvedValueOnce({ entries: [criticalEntry], data_revision: 3, schema_version: 1 })
      .mockResolvedValueOnce({ references: [] })
      .mockRejectedValueOnce(Object.assign(new Error("rename conflict"), { code: "revision_conflict", current: renamedCurrent }))
      .mockRejectedValueOnce(Object.assign(new Error("delete conflict"), { code: "revision_conflict", current: deletedCurrent }));
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("technikraum::new"));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const card = document.createElement("notification-registry-card");
    card.hass = hass;
    document.body.append(card);
    await settle(card);
    card.shadowRoot.querySelector('[data-action="rename"]').click();
    await settle(card);
    expect(card.shadowRoot.textContent).toContain(renamedCurrent.titel);
    card.shadowRoot.querySelector('[data-action="delete"]').click();
    await settle(card);
    expect(card.shadowRoot.textContent).toContain(deletedCurrent.titel);
  });

  it("switches visible layout semantics when matchMedia changes to 360px", async () => {
    const listeners = [];
    let width = 1280;
    const media = { get matches() { return width < 700; }, media: "(max-width: 699px)", addEventListener: (_type, listener) => listeners.push(listener), removeEventListener: vi.fn() };
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(media));
    const card = makeCard([criticalEntry]);
    await settle(card);
    expect(card.shadowRoot.querySelector(".desktop-list").hidden).toBe(false);
    expect(card.shadowRoot.querySelector(".mobile-list").hidden).toBe(true);
    width = 360;
    listeners.forEach((listener) => listener({ matches: true }));
    await settle(card);
    expect(card.shadowRoot.querySelector(".desktop-list").hidden).toBe(true);
    expect(card.shadowRoot.querySelector(".mobile-list").hidden).toBe(false);
  });
});
