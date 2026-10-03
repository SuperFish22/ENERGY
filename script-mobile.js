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
    var isScrolling = false;   // блокировка во время анимации

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
                var $pane = $('.pane[data-id=' + $CibleSlide + ']');
                if ($pane.length) {
                    TweenMax.to('#ScrollPane', 0, {scrollTo: $pane});
                }
            }
        }, 250);
    });
});


/* ============================================================
   ОБЩИЕ ФУНКЦИИ — те же, что и в десктопной версии.
   ВАЖНО: если будешь править — правь в обоих файлах, либо
   вынеси их в отдельный script-common.js (см. ниже).
   ============================================================ */

function Init() {
    $ScrollSpeed = 0.4;   // на мобилке чуть быстрее — приятнее
    $ScrollState = false;
    $ActualSlide = $CibleSlide = $('.pane').first().attr('data-id');

    $ListSlides = [];
    $('.pane').each(function() {
        $ListSlides.push($(this).attr('data-id'));
    });

    $('#ScrollPane').scrollTop(0);
    $('.spane').scrollLeft(0);

    $('.visible').removeClass('visible');
    $('.pane').first().addClass('visible');

    $('#Helper').html('Mobile / Init()');
}

function UpdateScreen(operator) {
    $ActualSlide = $CibleSlide;

    var idx = $ListSlides.indexOf($ActualSlide);
    $CibleSlide = (operator === '+')
        ? $ListSlides[idx + 1]
        : $ListSlides[idx - 1];

    $('#Helper').html('Mobile: ' + $ActualSlide + ' → ' + $CibleSlide);

    if (!$CibleSlide) {
        $ScrollState = false;
        $('#Helper').html('Break');
        $CibleSlide = $ActualSlide;
        return;
    }

    var $ActualSlideDOM = $('.pane[data-id=' + $ActualSlide + ']');
    var $CibleSlideDOM   = $('.pane[data-id=' + $CibleSlide + ']');

    // Горизонтальный блок
    if ($ActualSlideDOM.closest('.prt').find('.spane').length &&
        ((operator === '+' && $ActualSlideDOM.next('.pane').length) ||
         (operator === '-' && $ActualSlideDOM.prev('.pane').length))) {

        TweenMax.to($ActualSlideDOM.closest('.spane'), $ScrollSpeed, {
            scrollTo: '.pane[data-id=' + $CibleSlide + ']',
            ease: Power2.easeOut,
            onComplete: function() {
                $ScrollState = false;
                $CibleSlideDOM.addClass('visible');
            }
        });
    } else {
        TweenMax.to('#ScrollPane', $ScrollSpeed, {
            scrollTo: '.pane[data-id=' + $CibleSlide + ']',
            ease: Power2.easeOut,
            onComplete: function() {
                $ScrollState = false;
                $CibleSlideDOM.addClass('visible');
            }
        });
    }
}