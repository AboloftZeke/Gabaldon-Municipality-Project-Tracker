(function () {
    const modal = document.querySelector('[data-project-modal]');

    if (!modal) {
        return;
    }

    const titleField = modal.querySelector('[data-project-modal-field="title"]');
    const statusField = modal.querySelector('[data-project-modal-field="status"]');
    const detailLink = modal.querySelector('[data-project-modal-detail-link]');
    const fieldMap = {
        type: modal.querySelector('[data-project-modal-field="type"]'),
        office: modal.querySelector('[data-project-modal-field="office"]'),
        location: modal.querySelector('[data-project-modal-field="location"]'),
        category: modal.querySelector('[data-project-modal-field="category"]'),
        contractor: modal.querySelector('[data-project-modal-field="contractor"]'),
        procurement_method: modal.querySelector('[data-project-modal-field="procurement_method"]'),
        award_status: modal.querySelector('[data-project-modal-field="award_status"]'),
        source_of_fund: modal.querySelector('[data-project-modal-field="source_of_fund"]'),
        budget_amount: modal.querySelector('[data-project-modal-field="budget_amount"]'),
        abc_amount: modal.querySelector('[data-project-modal-field="abc_amount"]'),
        contract_price: modal.querySelector('[data-project-modal-field="contract_price"]'),
        progress_percentage: modal.querySelector('[data-project-modal-field="progress_percentage"]'),
        overall_progress_percentage: modal.querySelector('[data-project-modal-field="overall_progress_percentage"]'),
        service_location_details: modal.querySelector('[data-project-modal-field="service_location_details"]'),
        service_period: modal.querySelector('[data-project-modal-field="service_period"]'),
        service_time: modal.querySelector('[data-project-modal-field="service_time"]'),
        planned_start_date: modal.querySelector('[data-project-modal-field="planned_start_date"]'),
        planned_end_date: modal.querySelector('[data-project-modal-field="planned_end_date"]'),
        actual_start_date: modal.querySelector('[data-project-modal-field="actual_start_date"]'),
        revised_completion_date: modal.querySelector('[data-project-modal-field="revised_completion_date"]'),
        cost_progress_percentage: modal.querySelector('[data-project-modal-field="cost_progress_percentage"]'),
        physical_progress_percentage: modal.querySelector('[data-project-modal-field="physical_progress_percentage"]'),
        service_description: modal.querySelector('[data-project-modal-field="service_description"]'),
        beneficiaries_description: modal.querySelector('[data-project-modal-field="beneficiaries_description"]'),
        results_achieved: modal.querySelector('[data-project-modal-field="results_achieved"]'),
        created_by: modal.querySelector('[data-project-modal-field="created_by"]'),
        created_at: modal.querySelector('[data-project-modal-field="created_at"]'),
        updated_at: modal.querySelector('[data-project-modal-field="updated_at"]'),
        description: modal.querySelector('[data-project-modal-field="description"]'),
    };

    const groupMap = {
        type: modal.querySelector('[data-project-modal-group="type"]'),
        office: modal.querySelector('[data-project-modal-group="office"]'),
        location: modal.querySelector('[data-project-modal-group="location"]'),
        category: modal.querySelector('[data-project-modal-group="category"]'),
        contractor: modal.querySelector('[data-project-modal-group="contractor"]'),
        procurement_method: modal.querySelector('[data-project-modal-group="procurement_method"]'),
        award_status: modal.querySelector('[data-project-modal-group="award_status"]'),
        source_of_fund: modal.querySelector('[data-project-modal-group="source_of_fund"]'),
        budget_amount: modal.querySelector('[data-project-modal-group="budget_amount"]'),
        abc_amount: modal.querySelector('[data-project-modal-group="abc_amount"]'),
        contract_price: modal.querySelector('[data-project-modal-group="contract_price"]'),
        progress_percentage: modal.querySelector('[data-project-modal-group="progress_percentage"]'),
        overall_progress_percentage: modal.querySelector('[data-project-modal-group="overall_progress_percentage"]'),
        service_location_details: modal.querySelector('[data-project-modal-group="service_location_details"]'),
        service_period: modal.querySelector('[data-project-modal-group="service_period"]'),
        service_time: modal.querySelector('[data-project-modal-group="service_time"]'),
        planned_start_date: modal.querySelector('[data-project-modal-group="planned_start_date"]'),
        planned_end_date: modal.querySelector('[data-project-modal-group="planned_end_date"]'),
        actual_start_date: modal.querySelector('[data-project-modal-group="actual_start_date"]'),
        revised_completion_date: modal.querySelector('[data-project-modal-group="revised_completion_date"]'),
        cost_progress_percentage: modal.querySelector('[data-project-modal-group="cost_progress_percentage"]'),
        physical_progress_percentage: modal.querySelector('[data-project-modal-group="physical_progress_percentage"]'),
        service_description: modal.querySelector('[data-project-modal-group="service_description"]'),
        beneficiaries_description: modal.querySelector('[data-project-modal-group="beneficiaries_description"]'),
        results_achieved: modal.querySelector('[data-project-modal-group="results_achieved"]'),
        created_by: modal.querySelector('[data-project-modal-group="created_by"]'),
        created_at: modal.querySelector('[data-project-modal-group="created_at"]'),
        updated_at: modal.querySelector('[data-project-modal-group="updated_at"]'),
        description: modal.querySelector('[data-project-modal-group="description"]'),
    };

    function setField(fieldName, value) {
        const field = fieldMap[fieldName];
        const group = groupMap[fieldName];

        if (!field || !group) {
            return;
        }

        const normalized = (value || '').trim();
        field.textContent = normalized;
        group.hidden = normalized.length === 0;
    }

    function setModalStatus(statusText, statusClass) {
        if (!statusField) {
            return;
        }

        statusField.textContent = statusText || '';
        statusField.className = 'project-modal__status';

        if (statusClass) {
            statusField.classList.add(statusClass);
        }
    }

    function openModal(trigger) {
        if (titleField) {
            titleField.textContent = (trigger.dataset.projectTitle || '').trim();
        }
        setField('type', trigger.dataset.projectTypeLabel);
        setField('office', trigger.dataset.projectOffice || trigger.dataset.projectImplementingOffice);
        setField('location', trigger.dataset.projectLocation);
        setField('category', trigger.dataset.projectCategory);
        setField('contractor', trigger.dataset.projectContractor);
        setField('procurement_method', trigger.dataset.projectProcurementMethod);
        setField('award_status', trigger.dataset.projectStatusLabel || trigger.dataset.projectAwardStatus);
        setField('source_of_fund', trigger.dataset.projectSourceOfFund);
        setField('budget_amount', trigger.dataset.projectBudgetAmount);
        setField('abc_amount', trigger.dataset.projectAbcAmount);
        setField('contract_price', trigger.dataset.projectContractPrice);
        setField('progress_percentage', trigger.dataset.projectProgressPercentage);
        setField('overall_progress_percentage', trigger.dataset.projectOverallProgressPercentage);
        setField('service_location_details', trigger.dataset.projectServiceLocationDetails);
        setField('service_period', trigger.dataset.projectServicePeriod);
        setField('service_time', trigger.dataset.projectServiceTime);
        setField('planned_start_date', trigger.dataset.projectPlannedStartDate);
        setField('planned_end_date', trigger.dataset.projectPlannedEndDate);
        setField('actual_start_date', trigger.dataset.projectActualStartDate);
        setField('revised_completion_date', trigger.dataset.projectRevisedCompletionDate);
        setField('cost_progress_percentage', trigger.dataset.projectCostProgressPercentage);
        setField('physical_progress_percentage', trigger.dataset.projectPhysicalProgressPercentage);
        setField('service_description', trigger.dataset.projectServiceDescription);
        setField('beneficiaries_description', trigger.dataset.projectBeneficiariesDescription);
        setField('results_achieved', trigger.dataset.projectResultsAchieved);
        setField('created_by', trigger.dataset.projectCreatedBy);
        setField('created_at', trigger.dataset.projectCreatedAt);
        setField('updated_at', trigger.dataset.projectUpdatedAt);
        setField('description', trigger.dataset.projectDescription);

        if (detailLink) {
            detailLink.href = trigger.dataset.projectDetailUrl || '#';
        }

        const statusLabel = trigger.dataset.projectStatusLabel || trigger.dataset.projectAwardStatusLabel || trigger.dataset.projectAwardStatus || '';
        const statusClass = trigger.dataset.projectStatusClass || '';
        setModalStatus(statusLabel, statusClass);

        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('project-modal-open');

        const closeButton = modal.querySelector('[data-project-modal-close]');
        if (closeButton) {
            closeButton.focus();
        }
    }

    function closeModal() {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('project-modal-open');
    }

    document.addEventListener('click', function (event) {
        const closeButton = event.target.closest('[data-project-modal-close]');

        if (closeButton) {
            event.preventDefault();
            event.stopPropagation();
            closeModal();
            return;
        }

        const trigger = event.target.closest('[data-project-modal-trigger]');

        if (trigger) {
            event.preventDefault();
            event.stopPropagation();
            openModal(trigger);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.hidden) {
            closeModal();
        }
    });
})();