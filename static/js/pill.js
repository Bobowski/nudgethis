window.app ??= {};
// The pill docks at the top or the bottom. A drag toward the middle moves it
// to the other dock; a pull toward its own edge bounces and opens the composer.
// A tap, a sideways swipe, and a long press are the other gestures. Each one
// is a DOM event on #nudge; Datastar attributes there turn it into signals.
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
    let start = null;
    let timer = 0;
    const emit = (name, detail) =>
      host.dispatchEvent(new CustomEvent(name, { detail }));
    const atBottom = () => host.classList.contains("bottom");
    const rubber = (d, max) =>
      Math.sign(d) * max * (1 - Math.exp(-Math.abs(d) / max));
    const place = (x, y) => {
      el.style.transform = x || y ? `translate(${x}px, ${y}px)` : "";
    };

    el.addEventListener("pointerdown", (e) => {
      start = { x: e.clientX, y: e.clientY, axis: null };
      el.setPointerCapture(e.pointerId);
      el.classList.add("pressed");
      timer = setTimeout(() => {
        start = null;
        el.classList.remove("pressed");
        emit("pill-hold");
      }, 480);
    });

    el.addEventListener("pointermove", (e) => {
      if (!start) return;
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      if (!start.axis && Math.hypot(dx, dy) > 6) {
        start.axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
        clearTimeout(timer);
        el.classList.remove("pressed");
        el.classList.add("dragging");
      }
      if (start.axis === "x") place(rubber(dx, 90), 0);
      if (start.axis === "y") {
        const toEdge = atBottom() ? dy > 0 : dy < 0;
        place(0, toEdge ? rubber(dy, 26) : dy);
      }
    });

    const end = (e, cancelled) => {
      clearTimeout(timer);
      el.classList.remove("pressed", "dragging");
      if (!start) return;
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      const axis = start.axis;
      start = null;
      if (cancelled) return place(0, 0);
      if (!axis) return emit("pill-tap");
      if (axis === "x") {
        place(0, 0);
        if (Math.abs(dx) > 56) emit("pill-swipe", dx < 0 ? "left" : "right");
        return;
      }
      const toEdge = atBottom() ? dy > 0 : dy < 0;
      if (toEdge) {
        place(0, 0);
        if (Math.abs(dy) > 14) {
          this.bounce(el);
          emit("pill-pull");
        }
        return;
      }
      if (Math.abs(dy) < innerHeight * 0.18) return place(0, 0);
      this.dock(el, host, atBottom() ? "top" : "bottom", emit);
    };
    el.addEventListener("pointerup", (e) => end(e, false));
    el.addEventListener("pointercancel", (e) => end(e, true));
  },

  // FLIP: keep the pill where the finger left it, switch the dock, then let
  // the transition carry it home.
  dock(el, host, side, emit) {
    const before = el.getBoundingClientRect().top;
    el.style.transition = "none";
    el.style.transform = "";
    host.classList.toggle("bottom", side === "bottom");
    emit("pill-dock", side);
    const after = el.getBoundingClientRect().top;
    el.style.transform = `translateY(${before - after}px)`;
    void el.offsetWidth;
    el.style.transition = "";
    el.style.transform = "";
  },

  bounce(el) {
    el.classList.remove("bounce");
    void el.offsetWidth;
    el.classList.add("bounce");
  },
};
