window.app ??= {};
// Dictation into the message box, with the browser's own speech recognition
// (Chrome, Edge, Safari). The words land in the box as they are heard; the
// person reads them and sends. A browser without it shows no microphone.
app.dictate = {
  rec: null,

  can() {
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  },

  // Start, or stop when already listening. `on` hears whether it listens.
  toggle(box, on) {
    if (this.rec) return this.stop();
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new Rec();
    rec.lang = navigator.language || "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    const before = box.value.trim();
    rec.onresult = (e) => {
      const heard = [...e.results].map((r) => r[0].transcript).join("");
      box.value = [before, heard.trim()].filter(Boolean).join(" ");
      // data-bind listens for input: the $text signal follows the box.
      box.dispatchEvent(new Event("input", { bubbles: true }));
    };
    rec.onend = () => {
      this.rec = null;
      on(false);
    };
    rec.onerror = () => rec.abort();
    this.rec = rec;
    rec.start();
    on(true);
  },

  stop() {
    if (this.rec) this.rec.stop();
  },
};
