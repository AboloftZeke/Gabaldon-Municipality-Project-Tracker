document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('publication-submit-form');
    const trigger = form?.querySelector('[data-publication-submit-trigger]');
    const modal = document.querySelector('[data-publication-submit-modal]');
    if (!form || !trigger || !modal) return;

    const dialog = modal.querySelector('.publication-submit-confirm__dialog');
    const confirmButton = modal.querySelector('[data-publication-submit-confirm]');
    const cancelButtons = modal.querySelectorAll('[data-publication-submit-cancel]');
    let previouslyFocused = null;
    let submitting = false;

    const closeModal = () => {
        if (submitting) return;
        modal.hidden = true;
        document.body.classList.remove('publication-submit-confirm-open');
        if (previouslyFocused) previouslyFocused.focus();
    };

    const openModal = () => {
        if (submitting) return;
        previouslyFocused = document.activeElement;
        modal.hidden = false;
        document.body.classList.add('publication-submit-confirm-open');
        dialog.focus();
    };

    form.addEventListener('submit', (event) => {
        if (submitting) return;
        event.preventDefault();
        openModal();
    });

    cancelButtons.forEach((button) => button.addEventListener('click', closeModal));

    confirmButton.addEventListener('click', () => {
        if (submitting) return;
        submitting = true;
        trigger.disabled = true;
        confirmButton.disabled = true;
        cancelButtons.forEach((button) => { button.disabled = true; });
        form.submit();
    });

    document.addEventListener('keydown', (event) => {
        if (!modal.hidden && event.key === 'Escape') closeModal();
    });
});
