window.app ??= {};
app.ink = {
  mount(el) {
    this.el = el;
    this.canvas = el.querySelector("canvas");
    this.ctx = this.canvas.getContext("2d");
    this.ops = [];
    this.draft = null;
    this.t = "marker";
    this.doneCb = null;
    this.img = null;
    this.canvas.addEventListener("pointerdown", (e) => this.down(e));
    this.canvas.addEventListener("pointermove", (e) => this.move(e));
    this.canvas.addEventListener("pointerup", (e) => this.up(e));
    this.canvas.addEventListener("pointercancel", (e) => this.up(e));
  },

  open(src, done) {
    this.doneCb = done;
    this.ops = [];
    this.draft = null;
    this.el.classList.add("on");
    const img = new Image();
    img.onload = () => {
      this.img = img;
      const dpr = window.devicePixelRatio || 1;
      const box = this.canvas.getBoundingClientRect();
      this.w = Math.max(1, box.width);
      this.h = Math.max(1, box.height);
      this.canvas.width = Math.round(this.w * dpr);
      this.canvas.height = Math.round(this.h * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Fit the shot inside the canvas without stretching it.
      const fit = Math.min(this.w / img.width, this.h / img.height);
      this.fw = img.width * fit;
      this.fh = img.height * fit;
      this.fx = (this.w - this.fw) / 2;
      this.fy = (this.h - this.fh) / 2;
      this.color =
        getComputedStyle(this.el).getPropertyValue("--accent").trim() ||
        "rgb(212, 70, 30)";
      this.tool("marker");
      this.redraw();
    };
    img.src = src;
  },

  tool(name) {
    this.t = name;
    for (const b of this.el.querySelectorAll("[data-tool]")) {
      b.classList.toggle("on", b.dataset.tool === name);
    }
  },

  undo() {
    if (this.draft) this.draft = null;
    else this.ops.pop();
    this.redraw();
  },

  cancel() {
    this.el.classList.remove("on");
  },

  done() {
    const dpr = this.canvas.width / this.w;
    const scale = Math.min(1, 1600 / (Math.max(this.fw, this.fh) * dpr));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(this.fw * dpr * scale));
    c.height = Math.max(1, Math.round(this.fh * dpr * scale));
    const ctx = c.getContext("2d");
    const [x, y, w, h] = [this.fx, this.fy, this.fw, this.fh].map((v) => v * dpr);
    ctx.drawImage(this.canvas, x, y, w, h, 0, 0, c.width, c.height);
    const marked = c.toDataURL("image/png");
    ctx.drawImage(this.img, 0, 0, c.width, c.height);
    this.el.classList.remove("on");
    this.doneCb([marked, c.toDataURL("image/png")]);
  },

  down(e) {
    if (!this.img) return;
    const p = this.point(e);
    if (this.t === "text") {
      const str = window.prompt("Label");
      if (str) {
        this.ops.push({ t: "t", x: p[0], y: p[1], str });
        this.redraw();
      }
      return;
    }
    this.canvas.setPointerCapture(e.pointerId);
    this.draft =
      this.t === "marker"
        ? { t: "m", pts: [p] }
        : { t: { arrow: "a", ring: "e" }[this.t] || "b", x1: p[0], y1: p[1], x2: p[0], y2: p[1] };
  },

  move(e) {
    if (!this.draft) return;
    const p = this.point(e);
    if (this.draft.t === "m") this.draft.pts.push(p);
    else {
      this.draft.x2 = p[0];
      this.draft.y2 = p[1];
    }
    this.redraw();
  },

  up() {
    if (!this.draft) return;
    this.ops.push(this.draft);
    this.draft = null;
    this.redraw();
  },

  point(e) {
    const r = this.canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  },

  redraw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);
    ctx.drawImage(this.img, this.fx, this.fy, this.fw, this.fh);
    for (const op of this.ops) this.draw(op);
    if (this.draft) this.draw(this.draft);
  },

  draw(op) {
    const ctx = this.ctx;
    ctx.strokeStyle = this.color;
    ctx.fillStyle = this.color;
    ctx.lineWidth = 4;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    if (op.t === "m") {
      ctx.moveTo(op.pts[0][0], op.pts[0][1]);
      for (const p of op.pts.slice(1)) ctx.lineTo(p[0], p[1]);
      ctx.stroke();
    } else if (op.t === "a") {
      const a = Math.atan2(op.y2 - op.y1, op.x2 - op.x1);
      ctx.moveTo(op.x1, op.y1);
      ctx.lineTo(op.x2, op.y2);
      for (const d of [0.45, -0.45]) {
        ctx.moveTo(op.x2, op.y2);
        ctx.lineTo(op.x2 - 14 * Math.cos(a + d), op.y2 - 14 * Math.sin(a + d));
      }
      ctx.stroke();
    } else if (op.t === "e") {
      const rx = Math.abs(op.x2 - op.x1) / 2;
      const ry = Math.abs(op.y2 - op.y1) / 2;
      ctx.ellipse((op.x1 + op.x2) / 2, (op.y1 + op.y2) / 2, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else if (op.t === "b") {
      ctx.strokeRect(op.x1, op.y1, op.x2 - op.x1, op.y2 - op.y1);
    } else if (op.t === "t") {
      ctx.font = "600 18px 'Instrument Sans', sans-serif";
      ctx.fillText(op.str, op.x, op.y);
    }
  },
};
