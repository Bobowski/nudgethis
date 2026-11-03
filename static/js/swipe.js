window.app ??= {};
// The sheet on a phone is held by its header: it follows the finger down, with
// a little give upward, and on release it closes when pulled past a quarter of
// its height or flicked down; else it springs back. The chat scrolls itself;
// the big screen has no drag.
app.swipe = {
  mount(el) {
    let held = null;
    const place = (dy) => {
      // Down follows the finger; up stretches a little and stops.
      const y = dy >= 0 ? dy : -18 * (1 - Math.exp(dy / 60));
      el.style.transform = `translateY(${y}px)`;
    };
    el.addEventListener(
      "touchstart",
      (e) => {
        const grab =
          e.touches.length === 1 &&
          !window.matchMedia("(min-width: 900px)").matches &&
          e.target.closest("[data-grab]") &&
          !e.target.closest("button, a, input, textarea");
        if (!grab) return;
        const t = e.touches[0];
        held = { y: t.clientY, last: t.clientY, at: Date.now(), v: 0 };
        el.classList.add("held");
      },
      { passive: true },
    );
    el.addEventListener(
      "touchmove",
      (e) => {
        if (!held) return;
        const t = e.touches[0];
        const now = Date.now();
        held.v = (t.clientY - held.last) / Math.max(1, now - held.at); // px per ms
        held.last = t.clientY;
        held.at = now;
        place(t.clientY - held.y);
      },
      { passive: true },
    );
    const end = () => {
      if (!held) return;
      const dy = held.last - held.y;
      const flick = held.v > 1 && dy > 30;
      held = null;
      el.classList.remove("held");
      // The class transition carries it from where the finger left it.
      el.style.transform = "";
      if (flick || dy > el.offsetHeight / 4) {
        el.dispatchEvent(new CustomEvent("swipe-close"));
      }
    };
    el.addEventListener("touchend", end, { passive: true });
    el.addEventListener("touchcancel", end, { passive: true });
  },
};
