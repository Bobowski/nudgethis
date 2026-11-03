window.app ??= {};
// A sideways swipe on the panel closes it, back to the app. Vertical scrolls,
// a swipe that starts in a field or a scrolled code block, and a swipe on the
// big screen (where the panel sits beside the app) are left alone.
app.swipe = {
  mount(el) {
    let start = null;
    el.addEventListener(
      "touchstart",
      (e) => {
        const t = e.touches[0];
        const skip =
          e.touches.length > 1 ||
          window.matchMedia("(min-width: 900px)").matches ||
          e.target.closest("input, textarea, select, pre, .tabs, .seg");
        start = skip ? null : { x: t.clientX, y: t.clientY, at: Date.now() };
      },
      { passive: true },
    );
    el.addEventListener(
      "touchend",
      (e) => {
        if (!start) return;
        const t = e.changedTouches[0];
        const dx = t.clientX - start.x;
        const dy = t.clientY - start.y;
        const quick = Date.now() - start.at < 700;
        start = null;
        if (quick && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.8) {
          el.dispatchEvent(new CustomEvent("swipe-close", { detail: dx > 0 ? "right" : "left" }));
        }
      },
      { passive: true },
    );
    el.addEventListener("touchcancel", () => (start = null), { passive: true });
  },
};
