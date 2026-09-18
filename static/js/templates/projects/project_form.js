document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('[data-project-wizard], [data-infrastructure-wizard]');
    if (!form) return;

    const panels = Array.from(form.querySelectorAll('[data-wizard-step]'));
    const indicators = Array.from(form.querySelectorAll('[data-wizard-indicator]'));
    const backButton = form.querySelector('[data-wizard-back]');
    const nextButton = form.querySelector('[data-wizard-next]');
    const submitButton = form.querySelector('[data-wizard-submit]');
    const progressText = form.querySelector('[data-wizard-progress-text]');
    const progressDetail = form.querySelector('[data-wizard-progress-detail]');
    const reviewPanel = form.querySelector('[data-review-panel]');
    if (!panels.length || !backButton || !nextButton || !submitButton) return;

    let activeStep = 0;
    let hasUnsavedChanges = false;
    let isSubmitting = false;
    const firstError = form.querySelector('.form-group.has-error');
    if (firstError) {
        const errorPanel = firstError.closest('[data-wizard-step]');
        if (errorPanel) activeStep = Number(errorPanel.dataset.wizardStep) || 0;
    }

    function fieldValue(field) {
        if (!field) return 'Not provided';
        if (field.type === 'file') {
            const count = field.files ? field.files.length : 0;
            return count ? `${count} new photo${count === 1 ? '' : 's'}` : 'No new photos';
        }
        if (field.tagName === 'SELECT') {
            const option = field.options[field.selectedIndex];
            return option && option.value ? option.text.trim() : 'Not provided';
        }
        if (field.type === 'checkbox') return field.checked ? 'Yes' : 'No';
        return field.value.trim() || 'Not provided';
    }

    function updateReview() {
        if (!reviewPanel) return;
        reviewPanel.querySelectorAll('[data-review-value]').forEach(function (output) {
            output.textContent = fieldValue(document.getElementById(output.dataset.reviewValue));
        });
    }

    function showStep(stepIndex, options) {
        const settings = options || {};
        activeStep = Math.max(0, Math.min(stepIndex, panels.length - 1));
        if (panels[activeStep] === reviewPanel) updateReview();

        panels.forEach(function (panel, index) {
            const isActive = index === activeStep;
            panel.hidden = !isActive;
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });
        indicators.forEach(function (indicator, index) {
            indicator.classList.toggle('is-active', index === activeStep);
            indicator.classList.toggle('is-complete', index < activeStep);
            indicator.classList.toggle('is-future', index > activeStep);
            if (index === activeStep) indicator.setAttribute('aria-current', 'step');
            else indicator.removeAttribute('aria-current');
        });

        backButton.hidden = activeStep === 0;
        nextButton.hidden = activeStep === panels.length - 1;
        submitButton.hidden = activeStep !== panels.length - 1;
        if (progressText) progressText.textContent = `Step ${activeStep + 1} of ${panels.length}`;
        if (progressDetail) {
            const label = indicators[activeStep] && indicators[activeStep].querySelector('strong');
            progressDetail.textContent = label ? label.textContent.trim() : 'Complete each step to continue';
        }

        if (settings.focusPanel) {
            const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            panels[activeStep].scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
            const focusTarget = panels[activeStep].querySelector(
                '.has-error input:not([type="hidden"]), .has-client-error input:not([type="hidden"]), input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="-1"]'
            );
            if (focusTarget) {
                window.setTimeout(function () { focusTarget.focus({ preventScroll: true }); }, reducedMotion ? 0 : 180);
            }
        }
    }

    function clearFieldError(field) {
        const group = field.closest('.form-group');
        if (!group) return;
        field.removeAttribute('aria-invalid');
        const message = group.querySelector(`[data-client-error-for="${field.id}"]`);
        if (message) message.remove();
        if (!group.querySelector('.client-error-message')) {
            group.classList.remove('has-client-error');
        }
    }

    function showFieldError(field) {
        const group = field.closest('.form-group');
        if (!group) {
            field.reportValidity();
            return;
        }
        group.classList.add('has-client-error');
        field.setAttribute('aria-invalid', 'true');
        let message = group.querySelector(`[data-client-error-for="${field.id}"]`);
        if (!message) {
            message = document.createElement('div');
            message.className = 'error-message client-error-message';
            message.setAttribute('role', 'alert');
            message.dataset.clientErrorFor = field.id;
            group.appendChild(message);
        }
        message.textContent = field.validity.valueMissing
            ? 'This field is required before you continue.'
            : field.validationMessage;
    }

    function panelFields(panel) {
        return Array.from(panel.querySelectorAll(
            'input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled)'
        ));
    }

    function validatePanel(panel) {
        let firstInvalid = null;
        panelFields(panel).forEach(function (field) {
            if (field.checkValidity()) clearFieldError(field);
            else {
                showFieldError(field);
                firstInvalid = firstInvalid || field;
            }
        });
        if (firstInvalid) {
            firstInvalid.focus();
            return false;
        }
        return true;
    }

    backButton.addEventListener('click', function () { showStep(activeStep - 1, { focusPanel: true }); });
    nextButton.addEventListener('click', function () {
        if (validatePanel(panels[activeStep])) showStep(activeStep + 1, { focusPanel: true });
    });

    form.querySelectorAll('input, select, textarea').forEach(function (field) {
        ['input', 'change'].forEach(function (eventName) {
            field.addEventListener(eventName, function () {
                hasUnsavedChanges = true;
                if (field.checkValidity()) clearFieldError(field);
            });
        });
    });

    form.addEventListener('submit', function (event) {
        const editablePanels = panels.filter(function (panel) { return panel !== reviewPanel; });
        const invalidIndex = editablePanels.findIndex(function (panel) { return !validatePanel(panel); });
        if (invalidIndex !== -1) {
            event.preventDefault();
            showStep(invalidIndex, { focusPanel: true });
            return;
        }
        isSubmitting = true;
        hasUnsavedChanges = false;
        submitButton.disabled = true;
        submitButton.setAttribute('aria-busy', 'true');
        submitButton.textContent = submitButton.dataset.savingText || 'Saving...';
    });

    window.addEventListener('beforeunload', function (event) {
        if (!hasUnsavedChanges || isSubmitting) return;
        event.preventDefault();
        event.returnValue = '';
    });

    showStep(activeStep, { focusPanel: Boolean(firstError) });
});
