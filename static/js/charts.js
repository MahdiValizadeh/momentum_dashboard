// charts.js — fetches aggregated data from /api/chart-data and renders
// the three dashboard charts using Chart.js.

document.addEventListener("DOMContentLoaded", () => {
    fetch("/api/chart-data")
        .then((res) => res.json())
        .then((data) => {
            renderWeekChart(data);
            renderSkillChart(data);
            renderTrendChart(data);
        })
        .catch((err) => console.error("Failed to load chart data:", err));
});

function renderWeekChart(data) {
    const ctx = document.getElementById("weekChart");
    if (!ctx) return;
    new Chart(ctx, {
        type: "bar",
        data: {
            labels: data.week_labels,
            datasets: data.week_skill_datasets.map(skill => ({
                ...skill,
                backgroundColor: context => {
                    const area = context.chart.chartArea;
                    const color = skill.backgroundColor;
                    if (!area || !/^#[0-9a-f]{6}$/i.test(color)) return color;
                    const gradient = context.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
                    gradient.addColorStop(0, color + 'b8');
                    gradient.addColorStop(1, color);
                    return gradient;
                },
                borderRadius: 8,
                borderSkipped: false,
                borderColor: '#ffffff',
                stack: 'minutes',
                borderWidth: 1.5,
                maxBarThickness: 34,
                categoryPercentage: 0.65,
            })),
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14 } },
                tooltip: { callbacks: {
                    label: context => `${context.dataset.label}: ${context.parsed.y} min`,
                    footer: items => `Total: ${items.reduce((total, item) => total + item.parsed.y, 0)} min`,
                } },
            },
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Minutes' } },
            },
        },
    });
}

function renderSkillChart(data) {
    const ctx = document.getElementById("skillChart");
    if (!ctx) return;

    const hasData = data.skill_minutes.some((m) => m > 0);
    new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: data.skill_names,
            datasets: [
                {
                    data: hasData ? data.skill_minutes : data.skill_names.map(() => 1),
                    backgroundColor: data.skill_colors,
                    borderWidth: 2,
                    borderColor: "#fff",
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: "bottom", labels: { boxWidth: 12, padding: 14 } },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            if (!hasData) return context.label + ": no data yet";
                            return context.label + ": " + context.parsed + " min";
                        },
                    },
                },
            },
        },
    });
}

function renderTrendChart(data) {
    const ctx = document.getElementById("trendChart");
    if (!ctx) return;
    new Chart(ctx, {
        type: "line",
        data: {
            labels: data.trend_labels,
            datasets: [
                {
                    label: "Avg Quality (1-10)",
                    data: data.quality_trend,
                    borderColor: "#f59e0b",
                    backgroundColor: "rgba(245, 158, 11, 0.15)",
                    tension: 0.35,
                    spanGaps: true,
                    yAxisID: "y",
                },
                {
                    label: "Avg Completion (%)",
                    data: data.completion_trend,
                    borderColor: "#22c55e",
                    backgroundColor: "rgba(34, 197, 94, 0.15)",
                    tension: 0.35,
                    spanGaps: true,
                    yAxisID: "y1",
                },
            ],
        },
        options: {
            responsive: true,
            interaction: { mode: "index", intersect: false },
            scales: {
                y: {
                    type: "linear",
                    position: "left",
                    min: 0,
                    max: 10,
                    title: { display: true, text: "Quality" },
                },
                y1: {
                    type: "linear",
                    position: "right",
                    min: 0,
                    max: 100,
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: "Completion %" },
                },
            },
        },
    });
}
