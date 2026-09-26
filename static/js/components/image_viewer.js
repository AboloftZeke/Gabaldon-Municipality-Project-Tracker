(function () {
    'use strict';
    const viewer = document.querySelector('[data-image-viewer]');
    if (!viewer) return;

    const image = viewer.querySelector('[data-image-viewer-image]');
    const caption = viewer.querySelector('[data-image-viewer-caption]');
    const closeButton = viewer.querySelector('.image-viewer__close');
    let opener = null;

    function closeViewer() {
        if (viewer.hidden) return;
        viewer.hidden = true;
        image.removeAttribute('src');
        image.alt = '';
        caption.textContent = '';
        document.body.classList.remove('image-viewer-open');
        if (opener && opener.isConnected) opener.focus();
        opener = null;
    }

    document.addEventListener('click', function (event) {
        const trigger = event.target.closest('[data-image-viewer-trigger]');
        if (trigger && !viewer.contains(trigger)) {
            const src = trigger.dataset.imageSrc;
            if (!src) return;
            event.preventDefault();
            opener = trigger;
            image.src = src;
            image.alt = trigger.dataset.imageAlt || trigger.querySelector('img')?.alt || 'Project image';
            caption.textContent = trigger.dataset.imageCaption || image.alt;
            viewer.hidden = false;
            document.body.classList.add('image-viewer-open');
            closeButton.focus();
        } else if (event.target.closest('[data-image-viewer-close]')) {
            closeViewer();
        }
    });

    viewer.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            closeViewer();
        } else if (event.key === 'Tab') {
            // The close button is the only focusable element inside the dialog.
            event.preventDefault();
            closeButton.focus();
        }
    });
})();
