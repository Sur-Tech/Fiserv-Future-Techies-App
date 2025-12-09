// Dark Mode Toggle
const darkModeToggle = document.getElementById("darkModeToggle");
darkModeToggle.addEventListener("click", () => {
    document.body.classList.toggle("dark-mode");
    darkModeToggle.textContent = document.body.classList.contains("dark-mode") ? "☀️ Light Mode" : "🌙 Dark Mode";
});

// Routing / Page Loading (keeping your protocol)
function loadPage(page) {
    const main = document.querySelector("main");

    const routes = {
        "": "homepage.html", // the homepage content file
        "features": "features.html",
        "workflows": "workflows.html",
        "tech": "tech.html",
        "contact": "contact.html"
    };

    const target = routes[page];
    if (!target) {
        main.innerHTML = "<h1>404 Not Found</h1><p>The requested page was not found.</p>";
        return;
    }

    fetch(target)
        .then((response) => response.text())
        .then((html) => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, "text/html");
            const innerMain = doc.querySelector("main");
            main.innerHTML = innerMain ? innerMain.innerHTML : html;
        })
        .catch((error) => {
            console.error("Error loading page:", error);
            main.innerHTML = "<h1>Error</h1><p>Could not load the page.</p>";
        });
}
