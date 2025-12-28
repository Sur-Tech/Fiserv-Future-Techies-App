function loadPage(page) {
    const main = document.querySelector("main");
    if (!main) return;

    const routes = {
        home: "index.html",
        banks: "banks.html",
        groceries: "groceries.html",
        school: "school.html",
        "spending-analyzer": "spending-analyzer.html",
        utilities: "utilities.html",
        work: "work.html"
    };

    const target = routes[page];
    if (!target) {
        main.innerHTML = "<h1>404</h1><p>Page not found.</p>";
        return;
    }

    fetch(target)
        .then(res => {
            if (!res.ok) throw new Error("Fetch failed");
            return res.text();
        })
        .then(html => {
            const doc = new DOMParser().parseFromString(html, "text/html");
            const innerMain = doc.querySelector("main");
            main.innerHTML = innerMain ? innerMain.innerHTML : html;
        })
        .catch(err => {
            console.error(err);
            main.innerHTML = "<h1>Error</h1><p>Could not load page.</p>";
        });
}
