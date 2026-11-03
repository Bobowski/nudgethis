window.app ??= {};
// The pill is the only thing over the app. A tap opens the sheet; a long press
// draws on the app. Each is a DOM event on #nudge; Datastar attributes there
// turn it into signals. A finger that moves is scrolling the app, not a tap.
app.pill = {
  load(key, fallback) {
    try {
      const v = localStorage.getItem(`nudgethis.${key}`);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },

  save(key, value) {
    try {
      localStorage.setItem(`nudgethis.${key}`, JSON.stringify(value));
    } catch {}
  },

  mount(el) {
    const host = el.closest("#nudge");
    const emit = (name) => host.dispatchEvent(new CustomEvent(name));
    let start = null;
    let timer = 0;

    // The pill opens the sheet on the tap, so the mouse events a touch sends
    // after it would land on the app and blur the page.
    el.addEventListener("touchend", (e) => e.cancelable && e.preventDefault(), {
      passive: false,
    });

    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      start = { x: e.clientX, y: e.clientY };
      el.setPointerCapture(e.pointerId);
      el.classList.add("pressed");
      timer = setTimeout(() => {
        start = null;
        el.classList.remove("pressed");
        emit("pill-hold");
      }, 480);
    });

    el.addEventListener("pointermove", (e) => {
      if (start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 10) {
        clearTimeout(timer);
        start = null;
        el.classList.remove("pressed");
      }
    });

    const end = (cancelled) => {
      clearTimeout(timer);
      el.classList.remove("pressed");
      if (start && !cancelled) emit("pill-tap");
      start = null;
    };
    el.addEventListener("pointerup", () => end(false));
    el.addEventListener("pointercancel", () => end(true));
  },
};
