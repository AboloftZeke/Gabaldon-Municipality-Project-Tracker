(function () {
    function setupPasswordToggle(button) {
        const targetId = button.dataset.passwordToggle;
        const input = targetId ? document.getElementById(targetId) : null;
        const icon = button.querySelector('img');

        if (!input || !icon) {
            return;
        }

        const viewIcon = button.dataset.viewIcon || icon.src;
        const hideIcon = button.dataset.hideIcon || icon.src;

        const syncState = () => {
            const isVisible = input.type === 'text';
            icon.src = isVisible ? hideIcon : viewIcon;
            icon.alt = isVisible ? 'Hide password' : 'Show password';
            button.setAttribute('aria-label', isVisible ? 'Hide password' : 'Show password');
            button.setAttribute('aria-pressed', isVisible ? 'true' : 'false');
        };

        button.addEventListener('click', (event) => {
            event.preventDefault();
            input.type = input.type === 'password' ? 'text' : 'password';
            syncState();
            input.focus({ preventScroll: true });
        });

        syncState();
    }

    document.querySelectorAll('[data-password-toggle]').forEach(setupPasswordToggle);
})();
