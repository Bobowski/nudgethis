window.app ??= {};
app.frame = {
  el: null,
  markEl: null,
  seen: undefined,

  bind(el) {
    this.el = el;
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
