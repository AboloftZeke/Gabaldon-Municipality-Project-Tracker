document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-toast]').forEach((toast) => {
        const dismiss = toast.querySelector('[data-toast-dismiss]');
        let timer;
        const close = () => {
            window.clearTimeout(timer);
            toast.remove();
        };
        const start = () => {
            // Errors stay available until dismissed; other messages remain readable.
            if (!toast.classList.contains('ui-toast--error')) {
                timer = window.setTimeout(close, 10000);
            }
        };
        dismiss.addEventListener('click', close);
        toast.addEventListener('mouseenter', () => window.clearTimeout(timer));
        toast.addEventListener('mouseleave', start);
        toast.addEventListener('focusin', () => window.clearTimeout(timer));
        toast.addEventListener('focusout', start);
        start();
    });
});
