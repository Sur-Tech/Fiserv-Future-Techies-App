function loadPage(page) {
    // Update active tab highlight
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    const activeTab = document.getElementById(page);
    if (activeTab) activeTab.classList.add("active");

    // spending-analyzer has its own Plaid scripts — navigate directly
    if (page === "spending-analyzer") {
        window.location.href = "spending-analyzer.html";
        return;
    }

    const main = document.querySelector("main");
    if (!main) return;

    const routes = {
        home:       "index.html",
        banks:      "banks.html",
        groceries:  "groceries.html",
        school:     "school.html",
        utilities:  "utilities.html",
        work:       "work.html"
    };

    const target = routes[page];
    if (!target) {
        main.innerHTML = "<p style='padding:60px;text-align:center;color:var(--gray-500);font-size:16px'>Page not found.</p>";
        return;
    }

    // Fade out
    main.style.transition = "opacity 0.18s ease";
    main.style.opacity = "0.35";

    fetch(target)
        .then(res => {
            if (!res.ok) throw new Error("Fetch failed: " + res.status);
            return res.text();
        })
        .then(html => {
            const doc = new DOMParser().parseFromString(html, "text/html");
            const innerMain = doc.querySelector("main");
            main.innerHTML = innerMain ? innerMain.innerHTML : html;

            // Fade in
            requestAnimationFrame(() => {
                main.style.opacity = "1";
            });

            // Update browser title
            const titleEl = doc.querySelector("title");
            if (titleEl) document.title = titleEl.textContent;

            // Scroll to top smoothly
            window.scrollTo({ top: 0, behavior: "smooth" });
        })
        .catch(err => {
            console.error("loadPage error:", err);
            main.style.opacity = "1";
            main.innerHTML = `
                <div style="padding:60px;text-align:center">
                    <div style="font-size:48px;margin-bottom:16px">&#128533;</div>
                    <p style="color:#DC2626;font-size:16px;font-weight:600">Failed to load page.</p>
                    <p style="color:var(--gray-500);margin-top:8px">Please check the server is running and try again.</p>
                </div>`;
        });
}
