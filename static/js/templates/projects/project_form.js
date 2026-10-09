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
    const durationOutput = form.querySelector('[data-planned-duration-output]');
    const plannedStartDate = form.querySelector('[name="planned_start_date"]');
    const plannedEndDate = form.querySelector('[name="planned_end_date"]');
    if (!panels.length || !backButton || !nextButton || !submitButton) return;

    function updatePlannedDuration() {
        if (!durationOutput || !plannedStartDate || !plannedEndDate) return;

        const start = plannedStartDate.value;
        const end = plannedEndDate.value;
        durationOutput.removeAttribute('data-duration-invalid');
        if (!start || !end) {
            durationOutput.textContent = 'Enter both planned dates';
            return;
        }

        const [startYear, startMonth, startDay] = start.split('-').map(Number);
        const [endYear, endMonth, endDay] = end.split('-').map(Number);
        const startTime = Date.UTC(startYear, startMonth - 1, startDay);
        const endTime = Date.UTC(endYear, endMonth - 1, endDay);
        const duration = Math.round((endTime - startTime) / 86400000) + 1;
        if (duration < 1) {
            durationOutput.textContent = 'End date must be on or after start date';
            durationOutput.setAttribute('data-duration-invalid', 'true');
            return;
        }
        durationOutput.textContent = `${duration} ${duration === 1 ? 'day' : 'days'}`;
    }

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
            const field = document.getElementById(output.dataset.reviewValue);
            const currencyFields = new Set(['abc_amount', 'contract_price', 'actual_expenditure', 'project_cost']);
            if (field && currencyFields.has(field.name) && field.value.trim() !== '' &&
                Number.isFinite(Number(field.value))) {
                output.textContent = '₱' + Number(field.value).toLocaleString('en-PH', {
                    minimumFractionDigits: 2, maximumFractionDigits: 2,
                });
            } else {
                output.textContent = fieldValue(field);
            }
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

    function showFieldError(field, customMessage, isProcurementDateError) {
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
        if (isProcurementDateError) message.dataset.procurementDateError = 'true';
        message.textContent = customMessage || (field.validity.valueMissing
            ? 'This field is required before you continue.'
            : field.validationMessage);
    }

    function panelFields(panel) {
        return Array.from(panel.querySelectorAll(
            'input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled)'
        ));
    }

    function validateProcurementDates(panel) {
        if (!panel.hasAttribute('data-procurement-date-validation')) return null;

        const milestones = [
            ['posting_date', 'Posting date'],
            ['pre_bid_date', 'Pre-bid date'],
            ['bidding_date', 'Bidding date'],
            ['notice_award_date', 'Notice of award date'],
            ['notice_to_proceed_date', 'Notice to proceed date'],
        ].map(function ([name, label]) {
            return {
                field: panel.querySelector(`[name="${name}"]`),
                label: label,
            };
        }).filter(function (milestone) {
            return milestone.field;
        });

        milestones.forEach(function (milestone) {
            const group = milestone.field.closest('.form-group');
            const message = group && group.querySelector('[data-procurement-date-error]');
            if (message) {
                message.remove();
                milestone.field.removeAttribute('aria-invalid');
                if (!group.querySelector('.client-error-message')) {
                    group.classList.remove('has-client-error');
                }
            }
        });

        const populatedMilestones = milestones.filter(function (milestone) {
            return milestone.field.value;
        });
        let firstInvalid = null;
        for (let index = 1; index < populatedMilestones.length; index += 1) {
            const previous = populatedMilestones[index - 1];
            const current = populatedMilestones[index];
            if (current.field.value < previous.field.value) {
                showFieldError(
                    current.field,
                    `${current.label} cannot be earlier than ${previous.label.toLowerCase()}.`,
                    true
                );
                firstInvalid = firstInvalid || current.field;
            }
        }
        return firstInvalid;
    }

    function validatePanel(panel) {
        // Hidden coordinates need explicit validation by the map picker;
        // HTML constraint validation does not apply to hidden form inputs.
        const picker = panel.querySelector('[data-location-picker]');
        const locationValid = !picker || picker.dispatchEvent(new CustomEvent(
            'location-picker:validate', { cancelable: true }
        ));
        let firstInvalid = null;
        panelFields(panel).forEach(function (field) {
            if (field.checkValidity()) clearFieldError(field);
            else {
                showFieldError(field);
                firstInvalid = firstInvalid || field;
            }
        });
        const firstInvalidProcurementDate = validateProcurementDates(panel);
        if (firstInvalid) {
            firstInvalid.focus();
            return false;
        }
        if (firstInvalidProcurementDate) {
            firstInvalidProcurementDate.focus();
            return false;
        }
        return locationValid;
    }

    backButton.addEventListener('click', function () { showStep(activeStep - 1, { focusPanel: true }); });
    nextButton.addEventListener('click', function () {
        if (validatePanel(panels[activeStep])) showStep(activeStep + 1, { focusPanel: true });
    });

    form.querySelectorAll('input, select, textarea').forEach(function (field) {
        ['input', 'change'].forEach(function (eventName) {
            field.addEventListener(eventName, function () {
                hasUnsavedChanges = true;
                if (field === plannedStartDate || field === plannedEndDate) {
                    updatePlannedDuration();
                }
                const procurementPanel = field.closest('[data-procurement-date-validation]');
                const revalidateProcurementDates = procurementPanel &&
                    procurementPanel.querySelector('[data-procurement-date-error]');
                if (field.checkValidity()) clearFieldError(field);
                if (revalidateProcurementDates) validateProcurementDates(procurementPanel);
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

    updatePlannedDuration();
    showStep(activeStep, { focusPanel: Boolean(firstError) });
});
