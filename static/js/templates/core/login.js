(function () {
    const frame = document.getElementById('slideFrame');
    const caption = document.getElementById('slideCaption');
    const dotsWrap = document.getElementById('slideDots');

    if (!frame || !caption || !dotsWrap) {
        return;
    }

    const slides = Array.from(frame.querySelectorAll('img'));
    if (slides.length === 0) {
        return;
    }

    const validSlides = () => slides.filter((img) => !img.hidden && img.dataset.failed !== 'true');

    slides.forEach((slide) => {
        slide.addEventListener('error', () => {
            slide.dataset.failed = 'true';
            slide.hidden = true;
            slide.classList.remove('is-active');

            const available = validSlides();
            if (available.length === 0) {
                caption.textContent = '';
            } else if (!available.some((img) => img.classList.contains('is-active'))) {
                const first = available[0];
                first.classList.add('is-active');
                caption.textContent = first.dataset.caption || '';
            }
        });

        slide.addEventListener('load', () => {
            slide.dataset.failed = 'false';
            slide.hidden = false;
        });
    });

    slides.forEach((_, index) => {
        const dot = document.createElement('span');
        dot.className = 'slide-dot' + (index === 0 ? ' is-active' : '');
        dotsWrap.appendChild(dot);
    });

    const dots = Array.from(dotsWrap.children);
    let current = 0;

    const activate = (index) => {
        if (slides[current] && slides[current].dataset.failed !== 'true') {
            slides[current].classList.remove('is-active');
        }
        if (dots[current]) {
            dots[current].classList.remove('is-active');
        }

        current = index;

        if (slides[current] && slides[current].dataset.failed !== 'true') {
            slides[current].classList.add('is-active');
            caption.textContent = slides[current].dataset.caption || '';
        }

        if (dots[current]) {
            dots[current].classList.add('is-active');
        }
    };

    window.setTimeout(() => {
        const available = validSlides();

        if (available.length === 0) {
            return;
        }

        const firstAvailableIndex = slides.indexOf(available[0]);
        if (firstAvailableIndex !== 0) {
            activate(firstAvailableIndex);
        } else {
            caption.textContent = slides[0].dataset.caption || '';
        }

        if (available.length > 1) {
            window.setInterval(() => {
                const currentAvailable = validSlides();
                if (currentAvailable.length <= 1) {
                    return;
                }

                const currentPos = currentAvailable.indexOf(slides[current]);
                const nextSlide = currentAvailable[(currentPos + 1) % currentAvailable.length];
                activate(slides.indexOf(nextSlide));
            }, 5000);
        }
    }, 0);
})();

(function () {
    const passwordInput = document.getElementById('password');
    const toggleButton = document.getElementById('togglePassword');
    const toggleIcon = document.getElementById('passwordToggleIcon');

    if (!passwordInput || !toggleButton || !toggleIcon) {
        return;
    }

    const viewIcon = toggleButton.dataset.viewIcon || toggleIcon.src;
    const hideIcon = toggleButton.dataset.hideIcon || toggleIcon.src;

    toggleButton.addEventListener('click', (e) => {
        e.preventDefault();
        const isPassword = passwordInput.type === 'password';
        passwordInput.type = isPassword ? 'text' : 'password';
        toggleIcon.src = isPassword ? hideIcon : viewIcon;
        toggleIcon.alt = isPassword ? 'Hide password' : 'Show password';
    });
})();
