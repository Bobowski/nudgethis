window.app ??= {};
app.snap = {
  stream: null,
  frameEl: null,
  inputEl: null,

  bind(el) {
    this.frameEl = el;
  },

  input(el) {
    this.inputEl = el;
  },

  stop() {
    if (this.stream) {
      for (const track of this.stream.getTracks()) track.stop();
      this.stream = null;
    }
  },

  async go(hint) {
    const url = await this.grab();
    if (url) {
      hint("");
      app.ink.open(url);
    } else if (this.inputEl) {
      hint("Take a screenshot, then pick it.");
      this.inputEl.click();
    } else {
      hint("Snaps are not available on this browser.");
    }
  },

  pick(evt) {
    const file = evt.target.files && evt.target.files[0];
    evt.target.value = "";
    if (file) {
      const reader = new FileReader();
      reader.onload = () => app.ink.open(reader.result);
      reader.readAsDataURL(file);
    }
  },

  async grab() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      return null;
    }
    const root = document.documentElement;
    try {
      const track = await this.track();
      if (!track) return null;
      const video = document.createElement("video");
      video.muted = true;
      video.srcObject = this.stream;
      await video.play();
      // Element Capture sends frames only while the iframe is eligible. With no
      // fresh frame, crop the whole tab instead of drawing an empty video.
      let restricted = await this.restrict(track);
      if (restricted && !(await this.fresh(video))) {
        await track.restrictTo(null);
        restricted = false;
      }
      if (!restricted) {
        root.classList.add("snapping");
        await new Promise((resolve) => setTimeout(resolve, 120));
        if (!(await this.fresh(video))) return null;
      }
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (restricted) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
      } else {
        const rect = this.frameEl.getBoundingClientRect();
        const scale = video.videoWidth / window.innerWidth;
        const sx = rect.left * scale;
        const sy = rect.top * scale;
        const sw = rect.width * scale;
        const sh = rect.height * scale;
        canvas.width = Math.max(1, Math.round(sw));
        canvas.height = Math.max(1, Math.round(sh));
        ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
      }
      video.pause();
      video.srcObject = null;
      return canvas.toDataURL("image/png");
    } catch {
      return null;
    } finally {
      root.classList.remove("snapping");
    }
  },

  // True when the video paints a new frame within a second.
  fresh(video) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), 1000);
      video.requestVideoFrameCallback(() => {
        clearTimeout(timer);
        resolve(true);
      });
    });
  },

  async track() {
    const live =
      this.stream &&
      this.stream.getVideoTracks().some((t) => t.readyState === "live");
    if (live) return this.stream.getVideoTracks()[0];
    this.stop();
    this.stream = await navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: "browser" },
      preferCurrentTab: true,
      audio: false,
    });
    const track = this.stream.getVideoTracks()[0];
    track.addEventListener("ended", () => {
      this.stream = null;
    });
    return track;
  },

  async restrict(track) {
    if (!window.RestrictionTarget || !this.frameEl) return false;
    try {
      const target = await RestrictionTarget.fromElement(this.frameEl);
      await track.restrictTo(target);
      return true;
    } catch {
      return false;
    }
  },
};
