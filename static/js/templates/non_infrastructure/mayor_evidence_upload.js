document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('id_evidence_files');
    const summary = document.getElementById('mayor-selected-files');
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
                previewLink.target = '_blank';
                previewLink.rel = 'noopener';
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
