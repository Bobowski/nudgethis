window.app ??= {};
app.pod = (el) => {
  const bottom = () => {
    el.scrollTop = el.scrollHeight;
  };
  new MutationObserver(bottom).observe(el, { childList: true, subtree: true });
  bottom();
  return {};
};
