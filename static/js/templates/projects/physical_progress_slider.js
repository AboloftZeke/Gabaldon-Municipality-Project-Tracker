document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-progress-slider]').forEach((input) => {
        const output = input.parentElement.querySelector('[data-progress-output]');
        if (!output) {
            return;
        }

        const updateOutput = () => {
            output.value = `${input.value}%`;
            output.textContent = `${input.value}%`;
        };

        input.addEventListener('input', updateOutput);
        updateOutput();
    });
});
