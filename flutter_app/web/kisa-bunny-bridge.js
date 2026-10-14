/* Bunny's official Player.js integration. Events only trigger UI navigation;
   actual paid episode access is always rechecked server-side. */
(function () {
  'use strict';
  const attached = new WeakSet();
  function attachOne(frame) {
      if (!window.playerjs || !window.playerjs.Player || !frame) return;
      {
      if (attached.has(frame)) return;
      attached.add(frame);
      try {
        const player = new window.playerjs.Player(frame);
        player.on('ended', function () {
          window.dispatchEvent(new CustomEvent('kisa-bunny-ended', {
            detail: frame.getAttribute('data-kisa-bunny')
          }));
        });
      } catch (error) { console.warn('KISA Bunny player events unavailable', error); }
      }
  }
  window.addEventListener('kisa-bunny-mount', function (event) { attachOne(event.detail); });
})();
