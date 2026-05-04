import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadGallery() {
  vi.resetModules();
  document.body.innerHTML = `
    <button id="done-btn"></button>
    <div id="index-theme-controls"></div>
    <div id="gallery"></div>
  `;
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  window.__BUGSHOT_ENABLE_TEST_HOOKS__ = true;
  window.__BUGSHOT_UNITS__ = [];
  await import("../../static/gallery.ts");
  return window.__BUGSHOT_TEST__!;
}

describe("gallery region helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("normalizes pointer coordinates against the overlay bounds", async () => {
    const hooks = await loadGallery();
    const overlay = document.createElement("canvas");
    overlay.getBoundingClientRect = () => ({
      left: 10,
      top: 20,
      width: 200,
      height: 100,
      right: 210,
      bottom: 120,
      x: 10,
      y: 20,
      toJSON: () => ({}),
    });

    const point = hooks.pointFromEvent(
      { overlay },
      new MouseEvent("mousedown", { clientX: 60, clientY: 45 }),
    );

    expect(point).toEqual([0.25, 0.25]);
  });

  it("rejects too-small rectangle draws before they become comments", async () => {
    const hooks = await loadGallery();

    const region = hooks.buildCommittedRegion({
      type: "rect",
      origin: [0.1, 0.1],
      current: [0.101, 0.2],
    });

    expect(region).toBeNull();
  });

  it("commits a pending region when not replacing an existing comment", async () => {
    const hooks = await loadGallery();
    const input = document.createElement("input");
    input.id = "comment-input";
    document.body.appendChild(input);
    const state = {
      activeTool: "rect",
      pendingRegion: null,
      existingRegions: [],
      overlay: null,
      ctx: null,
      drawState: { type: "rect", origin: [0.1, 0.2], current: [0.4, 0.5] },
      imageElement: null,
      highlightedSelectionId: null,
      assetCard: null,
      replaceTarget: null,
    };

    hooks.commitDrawState(state);

    expect(state.pendingRegion).toMatchObject({
      type: "rect",
      x: 0.1,
      y: 0.2,
      w: 0.30000000000000004,
      h: 0.3,
    });
    expect(document.activeElement).toBe(input);
  });

  it("replaces an existing region without creating a pending region", async () => {
    const hooks = await loadGallery();
    const originalRegion = { type: "rect", x: 0.1, y: 0.1, w: 0.2, h: 0.2, selection_id: 7 };
    const comment = {
      id: 42,
      unit_id: "login",
      body: "move highlight",
      region: originalRegion,
    };
    const state = {
      activeTool: "rect",
      pendingRegion: null,
      existingRegions: [originalRegion],
      overlay: null,
      ctx: null,
      drawState: { type: "rect", origin: [0.2, 0.3], current: [0.6, 0.7] },
      imageElement: null,
      highlightedSelectionId: null,
      assetCard: null,
      replaceTarget: { comment },
    };
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    hooks.commitDrawState(state);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(fetch).toHaveBeenCalledWith(
      "/api/comments/42",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(state.pendingRegion).toBeNull();
    expect(state.replaceTarget).toBeNull();
    expect(comment.region).toMatchObject({ type: "rect", selection_id: 7 });
    expect(state.existingRegions[0]).toBe(comment.region);
  });

  it("restores inline comment edit mode on Escape", async () => {
    const hooks = await loadGallery();
    const item = document.createElement("div");
    const body = document.createElement("span");
    const actions = document.createElement("span");
    const status = document.createElement("div");
    const comment = {
      id: 1,
      unit_id: "login",
      body: "original",
      region: null,
    };
    body.textContent = "original";
    actions.textContent = "actions";
    item.append(body, actions);
    document.body.append(item);

    hooks.beginInlineEdit(item, body, actions, comment, status);
    const editor = item.querySelector("textarea")!;
    editor.value = "changed";
    editor.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(item.classList.contains("is-editing")).toBe(false);
    expect(item.querySelector("textarea")).toBeNull();
    expect(body.textContent).toBe("original");
  });
});
