/* ============================================================
   DESKTOP SCRIPT — управление мышью и колесом
   ============================================================ */

// Сначала подгружаем плагин mousewheel (он нужен только на ПК)
(function loadMousewheel(callback) {
    var s = document.createElement('script');
    s.src = './lib/jquery.mousewheel.min.js';
    s.onload = callback;
    s.onerror = function() {
        console.error('Не удалось загрузить jquery.mousewheel.min.js');
    };
    document.body.appendChild(s);
})(function() {

    // ===== Инициализация =====
    Init();

    // ===== Mouse Wheel =====
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

    // ===== Клавиатура — бонус для ПК =====
    $(document).on('keydown', function(e) {
        if ($ScrollState) return;
        if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ') {
            e.preventDefault();
            $ScrollState = true;
            UpdateScreen('+');
        } else if (e.key === 'ArrowUp' || e.key === 'PageUp') {
            e.preventDefault();
            $ScrollState = true;
            UpdateScreen('-');
        }
    });

    // ===== Resize =====
    var resizeTimer;
    $(window).on('resize', function() {
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
   ОБЩИЕ ФУНКЦИИ (используются и на ПК, и на мобилке)
   ============================================================ */

function Init() {
    $ScrollSpeed = 0.3;
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

    $('#Helper').html('Desktop / Init()');
}

function UpdateScreen(operator) {
    $ActualSlide = $CibleSlide;

    var idx = $ListSlides.indexOf($ActualSlide);
    $CibleSlide = (operator === '+')
        ? $ListSlides[idx + 1]
        : $ListSlides[idx - 1];

    $('#Helper').html('Desktop: ' + $ActualSlide + ' → ' + $CibleSlide);

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