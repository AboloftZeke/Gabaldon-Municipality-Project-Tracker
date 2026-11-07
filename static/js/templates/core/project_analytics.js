(() => {
    const dataElement = document.getElementById('project-analytics-data');
    if (!dataElement) return;

    const charts = JSON.parse(dataElement.textContent);
    const namespace = 'http://www.w3.org/2000/svg';
    const colors = {
        blue: '#2878b5',
        teal: '#159b8c',
        orange: '#e88a31',
        grid: '#e5ebe7',
        text: '#536158',
    };

    function element(name, attributes = {}) {
        const node = document.createElementNS(namespace, name);
        Object.entries(attributes).forEach(([key, value]) => {
            node.setAttribute(key, value);
        });
        return node;
    }

    function resetSvg(svg, viewBox, description) {
        svg.replaceChildren();
        svg.setAttribute('viewBox', viewBox);
        svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
        svg.setAttribute('aria-label', description);
        svg.append(element('title')).textContent = description;
    }

    function emptyState(svg, width, height, message) {
        const text = element('text', {
            x: width / 2,
            y: height / 2,
            class: 'project-analytics__empty',
            fill: colors.text,
            'font-size': 14,
        });
        text.textContent = message;
        svg.append(text);
    }

    function renderMonthly(svg, chart, description) {
        const labels = chart.labels || [];
        const values = chart.values || [];
        if (!labels.length) {
            resetSvg(svg, '0 0 640 230', description);
            svg.style.width = '100%';
            emptyState(svg, 640, 230, 'No dated records available.');
            return;
        }

        const width = Math.max(640, labels.length * 52 + 72);
        const height = 270;
        const left = 38;
        const top = 14;
        const bottom = 82;
        const plotHeight = height - top - bottom;
        const plotWidth = width - left - 18;
        const maxValue = Math.max(1, ...values);
        const step = plotWidth / labels.length;
        const barWidth = Math.max(3, step * .64);
        resetSvg(svg, `0 0 ${width} ${height}`, description);
        svg.style.width = `${width}px`;

        for (let tick = 0; tick <= 4; tick += 1) {
            const value = Math.ceil(maxValue * tick / 4);
            const y = top + plotHeight - (plotHeight * tick / 4);
            svg.append(element('line', {
                x1: left, y1: y, x2: width - 8, y2: y,
                stroke: colors.grid, 'stroke-width': 1,
            }));
            const label = element('text', {
                x: left - 8, y: y + 4, 'text-anchor': 'end',
                fill: colors.text, 'font-size': 11,
            });
            label.textContent = value;
            svg.append(label);
        }

        labels.forEach((label, index) => {
            const value = values[index] || 0;
            const barHeight = (value / maxValue) * plotHeight;
            const x = left + index * step + (step - barWidth) / 2;
            const y = top + plotHeight - barHeight;
            const bar = element('rect', {
                x, y, width: barWidth, height: Math.max(value ? 2 : 0, barHeight),
                rx: 3, fill: colors.teal,
            });
            const tip = element('title');
            tip.textContent = `${label}: ${value}`;
            bar.append(tip);
            svg.append(bar);
            const monthLabel = element('text', {
                x: left + index * step + step / 2,
                y: height - 12,
                transform: `rotate(-42 ${left + index * step + step / 2} ${height - 12})`,
                'text-anchor': 'end',
                fill: colors.text,
                'font-size': 10,
            });
            monthLabel.textContent = label;
            svg.append(monthLabel);
        });
    }

    function renderStatus(svg, legend, rows, total) {
        const width = 220;
        const height = 220;
        const center = width / 2;
        const radius = 82;
        const innerRadius = 49;
        const palette = [colors.teal, colors.blue, colors.orange];
        resetSvg(svg, `0 0 ${width} ${height}`, 'Project distribution by implementation status');
        svg.style.width = '100%';
        legend.replaceChildren();

        if (!total) {
            svg.append(element('circle', {
                cx: center, cy: center, r: radius, fill: 'none',
                stroke: colors.grid, 'stroke-width': 30,
            }));
            emptyState(svg, width, height, 'No projects');
        } else {
            let angle = -Math.PI / 2;
            rows.forEach((row, index) => {
                if (!row.value) return;
                const next = angle + (row.value / total) * Math.PI * 2;
                const startX = center + radius * Math.cos(angle);
                const startY = center + radius * Math.sin(angle);
                const endX = center + radius * Math.cos(next);
                const endY = center + radius * Math.sin(next);
                const innerStartX = center + innerRadius * Math.cos(angle);
                const innerStartY = center + innerRadius * Math.sin(angle);
                const innerEndX = center + innerRadius * Math.cos(next);
                const innerEndY = center + innerRadius * Math.sin(next);
                const isFullCircle = row.value === total;
                const largeArc = next - angle > Math.PI ? 1 : 0;
                if (isFullCircle) {
                    const circle = element('circle', {
                        cx: center,
                        cy: center,
                        r: radius,
                        fill: palette[index % palette.length],
                    });
                    const tip = element('title');
                    tip.textContent = `${row.label}: ${row.value} (100%)`;
                    circle.append(tip);
                    svg.append(circle);
                    svg.append(element('circle', {
                        cx: center, cy: center, r: innerRadius, fill: '#fff',
                    }));
                } else {
                    const path = element('path', {
                        d: `M ${startX} ${startY} A ${radius} ${radius} 0 ${largeArc} 1 ${endX} ${endY} L ${innerEndX} ${innerEndY} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerStartX} ${innerStartY} Z`,
                        fill: palette[index % palette.length],
                        stroke: '#fff',
                        'stroke-width': 2,
                    });
                    const tip = element('title');
                    tip.textContent = `${row.label}: ${row.value} (${Math.round(row.value / total * 100)}%)`;
                    path.append(tip);
                    svg.append(path);
                }
                angle = next;
            });
            const totalText = element('text', {
                x: center,
                y: center + 5,
                'text-anchor': 'middle',
                fill: colors.text,
                'font-size': 20,
                'font-weight': 700,
            });
            totalText.textContent = total;
            svg.append(totalText);
        }

        rows.forEach((row, index) => {
            const item = document.createElement('li');
            const swatch = document.createElement('span');
            swatch.className = 'project-analytics__legend-swatch';
            swatch.style.backgroundColor = palette[index % palette.length];
            const label = document.createElement('span');
            label.textContent = row.label;
            const value = document.createElement('span');
            value.className = 'project-analytics__legend-value';
            const percentage = total ? Math.round(row.value / total * 100) : 0;
            value.textContent = `${row.value} (${percentage}%)`;
            item.append(swatch, label, value);
            legend.append(item);
        });
    }

    function renderBarangays(svg, rows) {
        const width = 780;
        const rowHeight = 27;
        const height = rows.length * rowHeight + 20;
        const left = 180;
        const right = 42;
        const maxValue = Math.max(1, ...rows.map(row => row.value));
        const plotWidth = width - left - right;
        resetSvg(svg, `0 0 ${width} ${height}`, 'Projects by barangay');
        svg.style.width = `${width}px`;

        rows.forEach((row, index) => {
            const y = 10 + index * rowHeight;
            const label = element('text', {
                x: left - 10, y: y + 16,
                'text-anchor': 'end',
                fill: colors.text,
                'font-size': 12,
            });
            label.textContent = row.label;
            svg.append(label);

            const barWidth = row.value / maxValue * plotWidth;
            const bar = element('rect', {
                x: left, y: y + 3, width: Math.max(row.value ? 2 : 0, barWidth),
                height: 16, rx: 4, fill: colors.blue,
            });
            const tip = element('title');
            tip.textContent = `${row.label}: ${row.value}`;
            bar.append(tip);
            svg.append(bar);

            const count = element('text', {
                x: left + barWidth + 7, y: y + 16,
                fill: colors.text, 'font-size': 12,
            });
            count.textContent = row.value;
            svg.append(count);
        });
    }

    document.querySelectorAll('[data-chart="published_by_month"]').forEach(node => {
        renderMonthly(node.querySelector('[data-plot]'), charts.published_by_month, 'Projects published by month');
    });
    document.querySelectorAll('[data-chart="completed_by_month"]').forEach(node => {
        renderMonthly(node.querySelector('[data-plot]'), charts.completed_by_month, 'Projects completed by month');
    });
    const statusSvg = document.querySelector('svg[data-chart="status"]');
    const statusLegend = document.querySelector('[data-status-legend]');
    if (statusSvg && statusLegend) {
        renderStatus(statusSvg, statusLegend, charts.status, charts.status_project_count);
    }
    document.querySelectorAll('[data-chart="barangays"]').forEach(node => {
        renderBarangays(node.querySelector('[data-plot]'), charts.barangays);
    });
})();
