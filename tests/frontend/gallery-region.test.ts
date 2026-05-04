import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadGallery() {
  vi.resetModules();
  document.body.innerHTML = "";
  window.__BUGSHOT_ENABLE_TEST_HOOKS__ = true;
  window.__BUGSHOT_UNITS__ = [];
  await import("../../static/gallery.ts");
  return window.__BUGSHOT_TEST__;
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
});
