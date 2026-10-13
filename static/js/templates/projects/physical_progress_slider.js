document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-physical-progress-slider]').forEach((slider) => {
        const output = document.querySelector('[data-physical-progress-output]');
        if (!output) {
            return;
        }

        const updateOutput = () => {
            output.value = `${slider.value}%`;
            output.textContent = `${slider.value}%`;
        };

        slider.addEventListener('input', updateOutput);
        updateOutput();
    });
});
