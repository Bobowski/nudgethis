window.app ??= {};
// The chat list sits at its newest message. It goes to the bottom each time
// it is shown (a hidden list has no height, so an earlier scroll did
// nothing), and stays there as messages arrive and shots load, unless the
// user has scrolled up to read. A finger on the list owns it: no jump to the
// bottom while it scrolls, and dragging it closes the phone's keyboard (with
// the keyboard up, iOS scrolls the page instead of the list).
app.pod = (el) => {
  let pinned = true;
  let touching = false;
  let startY = 0;
  const bottom = () => {
    el.scrollTop = el.scrollHeight;
  };
  const follow = () => pinned && !touching && bottom();
  el.addEventListener(
    "scroll",
    () => {
      pinned = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    },
    { passive: true },
  );
  el.addEventListener(
    "touchstart",
    (e) => {
      touching = true;
      startY = e.touches[0].clientY;
    },
    { passive: true },
  );
  el.addEventListener(
    "touchmove",
    (e) => {
      const field = document.activeElement;
      if (field && field.matches("textarea, input") && Math.abs(e.touches[0].clientY - startY) > 8) {
        field.blur();
      }
    },
    { passive: true },
  );
  const release = () => {
    touching = false;
  };
  el.addEventListener("touchend", release, { passive: true });
  el.addEventListener("touchcancel", release, { passive: true });
  // Shown again (it was display: none, or the panel slid in): to the bottom.
  let shown = false;
  new ResizeObserver(() => {
    const now = el.clientHeight > 0;
    if (now && !shown) {
      pinned = true;
      bottom();
    } else follow();
    shown = now;
  }).observe(el);
  // New messages follow; the status line's ticking clock is not news.
  new MutationObserver((records) => {
    if (records.every((r) => r.target.closest && r.target.closest(".clock"))) return;
    follow();
  }).observe(el, { childList: true, subtree: true });
  el.addEventListener("load", follow, true);
  bottom();
  return {};
};
