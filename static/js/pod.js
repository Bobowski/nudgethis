window.app ??= {};
// The chat list sits at its newest message. It goes to the bottom each time
// it is shown (a hidden list has no height, so an earlier scroll did
// nothing), and stays there as messages arrive and shots load, unless the
// user has scrolled up to read.
app.pod = (el) => {
  let pinned = true;
  const bottom = () => {
    el.scrollTop = el.scrollHeight;
  };
  const follow = () => pinned && bottom();
  el.addEventListener(
    "scroll",
    () => {
      pinned = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    },
    { passive: true },
  );
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
  new MutationObserver(follow).observe(el, { childList: true, subtree: true });
  el.addEventListener("load", follow, true);
  bottom();
  return {};
};
