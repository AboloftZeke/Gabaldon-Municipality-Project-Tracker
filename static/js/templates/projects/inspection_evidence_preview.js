document.addEventListener('DOMContentLoaded', function () {
    const preview = document.querySelector('[data-selected-evidence]');
    const grid = preview && preview.querySelector('[data-selected-evidence-grid]');
    if (!preview || !grid) return;

    const inputs = [
        { selector: '#id_inspection_photos', type: 'image', label: 'Photo' },
        { selector: '#id_inspection_documents', type: 'document', label: 'PDF document' },
    ].map(function (entry) {
        return {
            input: document.querySelector(entry.selector),
            type: entry.type,
            label: entry.label,
        };
    }).filter(function (entry) {
        return entry.input;
    });
    const objectUrls = new Set();

    function renderSelectedEvidence() {
        objectUrls.forEach(function (url) { URL.revokeObjectURL(url); });
        objectUrls.clear();
        grid.replaceChildren();

        inputs.forEach(function (entry) {
            Array.from(entry.input.files || []).forEach(function (file) {
                const url = URL.createObjectURL(file);
                objectUrls.add(url);

                const fileCard = document.createElement(
                    entry.type === 'image' ? 'button' : 'a'
                );
                fileCard.className = `inspection-file-card inspection-file-card--${entry.type}`;

                if (entry.type === 'image') {
                    fileCard.type = 'button';
                    fileCard.dataset.imageViewerTrigger = '';
                    fileCard.dataset.imageSrc = url;
                    fileCard.dataset.imageAlt = file.name;
                    fileCard.setAttribute('aria-label', `View photo ${file.name}`);
                    const image = document.createElement('img');
                    image.src = url;
                    image.alt = file.name;
                    fileCard.appendChild(image);
                } else {
                    fileCard.href = url;
                    fileCard.target = '_blank';
                    fileCard.rel = 'noopener';
                    fileCard.setAttribute('aria-label', `Open ${entry.label}: ${file.name}`);
                    const icon = document.createElement('span');
                    icon.className = 'inspection-file-card__icon';
                    icon.textContent = 'PDF';
                    fileCard.appendChild(icon);
                }

                const details = document.createElement('span');
                const name = document.createElement('strong');
                name.textContent = file.name;
                const kind = document.createElement('small');
                kind.textContent = entry.label;
                details.append(name, kind);
                fileCard.appendChild(details);
                grid.appendChild(fileCard);
            });
        });

        preview.hidden = grid.childElementCount === 0;
    }

    inputs.forEach(function (entry) {
        entry.input.addEventListener('change', renderSelectedEvidence);
    });
    window.addEventListener('beforeunload', function () {
        objectUrls.forEach(function (url) { URL.revokeObjectURL(url); });
    });
    renderSelectedEvidence();
});
