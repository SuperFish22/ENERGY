Init();

// ====== Настройки ======
var SCROLL_SPEED    = 0.5;   // скорость анимации
var SWIPE_THRESHOLD = 50;    // минимальная длина свайпа в px

// ====== Состояние ======
var ScrollState = false;
var ActualSlide, CibleSlide, ListSlides = [];

// ====== Инициализация ======
function Init() {
    ScrollState = false;
    ActualSlide = CibleSlide = $('.pane').first().attr('data-id');
    ListSlides = [];
    $('.pane').each(function () {
        ListSlides.push($(this).attr('data-id'));
    });
    TweenMax.to(window, 0, { scrollTo: 0 });
    TweenMax.to('.spane', 0, { scrollTo: { y: 0, x: 0 } });
    $('.visible').removeClass('visible');
    $('#Helper').html('Init()');
}

// ====== Переключение слайда ======
function UpdateScreen(operator) {
    ActualSlide = CibleSlide;
    if (operator === '+') {
        CibleSlide = ListSlides[ListSlides.indexOf(ActualSlide) + 1];
    } else {
        CibleSlide = ListSlides[ListSlides.indexOf(ActualSlide) - 1];
    }
    $('#Helper').html('From <strong>' + ActualSlide + '</strong> to <strong>' + CibleSlide + '</strong>');

    if (!CibleSlide) {
        ScrollState = false;
        $('#Helper').html('Break');
        CibleSlide = ActualSlide;
        return;
    }

    var ActualSlideDOM = $('.pane[data-id=' + ActualSlide + ']');
    var CibleSlideDOM  = $('.pane[data-id=' + CibleSlide + ']');

    // Внутри одного .prt — горизонтальный или вертикальный сплит
    if (
        ActualSlideDOM.closest('.prt').find('.spane').length &&
        ((operator === '+' && ActualSlideDOM.next('.pane').length) ||
         (operator === '-' && ActualSlideDOM.prev('.pane').length))
    ) {
        TweenMax.to(ActualSlideDOM.closest('.spane'), SCROLL_SPEED, {
            scrollTo: '.pane[data-id=' + CibleSlide + ']',
            ease: Power2.easeOut,
            onComplete: function () {
                ScrollState = false;
                CibleSlideDOM.addClass('visible');
            }
        });
    } else {
        TweenMax.to(window, SCROLL_SPEED, {
            scrollTo: '.pane[data-id=' + CibleSlide + ']',
            ease: Power2.easeOut,
            onComplete: function () {
                ScrollState = false;
                CibleSlideDOM.addClass('visible');
            }
        });
    }
}

// ====== Колесо мыши (десктоп) ======
$('.pane, .scrzone').on('mousewheel', function (event) {
    event.preventDefault();
    if (ScrollState === true) return;

    ScrollState = true;
    if (event.deltaY < 0) {
        UpdateScreen('+');
    } else if (event.deltaY > 0) {
        UpdateScreen('-');
    } else {
        ScrollState = false;
    }
});

// ====== Свайпы (только если есть тач) ======
if ('ontouchstart' in window || navigator.maxTouchPoints > 0) {
    var touchStartX = 0, touchStartY = 0, touchActive = false;

    document.addEventListener('touchstart', function (e) {
        if (e.touches.length !== 1) { touchActive = false; return; }
        touchActive = true;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        if (!touchActive || ScrollState === true) return;
        if (e.cancelable) e.preventDefault();
    }, { passive: false });

    document.addEventListener('touchend', function (e) {
        if (!touchActive) return;
        touchActive = false;
        if (ScrollState === true) return;

        var touch = e.changedTouches[0];
        var dx = touch.clientX - touchStartX;
        var dy = touch.clientY - touchStartY;
        var absX = Math.abs(dx);
        var absY = Math.abs(dy);

        if (Math.max(absX, absY) < SWIPE_THRESHOLD) return;

        ScrollState = true;

        if (absY > absX) {
            // Вертикальный свайп
            if (dy < 0) UpdateScreen('+');
            else        UpdateScreen('-');
        } else {
            // Горизонтальный свайп — только внутри сплитов
            var inSplit = $(e.target).closest('.spane').length > 0;
            if (!inSplit) { ScrollState = false; return; }
            if (dx < 0) UpdateScreen('+');
            else        UpdateScreen('-');
        }
    }, { passive: true });
}

// ====== Init() при ресайзе и повороте ======
$(window).on('resize orientationchange', function () {
    Init();
});
