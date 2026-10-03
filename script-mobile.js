/* ============================================================
   MOBILE SCRIPT — управление свайпами
   ============================================================ */

$(document).ready(function() {

    // ===== Инициализация =====
    Init();

    // ===== Настройки свайпа =====
    var touchStartY = 0;
    var touchStartX = 0;
    var touchStartTime = 0;
    var touchThreshold = 40;   // минимальная дистанция свайпа в px
    var touchMaxTime = 600;    // макс. длительность свайпа в мс

    $(document)
        .on('touchstart', function(e) {
            if (e.originalEvent.touches.length !== 1) return;
            var t = e.originalEvent.touches[0];
            touchStartY = t.clientY;
            touchStartX = t.clientX;
            touchStartTime = Date.now();
        })

        .on('touchend', function(e) {
            if ($ScrollState) return;

            var t = e.originalEvent.changedTouches[0];
            var deltaY = touchStartY - t.clientY;
            var deltaX = touchStartX - t.clientX;
            var duration = Date.now() - touchStartTime;

            // Слишком долго — это был не свайп, а тап/удержание
            if (duration > touchMaxTime) return;

            var absY = Math.abs(deltaY);
            var absX = Math.abs(deltaX);

            // Вертикальный свайп
            if (absY > absX && absY > touchThreshold) {
                $ScrollState = true;
                UpdateScreen(deltaY > 0 ? '+' : '-');
            }
            // Горизонтальный свайп
            else if (absX > absY && absX > touchThreshold) {
                $ScrollState = true;
                UpdateScreen(deltaX > 0 ? '-' : '+');
            }
        });

    // ===== Блокируем нативный скролл внутри ScrollPane =====
    $('#ScrollPane').on('touchmove', function(e) {
        e.preventDefault();
    });

    // ===== Resize / orientationchange =====
    var resizeTimer;
    $(window).on('resize orientationchange', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            if (typeof $CibleSlide !== 'undefined' && $CibleSlide) {
                var $pane = $('.pane[data-id="' + $CibleSlide + '"]');
                if ($pane.length) {
                    var $spane = $pane.closest('.spane');
                    if ($spane.length) {
                        TweenMax.set($spane, {scrollTo: $pane});
                    }
                    var $scr = $pane.closest('.scr');
                    if (!$scr.length) $scr = $pane;
                    TweenMax.to('#ScrollPane', 0, {scrollTo: $scr});
                }
            }
        }, 250);
    });
});


/* ============================================================
   ОБЩИЕ ФУНКЦИИ
   ============================================================ */

function Init() {
    $ScrollSpeed = 0.4;   // на мобилке чуть быстрее — приятнее
    $ScrollState = false;

    // Собираем все слайды с data-id в порядке DOM
    $ListSlides = [];
    $('.pane[data-id]').each(function() {
        $ListSlides.push($(this).attr('data-id'));
    });

    $ActualSlide = $CibleSlide = $ListSlides[0];

    // Сброс позиций
    $('#ScrollPane').scrollTop(0);
    $('.spane').scrollLeft(0);

    // Показываем первый слайд
    $('.visible').removeClass('visible');
    $('.pane[data-id="' + $ActualSlide + '"]').addClass('visible');

    $('#Helper').html('Mobile / Init()');
}

function UpdateScreen(operator) {
    $ActualSlide = $CibleSlide;

    var idx = $ListSlides.indexOf($ActualSlide);
    $CibleSlide = (operator === '+')
        ? $ListSlides[idx + 1]
        : $ListSlides[idx - 1];

    if (!$CibleSlide) {
        $ScrollState = false;
        $CibleSlide = $ActualSlide;
        $('#Helper').html('Break');
        return;
    }

    $('#Helper').html('Mobile: ' + $ActualSlide + ' → ' + $CibleSlide);

    var $ActualSlideDOM = $('.pane[data-id="' + $ActualSlide + '"]');
    var $CibleSlideDOM  = $('.pane[data-id="' + $CibleSlide + '"]');

    // Определяем, в одном ли .spane находятся текущий и целевой слайды
    var $actualSpane = $ActualSlideDOM.closest('.spane');
    var $cibleSpane  = $CibleSlideDOM.closest('.spane');

    var sameSpane = $actualSpane.length && $cibleSpane.length &&
                    $actualSpane[0] === $cibleSpane[0];

    if (sameSpane) {
        // === Случай 1: оба слайда в одном .spane → скроллим .spane горизонтально ===
        TweenMax.to($actualSpane, $ScrollSpeed, {
            scrollTo: $CibleSlideDOM,
            ease: Power2.easeOut,
            onComplete: function() {
                $ScrollState = false;
                $CibleSlideDOM.addClass('visible');
            }
        });
    } else {
        // === Случай 2: переход между разными .scr / .spane → скроллим #ScrollPane ===
        var $targetScr = $CibleSlideDOM.closest('.scr');
        if (!$targetScr.length) $targetScr = $CibleSlideDOM;

        TweenMax.to('#ScrollPane', $ScrollSpeed, {
            scrollTo: $targetScr,
            ease: Power2.easeOut,
            onComplete: function() {
                $ScrollState = false;
                $CibleSlideDOM.addClass('visible');
            }
        });
    }
}
