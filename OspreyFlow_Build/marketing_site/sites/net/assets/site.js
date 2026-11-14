/* OspreyFlow websites: the theme switch and the animations' player. No dependencies, no network. Written by hand;
   build.py copies it into each site. */
(function () {
  'use strict';
  var KEY = 'ospreyflow.site.theme', root = document.documentElement;
  function dark() { return root.classList.contains('theme-dark'); }
  function label() {
    var b = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < b.length; i++) { b[i].textContent = dark() ? 'Light theme' : 'Dark theme'; }
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('[data-theme-toggle]') : null;
    if (!t) { return; }
    root.classList.toggle('theme-dark');
    try { localStorage.setItem(KEY, dark() ? 'dark' : 'light'); } catch (err) {}
    label();
  });
  label();

  var STEP_SECONDS = 7;
  var still = false;
  try { still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (err) {}

  function player(el) {
    var scenes = el.querySelectorAll('[data-seat][data-step]:not(button)');
    var groups = el.querySelectorAll('.ov-steps, .gv-steps');
    var tabs = el.querySelectorAll('.ov-tab');
    var play = el.querySelector('[data-play]');
    var count = {}, seats = 0, seat = 0, step = 0, elapsed = 0, playing = !still, inView = true;
    for (var i = 0; i < scenes.length; i++) {
      var s = +scenes[i].getAttribute('data-seat'); count[s] = (count[s] || 0) + 1; seats = Math.max(seats, s + 1);
    }
    function show() {
      var i, j, on;
      for (i = 0; i < scenes.length; i++) {
        scenes[i].hidden = !(+scenes[i].getAttribute('data-seat') === seat && +scenes[i].getAttribute('data-step') === step);
      }
      for (i = 0; i < groups.length; i++) {
        on = +groups[i].getAttribute('data-seat') === seat; groups[i].hidden = !on;
        var bs = groups[i].querySelectorAll('button');
        for (j = 0; j < bs.length; j++) { bs[j].classList.toggle('is-on', on && +bs[j].getAttribute('data-step') === step); }
      }
      for (i = 0; i < tabs.length; i++) {
        on = +tabs[i].getAttribute('data-seat') === seat; tabs[i].classList.toggle('is-on', on); tabs[i].setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      elapsed = 0;
      // A chapter shown while paused is drawn in full, not frozen at its first frame.
      el.classList.toggle('is-still', !playing);
    }
    function next() { step += 1; if (step >= count[seat]) { step = 0; seat = (seat + 1) % seats; } show(); }
    function setPlaying(v) { playing = v; el.classList.toggle('is-paused', !v); if (v) { el.classList.remove('is-still'); } if (play) { play.textContent = v ? 'Pause' : 'Play'; } }
    el.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (!b || !el.contains(b)) { return; }
      if (b === play) { setPlaying(!playing); return; }
      if (b.classList.contains('ov-tab')) { seat = +b.getAttribute('data-seat'); step = 0; show(); return; }
      if (b.hasAttribute('data-step')) { step = +b.getAttribute('data-step'); show(); }
    });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) { inView = entries[0].isIntersecting; }, { threshold: 0.2 }).observe(el);
    }
    setPlaying(playing);
    el.classList.toggle('is-still', !playing);
    setInterval(function () { if (!playing || !inView || document.hidden) { return; } elapsed += 0.25; if (elapsed >= STEP_SECONDS) { next(); } }, 250);
  }
  var players = document.querySelectorAll('[data-player]');
  for (var p = 0; p < players.length; p++) { player(players[p]); }
})();
