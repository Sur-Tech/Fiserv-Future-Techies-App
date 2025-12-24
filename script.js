// Dark Mode Toggle
const darkModeToggle = document.getElementById("darkModeToggle");

darkModeToggle.addEventListener("click", () => {
    document.body.classList.toggle("dark-mode");
    darkModeToggle.textContent =
        document.body.classList.contains("dark-mode") ?
        "☀️ Light Mode" :
        "🌙 Dark Mode";
});

// Scroll to section function
function scrollToSection(id) {
    const section = document.getElementById(id);
    if (section) {
        section.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

// Routing File
function loadPage(page) {
    const main = document.querySelector("main");

    const routes = {
        "home": "index.html",
        "soil-ai": "soil-ai.html",
        "common-plants": "common-plants.html"
    };

    const target = routes[page];
    if (!target) {
        main.innerHTML = "<h1>404 Not Found</h1><p>The requested page was not found.</p>";
        return;
    }

    fetch(target)
        .then((response) => response.text())
        .then((html) => {
            // Try to extract just the <main> content if a full HTML doc was fetched
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, "text/html");
            const innerMain = doc.querySelector("main");
            main.innerHTML = innerMain ? innerMain.innerHTML : html;
            // If this is the Soil AI page, initialize its UI
            if (page === 'soil-ai' && typeof window.initializePlantIdUI === 'function') {
                window.initializePlantIdUI();
            }
        })
        .catch((error) => {
            console.error("Error loading page:", error);
            main.innerHTML = "<h1>Error</h1><p>Could not load the page.</p>";
        });
}
