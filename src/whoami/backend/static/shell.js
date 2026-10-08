/* Shell behaviour shared by every screen: the source drawer, the score popover and "back" links. */
(() => {
  let opener = null;
  const drawerOf = node => node.closest('.drawer');
  const openDrawer = () => document.querySelector('.drawer.is-open');
  const openPopover = () => document.querySelector('details.relative[open]');

  function closeDrawer(drawer) {
    drawer.classList.remove('is-open');
  }

  // The drawer is inert while closed so its hidden controls are not tab stops; opening moves focus in, closing returns it.
  new MutationObserver(records => {
    for (const {target} of records) {
      if (!target.matches('.drawer')) continue;
      const open = target.classList.contains('is-open');
      if (target.inert === !open) continue;
      target.inert = !open;
      if (open) {
        target.tabIndex = -1;
        target.focus({preventScroll: true});
      } else if (opener?.isConnected) {
        opener.focus({preventScroll: true});
      }
    }
  }).observe(document.body, {attributes: true, attributeFilter: ['class'], subtree: true});

  document.addEventListener('htmx:beforeRequest', event => {
    if (event.detail.target?.id === 'source-body') opener = event.detail.elt;
  });
  document.addEventListener('click', event => {
    const close = event.target.closest('[data-close-drawer]');
    if (close) return closeDrawer(drawerOf(close));
    const back = event.target.closest('[data-history-back]');
    if (back && history.length > 1 && document.referrer.startsWith(location.origin)) {
      event.preventDefault();
      history.back();
    }
    const popover = openPopover();
    if (popover && !popover.contains(event.target)) popover.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    const drawer = openDrawer();
    const popover = openPopover();
    if (popover) {
      popover.open = false;
      popover.querySelector('summary').focus({preventScroll: true});
    } else if (drawer) {
      closeDrawer(drawer);
    }
  });
})();
