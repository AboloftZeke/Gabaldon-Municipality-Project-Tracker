document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('.operational-form');
    const trigger = document.querySelector('[data-progress-submit-trigger]');
    const modal = document.querySelector('[data-progress-submit-confirm]');
    if (!form || !trigger || !modal) return;

    const dialog = modal.querySelector('.progress-submit-confirm__dialog');
    const confirmButton = modal.querySelector('[data-progress-submit-confirm]');
    const cancelButtons = modal.querySelectorAll('[data-progress-submit-cancel]');
    let previouslyFocused = null;
    let submitting = false;

    const closeModal = () => {
        if (submitting) return;
        modal.hidden = true;
        document.body.classList.remove('progress-submit-confirm-open');
        if (previouslyFocused) previouslyFocused.focus();
    };

    trigger.addEventListener('click', (event) => {
        event.preventDefault();
        if (submitting) return;
        previouslyFocused = document.activeElement;
        modal.hidden = false;
        document.body.classList.add('progress-submit-confirm-open');
        dialog.focus();
    });

    cancelButtons.forEach((button) => button.addEventListener('click', closeModal));

    confirmButton.addEventListener('click', () => {
        if (submitting) return;
        if (!form.checkValidity()) {
            closeModal();
            form.reportValidity();
            return;
        }
        submitting = true;
        confirmButton.disabled = true;
        cancelButtons.forEach((button) => { button.disabled = true; });
        trigger.disabled = true;
        form.requestSubmit();
    });

    form.addEventListener('submit', (event) => {
        if (!submitting) {
            event.preventDefault();
            trigger.click();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (!modal.hidden && event.key === 'Escape') closeModal();
    });
});
