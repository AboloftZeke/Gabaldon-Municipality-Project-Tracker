document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('id_evidence_files');
    const summary = document.getElementById('mayor-selected-files');

    let lastFocusedElement = null;
    const lightbox = document.createElement('div');
    lightbox.className = 'mayor-evidence-lightbox';
    lightbox.hidden = true;
    lightbox.setAttribute('role', 'dialog');
    lightbox.setAttribute('aria-modal', 'true');
    lightbox.setAttribute('aria-label', 'Evidence image preview');
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'mayor-evidence-lightbox__close';
    closeButton.textContent = 'Close image preview';
    const lightboxImage = document.createElement('img');
    lightboxImage.className = 'mayor-evidence-lightbox__image';
    lightbox.append(closeButton, lightboxImage);
    document.body.appendChild(lightbox);

    const closeLightbox = () => {
        lightbox.hidden = true;
        lightboxImage.removeAttribute('src');
        document.body.classList.remove('mayor-evidence-lightbox-open');
        if (lastFocusedElement) lastFocusedElement.focus();
    };

    const openLightbox = (link) => {
        lastFocusedElement = document.activeElement;
        lightboxImage.src = link.href;
        lightboxImage.alt = link.querySelector('img')?.alt || 'Evidence image preview';
        lightbox.hidden = false;
        document.body.classList.add('mayor-evidence-lightbox-open');
        closeButton.focus();
    };

    closeButton.addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', (event) => {
        if (event.target === lightbox) closeLightbox();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !lightbox.hidden) closeLightbox();
    });
    document.addEventListener('click', (event) => {
        const link = event.target.closest(
            '.mayor-upload__preview-link, .mayor-evidence-file__preview-link',
        );
        if (!link) return;
        event.preventDefault();
        openLightbox(link);
    });

    if (!input || !summary) return;

    const imageTypes = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp']);
    const imageExtensions = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp']);
    let previewUrls = [];

    const clearPreviewUrls = () => {
        previewUrls.forEach((url) => URL.revokeObjectURL(url));
        previewUrls = [];
    };

    const renderFiles = () => {
        const files = Array.from(input.files || []);
        clearPreviewUrls();
        summary.replaceChildren();
        if (!files.length) {
            summary.textContent = 'No files selected.';
            return;
        }

        const heading = document.createElement('strong');
        heading.textContent = `${files.length} file${files.length === 1 ? '' : 's'} selected`;
        const list = document.createElement('ul');
        list.className = 'mayor-upload__preview-list';
        files.forEach((file) => {
            const item = document.createElement('li');
            item.className = 'mayor-upload__preview-item';

            const details = document.createElement('div');
            details.className = 'mayor-upload__preview-details';
            const name = document.createElement('strong');
            name.className = 'mayor-upload__preview-name';
            name.textContent = file.name;
            const type = document.createElement('span');
            type.className = 'mayor-upload__preview-type';
            type.textContent = file.type || 'File';
            details.append(name, type);

            const extension = file.name.split('.').pop().toLowerCase();
            const isImage = imageTypes.has(file.type) || imageExtensions.has(extension);
            const fileUrl = URL.createObjectURL(file);
            previewUrls.push(fileUrl);

            if (isImage) {
                const previewLink = document.createElement('a');
                previewLink.className = 'mayor-upload__preview-link';
                previewLink.href = fileUrl;
                previewLink.setAttribute('aria-label', `Open image preview for ${file.name}`);
                const image = document.createElement('img');
                image.className = 'mayor-upload__preview-image';
                image.src = fileUrl;
                image.alt = `Preview of ${file.name}`;
                previewLink.appendChild(image);
                details.prepend(previewLink);
            } else {
                const openLink = document.createElement('a');
                openLink.className = 'ui-button ui-button--secondary mayor-upload__open';
                openLink.href = fileUrl;
                openLink.target = '_blank';
                openLink.rel = 'noopener';
                openLink.textContent = 'Open file';
                details.appendChild(openLink);
            }

            const removeButton = document.createElement('button');
            removeButton.type = 'button';
            removeButton.className = 'ui-button ui-button--secondary mayor-upload__remove';
            removeButton.textContent = 'Remove';
            removeButton.addEventListener('click', () => {
                const remainingFiles = files.filter((selectedFile) => selectedFile !== file);
                const dataTransfer = new DataTransfer();
                remainingFiles.forEach((remainingFile) => dataTransfer.items.add(remainingFile));
                input.files = dataTransfer.files;
                renderFiles();
            });

            item.append(details, removeButton);
            list.appendChild(item);
        });
        summary.append(heading, list);
    };

    input.addEventListener('change', renderFiles);
    window.addEventListener('beforeunload', clearPreviewUrls);
});
