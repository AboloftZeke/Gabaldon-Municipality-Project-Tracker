document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('[data-infrastructure-wizard]');

    if (!form) {
        return;
    }

    const panels = Array.from(form.querySelectorAll('[data-wizard-step]'));
    const indicators = Array.from(form.querySelectorAll('[data-wizard-indicator]'));
    const backButton = form.querySelector('[data-wizard-back]');
    const nextButton = form.querySelector('[data-wizard-next]');
    const submitButton = form.querySelector('[data-wizard-submit]');
    const progressText = form.querySelector('[data-wizard-progress-text]');

    if (!panels.length || !backButton || !nextButton || !submitButton) {
        return;
    }

    let activeStep = 0;
    const firstError = form.querySelector('.form-group.has-error');

    if (firstError) {
        const errorPanel = firstError.closest('[data-wizard-step]');
        if (errorPanel) {
            activeStep = Number(errorPanel.dataset.wizardStep) || 0;
        }
    }

    function showStep(stepIndex, options) {
        const settings = options || {};
        activeStep = Math.max(0, Math.min(stepIndex, panels.length - 1));

        panels.forEach(function (panel, index) {
            const isActive = index === activeStep;
            panel.hidden = !isActive;
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });

        indicators.forEach(function (indicator, index) {
            indicator.classList.toggle('is-active', index === activeStep);
            indicator.classList.toggle('is-complete', index < activeStep);
            if (index === activeStep) {
                indicator.setAttribute('aria-current', 'step');
            } else {
                indicator.removeAttribute('aria-current');
            }
        });

        backButton.hidden = activeStep === 0;
        nextButton.hidden = activeStep === panels.length - 1;
        submitButton.hidden = activeStep !== panels.length - 1;

        if (progressText) {
            progressText.textContent = `Step ${activeStep + 1} of ${panels.length}`;
        }

        if (settings.focusPanel) {
            panels[activeStep].scrollIntoView({ behavior: 'smooth', block: 'start' });
            const focusTarget = panels[activeStep].querySelector(
                '.has-error input:not([type="hidden"]), .has-error select, .has-error textarea, input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled)'
            );
            if (focusTarget) {
                window.setTimeout(function () {
                    focusTarget.focus({ preventScroll: true });
                }, 250);
            }
        }
    }

    function validateActiveStep() {
        const fields = Array.from(panels[activeStep].querySelectorAll(
            'input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled)'
        ));
        const invalidField = fields.find(function (field) {
            return !field.checkValidity();
        });

        if (!invalidField) {
            return true;
        }

        invalidField.reportValidity();
        invalidField.focus();
        return false;
    }

    backButton.addEventListener('click', function () {
        showStep(activeStep - 1, { focusPanel: true });
    });

    nextButton.addEventListener('click', function () {
        if (validateActiveStep()) {
            showStep(activeStep + 1, { focusPanel: true });
        }
    });

    showStep(activeStep, { focusPanel: Boolean(firstError) });
});
