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
});
