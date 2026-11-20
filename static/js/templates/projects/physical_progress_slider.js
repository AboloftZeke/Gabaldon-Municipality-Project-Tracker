document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-physical-progress-input]').forEach((input) => {
        const output = document.querySelector('[data-physical-progress-output]');
        if (!output) {
            return;
        }

        const updateOutput = () => {
            const value = input.value.trim();
            output.value = value === '' ? '' : `${value}%`;
            output.textContent = value === '' ? '' : `${value}%`;
        };

        input.addEventListener('input', updateOutput);
        updateOutput();
    });
});
