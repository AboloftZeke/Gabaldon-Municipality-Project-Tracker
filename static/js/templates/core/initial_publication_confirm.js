document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('initial-publication-form');
    const trigger = document.querySelector('[data-initial-publication-trigger]');
    const modal = document.querySelector('[data-initial-publication-modal]');
    if (!form || !trigger || !modal) return;

    const dialog = modal.querySelector('.initial-publication-confirm__dialog');
    const confirmButton = modal.querySelector('[data-initial-publication-confirm]');
    const cancelButtons = modal.querySelectorAll('[data-initial-publication-cancel]');
    let previouslyFocused = null;
    let submitting = false;

    const closeModal = () => {
        if (submitting) return;
        modal.hidden = true;
        document.body.classList.remove('initial-publication-confirm-open');
        if (previouslyFocused) previouslyFocused.focus();
    };

    const openModal = () => {
        if (submitting) return;
        previouslyFocused = document.activeElement;
        modal.hidden = false;
        document.body.classList.add('initial-publication-confirm-open');
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
