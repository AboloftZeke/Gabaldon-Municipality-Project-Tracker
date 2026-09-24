document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('id_evidence_files');
    const summary = document.getElementById('mayor-selected-files');
    if (!input || !summary) return;

    input.addEventListener('change', () => {
        const files = Array.from(input.files || []);
        summary.replaceChildren();
        if (!files.length) {
            summary.textContent = 'No files selected.';
            return;
        }
        const heading = document.createElement('strong');
        heading.textContent = `${files.length} file${files.length === 1 ? '' : 's'} selected`;
        const list = document.createElement('ul');
        files.forEach((file) => {
            const item = document.createElement('li');
            item.textContent = file.name;
            list.appendChild(item);
        });
        summary.append(heading, list);
    });
});
