window.app ??= {};
// The sheet closes with a swipe down that starts on its header (a phone's
// bottom sheet). A swipe in the chat scrolls it; the big screen has no swipe.
app.swipe = {
  mount(el) {
    let start = null;
    el.addEventListener(
      "touchstart",
      (e) => {
        const t = e.touches[0];
        const grab =
          e.touches.length === 1 &&
          !window.matchMedia("(min-width: 900px)").matches &&
          e.target.closest("[data-grab]") &&
          !e.target.closest("button, a, input, textarea");
        start = grab ? { x: t.clientX, y: t.clientY, at: Date.now() } : null;
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
        const quick = Date.now() - start.at < 800;
        start = null;
        if (quick && dy > 60 && dy > Math.abs(dx) * 1.5) {
          el.dispatchEvent(new CustomEvent("swipe-close"));
        }
      },
      { passive: true },
    );
    el.addEventListener("touchcancel", () => (start = null), { passive: true });
  },
};
