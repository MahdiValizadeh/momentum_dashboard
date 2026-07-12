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
            datasets: [
                {
                    label: "Minutes",
                    data: data.week_minutes,
                    backgroundColor: "rgba(99, 102, 241, 0.75)",
                    borderRadius: 6,
                    maxBarThickness: 36,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, ticks: { precision: 0 } },
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
