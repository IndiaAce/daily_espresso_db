/* Daily Espresso — the only runtime behaviour on the page.
   Placeholder until `support.js` is imported from Claude Design. */
(function () {
  'use strict';

  // The first French card hides its answer until you ask for it.
  document.querySelectorAll('.card--quiz').forEach(function (card) {
    function reveal() { card.dataset.revealed = 'true'; }
    card.addEventListener('click', reveal);
    card.setAttribute('tabindex', '0');
    card.setAttribute('role', 'button');
    card.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        reveal();
      }
    });
  });
})();
