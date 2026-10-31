// Отправка заявки без перезагрузки страницы (без JS форма тоже работает)
(function () {
  var form = document.getElementById("lead-form");
  if (!form || !window.fetch) return;
  var errBox = form.querySelector(".form-error");
  var ok = form.querySelector(".form-ok");

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    errBox.textContent = "";
    if (!form.full_name.value.trim()) { errBox.textContent = "Напишите, как вас зовут"; form.full_name.focus(); return; }
    if (form.phone.value.replace(/\D/g, "").length < 10) { errBox.textContent = "Проверьте номер телефона"; form.phone.focus(); return; }
    if (!form.consent.checked) { errBox.textContent = "Нужно согласие на обработку персональных данных"; return; }

    form.classList.add("is-loading");
    fetch(form.action, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: "Ошибка сервера" }; }); })
      .then(function (res) {
        if (res.ok) {
          ok.setAttribute("data-show", "");
          form.reset();
          if (window.ym && window.YM_ID) window.ym(window.YM_ID, "reachGoal", "lead");
        } else {
          errBox.textContent = res.error || "Не получилось отправить. Попробуйте ещё раз.";
        }
      })
      .catch(function () { errBox.textContent = "Нет связи с сервером. Попробуйте ещё раз."; })
      .finally(function () { form.classList.remove("is-loading"); });
  });
})();

// Закрывать мобильное меню после клика по пункту
document.querySelectorAll(".nav a").forEach(function (a) {
  a.addEventListener("click", function () { var t = document.getElementById("nav-toggle"); if (t) t.checked = false; });
});

// Слайдер: свайп, стрелки, точки, автопрокрутка (пауза при наведении)
document.querySelectorAll(".slider").forEach(function (root) {
  var track = root.querySelector(".slider__track");
  var slides = root.querySelectorAll(".slide");
  var dotsBox = root.querySelector(".slider__dots");
  if (!track || slides.length < 2) { if (dotsBox) dotsBox.hidden = true; root.querySelectorAll(".slider__btn").forEach(function (b) { b.hidden = true; }); return; }
  var i = 0, timer = null, delay = parseInt(root.dataset.autoplay || "0", 10);
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var dots = Array.prototype.map.call(slides, function (_, k) {
    var d = document.createElement("button");
    d.type = "button"; d.setAttribute("aria-label", "Слайд " + (k + 1));
    d.addEventListener("click", function () { show(k); restart(); });
    dotsBox.appendChild(d); return d;
  });
  function show(k) {
    i = (k + slides.length) % slides.length;
    track.style.transform = "translateX(" + (-100 * i) + "%)";
    dots.forEach(function (d, n) { d.classList.toggle("is-active", n === i); });
  }
  function restart() { if (timer) clearInterval(timer); if (delay && !reduce) timer = setInterval(function () { show(i + 1); }, delay); }
  root.querySelector(".slider__btn--prev").addEventListener("click", function () { show(i - 1); restart(); });
  root.querySelector(".slider__btn--next").addEventListener("click", function () { show(i + 1); restart(); });
  root.addEventListener("mouseenter", function () { if (timer) clearInterval(timer); });
  root.addEventListener("mouseleave", restart);
  var x0 = null;
  root.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  root.addEventListener("touchend", function (e) {
    if (x0 === null) return; var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 40) { show(i + (dx < 0 ? 1 : -1)); restart(); } x0 = null;
  });
  show(0); restart();
});
