/* Shell behaviour shared by every screen: the source drawer, the score popover and "back" links. */
(() => {
  const mobileNav = matchMedia('(max-width: 960px)');
  const navMenu = document.querySelector('.nav__more');
  const syncNav = () => { if (navMenu) navMenu.open = !mobileNav.matches; };
  syncNav();
  mobileNav.addEventListener('change', syncNav);
  document.addEventListener('htmx:afterSwap', () => {
    if (!document.body.classList.contains('body--desk')) return;
    const topics = document.querySelector('.nav a[href="/inbox"]');
    if (document.querySelector('[data-editor]')) topics?.removeAttribute('aria-current');
    else topics?.setAttribute('aria-current', 'page');
  });
  // Native query navigation needs immediate feedback; restore it when returning through browser history.
  document.addEventListener('submit', event => {
    const form = event.target.closest('form[data-progress-label]');
    if (!form || event.defaultPrevented) return;
    const submit = form.querySelector('button[type="submit"]');
    submit.dataset.idleLabel = submit.textContent;
    submit.textContent = form.dataset.progressLabel;
    submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', () => {
    for (const form of document.querySelectorAll('form[data-progress-label]')) {
      const submit = form.querySelector('button[data-idle-label]');
      if (submit) { submit.textContent = submit.dataset.idleLabel; submit.disabled = false; }
      form.removeAttribute('aria-busy');
    }
  });
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
    if (mobileNav.matches && navMenu && !navMenu.contains(event.target)) navMenu.open = false;
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
    if (mobileNav.matches && navMenu?.open) { navMenu.open = false; navMenu.querySelector('summary').focus(); return; }
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
