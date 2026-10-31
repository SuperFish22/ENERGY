// Режим визитки: точки навигации и листание клавиатурой
(function () {
  var box = document.getElementById("vz");
  var slides = Array.prototype.slice.call(document.querySelectorAll(".vz-s"));
  var nav = document.querySelector(".vz-dots");
  if (!box || !slides.length) return;

  var dots = slides.map(function (s, i) {
    var b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", s.dataset.title || "Слайд " + (i + 1));
    b.innerHTML = "<span>" + (s.dataset.title || i + 1) + "</span>";
    b.addEventListener("click", function () { go(i); });
    nav.appendChild(b);
    return b;
  });

  function current() {
    var mid = box.scrollTop + box.clientHeight / 2, idx = 0;
    slides.forEach(function (s, i) { if (s.offsetTop <= mid) idx = i; });
    return idx;
  }
  function go(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    box.scrollTo({ top: slides[i].offsetTop });
  }
  function mark() {
    var c = current();
    dots.forEach(function (d, i) { d.classList.toggle("is-active", i === c); });
  }
  box.addEventListener("scroll", function () { window.requestAnimationFrame(mark); }, { passive: true });
  mark();

  document.addEventListener("keydown", function (e) {
    if (e.target.closest("input, textarea, select")) return;
    if (["ArrowDown", "PageDown", " "].indexOf(e.key) > -1) { e.preventDefault(); go(current() + 1); }
    if (["ArrowUp", "PageUp"].indexOf(e.key) > -1) { e.preventDefault(); go(current() - 1); }
    if (e.key === "Home") { e.preventDefault(); go(0); }
    if (e.key === "End") { e.preventDefault(); go(slides.length - 1); }
    if (e.key === "Escape") { window.location.href = "/"; }
  });
})();
