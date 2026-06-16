import { beforeEach, describe, expect, it, vi } from "vitest";

function makeDetailPayload() {
  return {
    unit: {
      id: "unit-1",
      label: "Unit 1",
      encoded_id: "unit-1",
      assets: [
        {
          type: "screenshot",
          path: "img.png",
          label: "img.png",
          encoded_path: "img.png",
          mime_type: "image/png",
        },
      ],
      metadata: [],
      vizdiff: null,
    },
    units: [{ id: "unit-1", label: "Unit 1", encoded_id: "unit-1" }],
    nav: { prev: null, next: null, prev_label: null, next_label: null },
  };
}

async function loadDetailGallery(fetchImpl = vi.fn(() => Promise.reject(new Error("offline")))) {
  vi.resetModules();
  document.body.innerHTML = [
    '<div id="detail-theme-controls"></div>',
    '<button id="detail-size-toggle" class="btn">Full Size</button>',
    '<span id="prev-slot"></span>',
    '<span id="next-slot"></span>',
    '<a href="/" id="index-btn"></a>',
    '<div id="unit-assets"></div>',
    '<div id="unit-metadata"></div>',
    '<div id="detail-filename">unit-1</div>',
    '<button id="copy-filename-btn"></button>',
    '<span id="copy-filename-status"></span>',
    '<div id="comments-list"></div>',
    '<form id="comment-form">',
    '  <input type="text" id="comment-input">',
    '  <button type="submit">Submit</button>',
    '</form>',
    '<button id="detail-done-btn"></button>',
  ].join("\n");
  vi.stubGlobal("fetch", fetchImpl);
  window.__BUGSHOT_ENABLE_TEST_HOOKS__ = true;
  window.__BUGSHOT_DETAIL__ = makeDetailPayload() as any;
  await import("../../static/gallery.ts");
  return window.__BUGSHOT_TEST__!;
}

async function flushPromises() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("detail page fullsize toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    delete (window as any).__BUGSHOT_DETAIL__;
    delete (window as any).__BUGSHOT_UNITS__;
  });

  it("s key toggles detail-fullsize-mode on then off within a single session", async () => {
    await loadDetailGallery();
    const assets = document.getElementById("unit-assets")!;
    expect(assets.classList.contains("detail-fullsize-mode")).toBe(false);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "s", bubbles: true }));
    expect(assets.classList.contains("detail-fullsize-mode")).toBe(true);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "s", bubbles: true }));
    expect(assets.classList.contains("detail-fullsize-mode")).toBe(false);
  });

  it("detail-size-toggle button toggles fullsize mode and updates label", async () => {
    await loadDetailGallery();
    const assets = document.getElementById("unit-assets")!;
    const btn = document.getElementById("detail-size-toggle") as HTMLButtonElement;

    btn.click();
    expect(assets.classList.contains("detail-fullsize-mode")).toBe(true);
    expect(btn.textContent).toBe("Constrained");

    btn.click();
    expect(assets.classList.contains("detail-fullsize-mode")).toBe(false);
    expect(btn.textContent).toBe("Full Size");
  });

  it("marks the current detail unit seen when the page loads", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response("{}", { status: 200 })));

    await loadDetailGallery(fetchMock);
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/review-state",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ unit_id: "unit-1", seen: true }),
      }),
    );
  });

  it("waits for the current seen update before marking the session done", async () => {
    let resolveSeen: (value: Response) => void = () => {};
    const fetchMock = vi.fn((url) => {
      if (url === "/api/review-state") {
        return new Promise<Response>((resolve) => {
          resolveSeen = resolve;
        });
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("confirm", vi.fn(() => true));

    await loadDetailGallery(fetchMock);
    (document.getElementById("detail-done-btn") as HTMLButtonElement).click();
    await flushPromises();

    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/done",
      expect.objectContaining({ method: "POST" }),
    );

    resolveSeen(new Response("{}", { status: 200 }));
    await flushPromises();
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/done",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
