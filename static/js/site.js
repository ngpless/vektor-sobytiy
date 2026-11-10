/* Минимальный чистый JavaScript: версия для слабовидящих, карусель, меню. */
(function () {
  'use strict';
  var root = document.documentElement;

  /* ---------- Версия для слабовидящих ----------
     Состояние хранится в cookie vektor_a11y = «вкл:размер:схема:картинки»,
     поэтому сервер сразу отдаёт страницу в нужном виде, без мигания. */
  function readState() {
    return {
      on: root.getAttribute('data-a11y') === '1',
      size: root.getAttribute('data-size') || '1',
      scheme: root.getAttribute('data-scheme') || 'bw',
      img: root.getAttribute('data-img') !== 'off'
    };
  }
  function saveState(st) {
    var value = (st.on ? '1' : '0') + ':' + st.size + ':' + st.scheme + ':' + (st.img ? '1' : '0');
    document.cookie = 'vektor_a11y=' + value + '; path=/; max-age=31536000; SameSite=Lax';
    try { localStorage.setItem('vektor_a11y', value); } catch (e) { /* хранилище недоступно */ }
  }
  function applyState(st) {
    root.setAttribute('data-a11y', st.on ? '1' : '0');
    root.setAttribute('data-size', st.size);
    root.setAttribute('data-scheme', st.scheme);
    root.setAttribute('data-img', st.img ? 'on' : 'off');
    var toggle = document.getElementById('a11y-toggle');
    if (toggle) toggle.setAttribute('aria-pressed', st.on ? 'true' : 'false');
    document.querySelectorAll('[data-a11y-size]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-a11y-size') === st.size ? 'true' : 'false');
    });
    document.querySelectorAll('[data-a11y-scheme]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-a11y-scheme') === st.scheme ? 'true' : 'false');
    });
    var imgBtn = document.getElementById('a11y-img-toggle');
    if (imgBtn) {
      imgBtn.setAttribute('aria-pressed', st.img ? 'false' : 'true');
      imgBtn.textContent = st.img ? 'Отключить изображения' : 'Включить изображения';
    }
    saveState(st);
  }

  // Если cookie ещё нет, но в localStorage есть выбор (сервер мог не получить cookie) - восстанавливаем.
  if (document.cookie.indexOf('vektor_a11y=') === -1) {
    try {
      var saved = localStorage.getItem('vektor_a11y');
      if (saved) {
        var p = saved.split(':');
        if (p.length === 4) applyState({ on: p[0] === '1', size: p[1], scheme: p[2], img: p[3] !== '0' });
      }
    } catch (e) { /* ничего */ }
  }

  var toggle = document.getElementById('a11y-toggle');
  if (toggle) toggle.addEventListener('click', function () {
    var st = readState(); st.on = !st.on; applyState(st);
    if (st.on) { var first = document.querySelector('.a11y-panel .a11y-btn'); if (first) first.focus(); }
  });
  var exitBtn = document.getElementById('a11y-exit');
  if (exitBtn) exitBtn.addEventListener('click', function () {
    var st = readState(); st.on = false; applyState(st);
    var t = document.getElementById('a11y-toggle'); if (t) t.focus();
  });
  document.querySelectorAll('[data-a11y-size]').forEach(function (b) {
    b.addEventListener('click', function () { var st = readState(); st.size = b.getAttribute('data-a11y-size'); applyState(st); });
  });
  document.querySelectorAll('[data-a11y-scheme]').forEach(function (b) {
    b.addEventListener('click', function () { var st = readState(); st.scheme = b.getAttribute('data-a11y-scheme'); applyState(st); });
  });
  var imgToggle = document.getElementById('a11y-img-toggle');
  if (imgToggle) imgToggle.addEventListener('click', function () { var st = readState(); st.img = !st.img; applyState(st); });

  /* ---------- Меню ---------- */
  var navToggle = document.getElementById('nav-toggle');
  var nav = document.getElementById('main-nav');
  if (navToggle && nav) navToggle.addEventListener('click', function () {
    var open = nav.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  document.querySelectorAll('.sub-toggle').forEach(function (btn) {
    var li = btn.parentNode;
    btn.addEventListener('click', function () {
      var open = li.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('.has-sub.is-open').forEach(function (li) {
      li.classList.remove('is-open'); li.querySelector('.sub-toggle').setAttribute('aria-expanded', 'false');
    });
  });
  document.addEventListener('click', function (e) {
    document.querySelectorAll('.has-sub.is-open').forEach(function (li) {
      if (!li.contains(e.target)) { li.classList.remove('is-open'); li.querySelector('.sub-toggle').setAttribute('aria-expanded', 'false'); }
    });
  });

  /* ---------- Карусель баннеров ---------- */
  var car = document.querySelector('[data-carousel]');
  if (car) {
    var slides = Array.prototype.slice.call(car.querySelectorAll('.slide'));
    var dots = Array.prototype.slice.call(car.querySelectorAll('[data-car-dot]'));
    var pauseBtn = car.querySelector('[data-car-pause]');
    var index = 0, timer = null, paused = false;

    function show(i) {
      index = (i + slides.length) % slides.length;
      slides.forEach(function (s, k) {
        var active = k === index;
        s.classList.toggle('is-active', active);
        if (active) s.removeAttribute('hidden'); else s.setAttribute('hidden', '');
      });
      dots.forEach(function (d, k) {
        d.classList.toggle('is-active', k === index);
        if (k === index) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current');
      });
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    function start() {
      stop();
      if (paused || slides.length < 2 || root.getAttribute('data-a11y') === '1') return;
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      timer = setInterval(function () { show(index + 1); }, 6500);
    }
    var prev = car.querySelector('[data-car-prev]'), next = car.querySelector('[data-car-next]');
    if (prev) prev.addEventListener('click', function () { show(index - 1); start(); });
    if (next) next.addEventListener('click', function () { show(index + 1); start(); });
    dots.forEach(function (d, k) { d.addEventListener('click', function () { show(k); start(); }); });
    if (pauseBtn) pauseBtn.addEventListener('click', function () {
      paused = !paused;
      pauseBtn.setAttribute('aria-pressed', paused ? 'true' : 'false');
      pauseBtn.textContent = paused ? 'Продолжить' : 'Пауза';
      start();
    });
    car.addEventListener('mouseenter', stop);
    car.addEventListener('mouseleave', start);
    car.addEventListener('focusin', stop);
    car.addEventListener('focusout', start);
    if (toggle) toggle.addEventListener('click', start);
    start();
  }
})();
