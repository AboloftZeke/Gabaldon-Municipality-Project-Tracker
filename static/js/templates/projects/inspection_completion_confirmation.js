(() => {
    const form = document.querySelector(
        'form[data-completion-confirmation-form]',
    );
    const dialog = document.querySelector('[data-completion-dialog]');
    if (!form || !dialog) return;

    const progress = form.querySelector('[data-completion-progress]');
    const confirmation = form.querySelector('[name="completion_confirmation"]');
    const confirmButton = dialog.querySelector('[data-confirm-completion]');
    const cancelButton = dialog.querySelector('[data-cancel-completion]');
    if (!progress || !confirmation || !confirmButton || !cancelButton) return;

    form.addEventListener('submit', event => {
        if (Number(progress.value) !== 100 || confirmation.value === 'yes') {
            return;
        }

        event.preventDefault();
        if (typeof dialog.showModal === 'function') {
            dialog.showModal();
            return;
        }

        if (window.confirm('Are you sure that the project is completed?')) {
            confirmation.value = 'yes';
            form.requestSubmit();
        }
    });

    confirmButton.addEventListener('click', () => {
        confirmation.value = 'yes';
        dialog.close();
        form.requestSubmit();
    });

    cancelButton.addEventListener('click', () => {
        dialog.close();
        progress.focus();
    });
})();
