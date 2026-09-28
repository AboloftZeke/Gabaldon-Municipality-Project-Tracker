(function () {
    const modal = document.querySelector('[data-logout-confirm]');

    if (!modal) {
        return;
    }

    const dialog = modal.querySelector('.logout-confirm__dialog');
    const proceedButton = modal.querySelector('[data-logout-proceed]');
    const cancelButtons = modal.querySelectorAll('[data-logout-cancel]');
    let logoutUrl = '';
    let previouslyFocused = null;

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove('logout-confirm-open');
        if (previouslyFocused) {
            previouslyFocused.focus();
        }
    }

    function openModal(link) {
        logoutUrl = link.href;
        previouslyFocused = document.activeElement;
        modal.hidden = false;
        document.body.classList.add('logout-confirm-open');
        dialog.focus();
    }

    document.querySelectorAll('a[href$="/logout/"]').forEach((link) => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            openModal(link);
        });
    });

    cancelButtons.forEach((button) => {
        button.addEventListener('click', closeModal);
    });

    proceedButton.addEventListener('click', () => {
        if (logoutUrl) {
            window.location.assign(logoutUrl);
        }
    });

    document.addEventListener('keydown', (event) => {
        if (modal.hidden) {
            return;
        }

        if (event.key === 'Escape') {
            closeModal();
        }
    });
})();
