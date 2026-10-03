console.log('mobile script loaded');

$(document).ready(function() {
    console.log('DOM ready');

    // Инициализация
    $ScrollSpeed = 0.4;
    $ScrollState = false;

    $ListSlides = [];
    $('.pane[data-id]').each(function() {
        $ListSlides.push($(this).attr('data-id'));
    });

    $ActualSlide = $CibleSlide = $ListSlides[0];
    console.log('slides:', $ListSlides);

    var touchStartY = 0;
    var touchStartX = 0;
    var touchThreshold = 40;

    document.addEventListener('touchstart', function(e) {
        console.log('touchstart');
        if (e.touches.length !== 1) return;
        touchStartY = e.touches[0].clientY;
        touchStartX = e.touches[0].clientX;
    }, { passive: true });

    document.addEventListener('touchend', function(e) {
        console.log('touchend');
        if ($ScrollState) return;

        var t = e.changedTouches[0];
        var deltaY = touchStartY - t.clientY;
        var deltaX = touchStartX - t.clientX;

        console.log('deltaY:', deltaY, 'deltaX:', deltaX);

        if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > touchThreshold) {
            $ScrollState = true;
            console.log('swipe', deltaY > 0 ? '+' : '-');
            nextSlide(deltaY > 0 ? '+' : '-');
        }
    }, { passive: true });
});

function nextSlide(operator) {
    var idx = $ListSlides.indexOf($CibleSlide);
    var next = (operator === '+') ? $ListSlides[idx + 1] : $ListSlides[idx - 1];

    console.log('nextSlide:', $CibleSlide, '→', next);

    if (!next) {
        $ScrollState = false;
        return;
    }

    $ActualSlide = $CibleSlide;
    $CibleSlide = next;

    var $target = $('.pane[data-id="' + next + '"]');
    var $scr = $target.closest('.scr');
    if (!$scr.length) $scr = $target;

    TweenMax.to('#ScrollPane', 0.4, {
        scrollTo: $scr,
        ease: Power2.easeOut,
        onComplete: function() {
            $ScrollState = false;
            $target.addClass('visible');
        }
    });
}
