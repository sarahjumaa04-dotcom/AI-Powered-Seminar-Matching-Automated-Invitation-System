document.addEventListener("DOMContentLoaded", () => {
    console.log("BAU Seminar & Summit Management loaded.");

    // Day name preview for event form date picker
    const dateInput = document.getElementById("event_date");
    const dayPreview = document.getElementById("dayNamePreview");
    if (dateInput && dayPreview) {
        dateInput.addEventListener("change", () => {
            const val = dateInput.value;
            if (val) {
                const d = new Date(val + "T00:00:00");
                const days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
                dayPreview.textContent = days[d.getDay()] + ", " + val;
            } else {
                dayPreview.textContent = "";
            }
        });
    }

    const scoreFills = document.querySelectorAll(".score-bar-fill[data-score]");
    scoreFills.forEach((fill) => {
        const scoreValue = parseFloat(fill.dataset.score);
        if (!Number.isNaN(scoreValue)) {
            fill.style.width = `${Math.min(100, Math.max(0, scoreValue))}%`;
        }
    });
});
