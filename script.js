// ===== Инициализация =====
Init();

// Определяем тач-устройство
var isTouchDevice = ('ontouchstart' in window) &&
                    (navigator.maxTouchPoints > 0) &&
                    !window.matchMedia('(pointer: fine)').matches;

// ===== Mouse Wheel (десктоп) =====
if (!isTouchDevice && typeof $.fn.mousewheel === 'function') {
    $('.pane, .scrzone').mousewheel(function(event) {
        event.preventDefault();
        if (!$ScrollState) {
            $ScrollState = true;
            if (event.deltaY < 0) {
                UpdateScreen('+');
            } else if (event.deltaY > 0) {
                UpdateScreen('-');
            } else {
                $ScrollState = false;
            }
        }
    });
}

// ===== Touch (мобилки и тачпады) =====
if (isTouchDevice) {
    var touchStartY = 0;
    var touchStartX = 0;
    var touchThreshold = 50;

    $(document).on('touchstart', function(e) {
        if (e.originalEvent.touches.length === 1) {
            touchStartY = e.originalEvent.touches[0].clientY;
            touchStartX = e.originalEvent.touches[0].clientX;
        }
    });

    $(document).on('touchend', function(e) {
        if ($ScrollState) return;

        var touchEndY = e.originalEvent.changedTouches[0].clientY;
        var touchEndX = e.originalEvent.changedTouches[0].clientX;

        var deltaY = touchStartY - touchEndY;
        var deltaX = touchStartX - touchEndX;

        if (Math.abs(deltaY) > Math.abs(deltaX)) {
            if (Math.abs(deltaY) > touchThreshold) {
                $ScrollState = true;
                UpdateScreen(deltaY > 0 ? '+' : '-');
            }
        } else {
            if (Math.abs(deltaX) > touchThreshold) {
                $ScrollState = true;
                UpdateScreen(deltaX > 0 ? '-' : '+');
            }
        }
    });
}

// ===== Функция Init =====
function Init() {
    $ScrollSpeed = 0.3;
    $ScrollState = false;
    $ActualSlide = $CibleSlide = $('.pane').first().attr('data-id');

    $ListSlides = [];
    $('.pane').each(function() {
        $ListSlides.push($(this).attr('data-id'));
    });

    // Стартовая позиция — начало документа и начало всех .spane
    $('#ScrollPane').scrollTop(0);
    $('.spane').scrollLeft(0);

    $('.visible').removeClass('visible');
    $('.pane').first().addClass('visible');

    $('#Helper').html('Init()');
}

// ===== Основная функция переключения слайдов =====
function UpdateScreen(operator) {
    $ActualSlide = $CibleSlide;

    var idx = $ListSlides.indexOf($ActualSlide);
    $CibleSlide = (operator === '+')
        ? $ListSlides[idx + 1]
        : $ListSlides[idx - 1];

    $('#Helper').html('From <strong>' + $ActualSlide + '</strong> to <strong>' + $CibleSlide + '</strong>');

    // Если слайда нет — стоп
    if (!$CibleSlide) {
        $ScrollState = false;
        $('#Helper').html('Break');
        $CibleSlide = $ActualSlide;
        return;
    }

    var $ActualSlideDOM = $('.pane[data-id=' + $ActualSlide + ']');
    var $CibleSlideDOM   = $('.pane[data-id=' + $CibleSlide + ']');

    // Случай 1: горизонтальный блок (.horiz) — скроллим .spane по горизонтали
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
    }
    // Случай 2: обычная вертикальная прокрутка — скроллим #ScrollPane
    else {
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

// ===== Resize — без сброса на первый слайд =====
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
