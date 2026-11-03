window.app ??= {};
app.frame = {
  el: null,
  markEl: null,
  seen: undefined,

  bind(el) {
    this.el = el;
    this.keyboard();
  },

  // iOS lays fixed elements out behind the on-screen keyboard. --kb is the
  // keyboard's height, so the bars at the bottom can ride above it.
  keyboard() {
    const vv = window.visualViewport;
    if (!vv || this.kbBound) return;
    this.kbBound = true;
    const set = () => {
      const kb = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty("--kb", `${Math.round(kb)}px`);
    };
    vv.addEventListener("resize", set);
    vv.addEventListener("scroll", set);
    set();
  },

  mark(el) {
    this.markEl = el;
  },

  rev(v) {
    if (this.seen === undefined) {
      this.seen = v;
      return;
    }
    if (v !== this.seen) {
      this.seen = v;
      if (this.el) this.el.src = this.el.src;
      if (this.markEl) {
        this.markEl.classList.remove("play");
        void this.markEl.offsetWidth;
        this.markEl.classList.add("play");
      }
    }
  },
};
