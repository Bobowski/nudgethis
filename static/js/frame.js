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
  // keyboard's height, so the bars at the bottom can ride above it. iOS also
  // scrolls the page to show a field and can leave it scrolled when the
  // keyboard closes, which moves the pill off the screen: scroll it back.
  keyboard() {
    const vv = window.visualViewport;
    if (!vv || this.kbBound) return;
    this.kbBound = true;
    const set = () => {
      // A pinch zoom also shrinks the visual viewport; that is no keyboard.
      const zoomed = Math.abs(vv.scale - 1) > 0.01;
      const kb = zoomed ? 0 : Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty("--kb", `${Math.round(kb)}px`);
      if (kb < 1 && !zoomed) this.settle();
    };
    vv.addEventListener("resize", set);
    vv.addEventListener("scroll", set);
    document.addEventListener("focusout", () => setTimeout(() => this.settle(), 120));
    set();
  },

  settle() {
    const field = document.activeElement;
    if (field && field.matches("input, textarea")) return;
    if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
  },

  // The app reloads itself (nudge.js), so it stays on the page the person is
  // on. An app without nudge.js does not answer: load its first page again.
  reload() {
    const win = this.el && this.el.contentWindow;
    if (!win) return;
    let heard = false;
    const on = (e) => {
      if (e.source === win && e.data && e.data.type === "nudge:reloading") heard = true;
    };
    window.addEventListener("message", on);
    win.postMessage({ type: "nudge:reload" }, "*");
    setTimeout(() => {
      window.removeEventListener("message", on);
      if (!heard) this.el.src = this.el.src;
    }, 700);
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
      this.reload();
      if (this.markEl) {
        this.markEl.classList.remove("play");
        void this.markEl.offsetWidth;
        this.markEl.classList.add("play");
      }
    }
  },
};
