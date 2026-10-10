(function () {
    document.querySelectorAll('[data-progress-slider]').forEach(function (slider) {
        const output = document.querySelector(
            '[data-progress-output][for="' + slider.id + '"]',
        );

        if (!output) {
            return;
        }

        function updateOutput() {
            const percentage = String(Number(slider.value));
            output.value = percentage + '%';
            slider.setAttribute('aria-valuetext', percentage + '%');
        }

        slider.addEventListener('input', updateOutput);
        updateOutput();
    });
})();
