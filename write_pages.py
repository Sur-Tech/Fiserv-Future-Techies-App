"""
Writes all sub-page HTML files with the modern Fiserv CFO UI.
Run: venv/Scripts/python.exe write_pages.py
"""

HEAD = lambda title: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - Fiserv CFO</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="style.css">
    <script src="script.js" defer></script>
</head>
<body>"""

FOOT = """    <footer>
        <p>&copy; 2024 <strong>Fiserv CFO</strong> &mdash; Fiserv Future Techies Challenge</p>
    </footer>
</body>
</html>"""

def nav(active):
    pages = [("banks","Banks"),("groceries","Groceries"),("school","School"),
             ("spending-analyzer","Spending Analyzer"),("utilities","Utilities"),("work","Work")]
    items = ""
    for pid, label in pages:
        cls = " active" if pid == active else ""
        fn  = pid if pid != "spending-analyzer" else "spending-analyzer"
        items += f'\n                <li class="tab{cls}" id="{pid}" onclick="loadPage(\'{fn}\')">{label}</li>'
    return f"""    <header class="header">
        <div class="main-header">
            <h2 class="topheader"><a class="logo" href="index.html">Fiserv CFO</a></h2>
        </div>
        <nav class="centertabs">
            <ul class="other_tabs1">{items}
            </ul>
        </nav>
    </header>"""

# ─────────────────────────────────────────────────────────────
#  GROCERIES
# ─────────────────────────────────────────────────────────────
GROCERIES_MAIN = """    <main>
        <section class="page-hero">
            <div>
                <div class="sub-hero-badge">&#128722; Grocery Manager</div>
                <h1 class="sub-hero-title">Smart Grocery Planner</h1>
                <p class="sub-hero-tagline">Track, budget, and shop smarter every week</p>
                <p class="sub-hero-desc">Manage your grocery budget, build smart shopping lists, compare prices across stores, and track spending by category — all in one place.</p>
            </div>
            <div>
                <img class="sub-hero-img" src="https://cdn.pixabay.com/photo/2017/06/06/22/46/shopping-2378383_640.jpg" alt="Grocery Shopping">
            </div>
        </section>

        <div class="stats-bar">
            <div class="stat-card green"><span class="stat-icon">&#128722;</span><div class="stat-label">Monthly Budget</div><div class="stat-value">$600</div><div class="stat-sub">Set for March 2026</div></div>
            <div class="stat-card orange"><span class="stat-icon">&#128179;</span><div class="stat-label">Spent So Far</div><div class="stat-value">$387</div><div class="stat-sub">64% of budget used</div></div>
            <div class="stat-card teal"><span class="stat-icon">&#129001;</span><div class="stat-label">Remaining</div><div class="stat-value">$213</div><div class="stat-sub">3 days left in month</div></div>
            <div class="stat-card navy"><span class="stat-icon">&#128203;</span><div class="stat-label">Items on List</div><div class="stat-value">18</div><div class="stat-sub">4 already picked up</div></div>
        </div>

        <div class="two-col">
            <div class="content-card">
                <div class="content-card-title">&#128203; Shopping List <span style="margin-left:auto;font-size:12px;font-weight:500;color:var(--orange);cursor:pointer">+ Add Item</span></div>
                <div class="check-item check-done"><input type="checkbox" id="g1" checked onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g1">Organic Whole Milk <span class="check-qty">1 gal</span></label><span class="check-price">$5.99</span></div>
                <div class="check-item check-done"><input type="checkbox" id="g2" checked onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g2">Large Eggs <span class="check-qty">1 doz</span></label><span class="check-price">$4.29</span></div>
                <div class="check-item check-done"><input type="checkbox" id="g3" checked onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g3">Greek Yogurt <span class="check-qty">3 pack</span></label><span class="check-price">$6.49</span></div>
                <div class="check-item check-done"><input type="checkbox" id="g4" checked onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g4">Whole Wheat Bread <span class="check-qty">1 loaf</span></label><span class="check-price">$3.79</span></div>
                <div class="check-item"><input type="checkbox" id="g5" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g5">Chicken Breast <span class="check-qty">2 lbs</span></label><span class="check-price">$9.99</span></div>
                <div class="check-item"><input type="checkbox" id="g6" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g6">Atlantic Salmon <span class="check-qty">1 lb</span></label><span class="check-price">$12.99</span></div>
                <div class="check-item"><input type="checkbox" id="g7" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g7">Baby Spinach <span class="check-qty">5 oz bag</span></label><span class="check-price">$3.49</span></div>
                <div class="check-item"><input type="checkbox" id="g8" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g8">Avocados <span class="check-qty">3 ct</span></label><span class="check-price">$4.99</span></div>
                <div class="check-item"><input type="checkbox" id="g9" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g9">Gala Apples <span class="check-qty">3 lb bag</span></label><span class="check-price">$5.49</span></div>
                <div class="check-item"><input type="checkbox" id="g10" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g10">Extra Virgin Olive Oil <span class="check-qty">16 oz</span></label><span class="check-price">$8.99</span></div>
                <div class="check-item"><input type="checkbox" id="g11" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g11">Brown Rice <span class="check-qty">2 lb bag</span></label><span class="check-price">$3.29</span></div>
                <div class="check-item"><input type="checkbox" id="g12" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g12">Penne Pasta <span class="check-qty">3 boxes</span></label><span class="check-price">$3.99</span></div>
                <div class="check-item"><input type="checkbox" id="g13" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g13">Sharp Cheddar <span class="check-qty">8 oz block</span></label><span class="check-price">$4.99</span></div>
                <div class="check-item"><input type="checkbox" id="g14" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g14">Orange Juice <span class="check-qty">64 oz</span></label><span class="check-price">$5.79</span></div>
                <div class="check-item"><input type="checkbox" id="g15" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g15">Broccoli <span class="check-qty">1 head</span></label><span class="check-price">$1.99</span></div>
                <div class="check-item"><input type="checkbox" id="g16" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g16">Fresh Blueberries <span class="check-qty">1 pint</span></label><span class="check-price">$4.49</span></div>
                <div class="check-item"><input type="checkbox" id="g17" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g17">Roma Tomatoes <span class="check-qty">4 ct</span></label><span class="check-price">$2.49</span></div>
                <div class="check-item"><input type="checkbox" id="g18" onchange="this.closest('.check-item').classList.toggle('check-done',this.checked)"><label class="check-label" for="g18">Raw Almonds <span class="check-qty">16 oz bag</span></label><span class="check-price">$9.99</span></div>
            </div>
            <div>
                <div class="content-card">
                    <div class="content-card-title">&#128202; Budget by Category</div>
                    <div class="cat-row"><div class="cat-header"><span class="cat-name">&#129382; Produce</span><span class="cat-amounts">$82 / $150</span></div><div class="progress-wrap"><div class="progress-bar green" style="width:55%"></div></div></div>
                    <div class="cat-row"><div class="cat-header"><span class="cat-name">&#129385; Meat &amp; Fish</span><span class="cat-amounts">$98 / $120</span></div><div class="progress-wrap"><div class="progress-bar" style="width:82%"></div></div></div>
                    <div class="cat-row"><div class="cat-header"><span class="cat-name">&#129371; Dairy &amp; Eggs</span><span class="cat-amounts">$72 / $80</span></div><div class="progress-wrap"><div class="progress-bar red" style="width:90%"></div></div></div>
                    <div class="cat-row"><div class="cat-header"><span class="cat-name">&#127807; Pantry Staples</span><span class="cat-amounts">$65 / $90</span></div><div class="progress-wrap"><div class="progress-bar" style="width:72%"></div></div></div>
                    <div class="cat-row"><div class="cat-header"><span class="cat-name">&#129381; Beverages</span><span class="cat-amounts">$38 / $60</span></div><div class="progress-wrap"><div class="progress-bar green" style="width:63%"></div></div></div>
                    <div class="cat-row"><div class="cat-header"><span class="cat-name">&#127839; Snacks</span><span class="cat-amounts">$32 / $50</span></div><div class="progress-wrap"><div class="progress-bar green" style="width:64%"></div></div></div>
                </div>
                <div class="content-card">
                    <div class="content-card-title">&#127978; Store Price Comparison</div>
                    <div class="list-item"><div class="list-icon orange">&#128722;</div><div class="list-info"><div class="list-name">Walmart Supercenter</div><div class="list-sub">Lowest everyday prices</div></div><div><div class="list-amount">$81.37</div><div style="text-align:right;margin-top:4px"><span class="badge badge-green">Cheapest</span></div></div></div>
                    <div class="list-item"><div class="list-icon green">&#128722;</div><div class="list-info"><div class="list-name">Trader Joe's</div><div class="list-sub">Best quality-to-price ratio</div></div><div class="list-amount">$94.20</div></div>
                    <div class="list-item"><div class="list-icon blue">&#128722;</div><div class="list-info"><div class="list-name">Target</div><div class="list-sub">RedCard saves 5%</div></div><div class="list-amount">$99.80</div></div>
                    <div class="list-item"><div class="list-icon gray">&#128722;</div><div class="list-info"><div class="list-name">Whole Foods Market</div><div class="list-sub">Prime member discounts</div></div><div class="list-amount">$112.45</div></div>
                </div>
            </div>
        </div>
        <div class="quick-actions">
            <button class="action-btn">&#10133; Add Item</button>
            <button class="action-btn">&#128228; Share List</button>
            <button class="action-btn">&#128260; Reorder Last Trip</button>
            <button class="action-btn">&#128202; Monthly Report</button>
            <button class="action-btn">&#127978; Find Deals Nearby</button>
        </div>
    </main>"""

# ─────────────────────────────────────────────────────────────
#  SCHOOL
# ─────────────────────────────────────────────────────────────
SCHOOL_MAIN = """    <main>
        <section class="page-hero">
            <div>
                <div class="sub-hero-badge">&#128218; Education Finance</div>
                <h1 class="sub-hero-title">School Finance Tracker</h1>
                <p class="sub-hero-tagline">Manage every school expense with ease</p>
                <p class="sub-hero-desc">Track tuition payments, school fees, activity costs, and grow your education savings fund — stay ahead of every upcoming payment.</p>
            </div>
            <div>
                <img class="sub-hero-img" src="https://cdn.pixabay.com/photo/2016/11/19/22/12/books-1842243_640.jpg" alt="Education">
            </div>
        </section>

        <div class="stats-bar">
            <div class="stat-card purple"><span class="stat-icon">&#127979;</span><div class="stat-label">Annual Tuition</div><div class="stat-value">$24,000</div><div class="stat-sub">2025-2026 school year</div></div>
            <div class="stat-card green"><span class="stat-icon">&#9989;</span><div class="stat-label">Paid to Date</div><div class="stat-value">$18,000</div><div class="stat-sub">75% of year complete</div></div>
            <div class="stat-card red"><span class="stat-icon">&#128197;</span><div class="stat-label">Next Payment</div><div class="stat-value">$6,000</div><div class="stat-sub">Due Mar 1 — 1 day away</div></div>
            <div class="stat-card navy"><span class="stat-icon">&#127381;</span><div class="stat-label">Education Fund</div><div class="stat-value">$45,000</div><div class="stat-sub">56% to $80K goal</div></div>
        </div>

        <!-- Education Savings Goal -->
        <div class="savings-goal">
            <div class="savings-title">&#127381; Education Savings Fund</div>
            <div class="savings-amount">$45,000</div>
            <div class="savings-sub">saved toward $80,000 college goal</div>
            <div class="savings-progress-wrap">
                <div class="savings-fill" style="width:56.25%"></div>
            </div>
            <div class="savings-meta">
                <span>56% complete</span>
                <span>$35,000 remaining</span>
            </div>
        </div>

        <div class="two-col">
            <div class="content-card">
                <div class="content-card-title">&#128197; Upcoming Payments</div>

                <div class="timeline-item">
                    <div class="timeline-dot red"></div>
                    <div class="timeline-info">
                        <div class="timeline-name">Q4 Tuition Payment</div>
                        <div class="timeline-date">Due Mar 1, 2026 &mdash; <span style="color:#EF4444;font-weight:600">1 day away</span></div>
                    </div>
                    <div>
                        <div class="timeline-amount">$6,000</div>
                        <span class="badge badge-red">Urgent</span>
                    </div>
                </div>

                <div class="timeline-item">
                    <div class="timeline-dot orange"></div>
                    <div class="timeline-info">
                        <div class="timeline-name">Spring Semester Activity Fee</div>
                        <div class="timeline-date">Due Mar 15, 2026</div>
                    </div>
                    <div>
                        <div class="timeline-amount">$150</div>
                        <span class="badge badge-orange">Soon</span>
                    </div>
                </div>

                <div class="timeline-item">
                    <div class="timeline-dot blue"></div>
                    <div class="timeline-info">
                        <div class="timeline-name">Spring Field Trip</div>
                        <div class="timeline-date">Due Mar 20, 2026</div>
                    </div>
                    <div>
                        <div class="timeline-amount">$85</div>
                        <span class="badge badge-blue">Upcoming</span>
                    </div>
                </div>

                <div class="timeline-item">
                    <div class="timeline-dot blue"></div>
                    <div class="timeline-info">
                        <div class="timeline-name">Yearbook Order</div>
                        <div class="timeline-date">Due Apr 1, 2026</div>
                    </div>
                    <div>
                        <div class="timeline-amount">$65</div>
                        <span class="badge badge-blue">Upcoming</span>
                    </div>
                </div>

                <div class="timeline-item">
                    <div class="timeline-dot gray"></div>
                    <div class="timeline-info">
                        <div class="timeline-name">Sports Equipment Fund</div>
                        <div class="timeline-date">Due Apr 15, 2026</div>
                    </div>
                    <div>
                        <div class="timeline-amount">$120</div>
                        <span class="badge badge-gray">Scheduled</span>
                    </div>
                </div>
            </div>

            <div class="content-card">
                <div class="content-card-title">&#128202; Expense Breakdown</div>

                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#127979; Tuition</span><span class="cat-amounts">$18,000 / $24,000</span></div>
                    <div class="progress-wrap"><div class="progress-bar purple" style="width:75%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128218; Books &amp; Supplies</span><span class="cat-amounts">$450 / $600</span></div>
                    <div class="progress-wrap"><div class="progress-bar" style="width:75%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#9917; Activities &amp; Clubs</span><span class="cat-amounts">$275 / $400</span></div>
                    <div class="progress-wrap"><div class="progress-bar green" style="width:69%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128084; Uniforms &amp; Clothing</span><span class="cat-amounts">$320 / $350</span></div>
                    <div class="progress-wrap"><div class="progress-bar red" style="width:91%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#127829; Lunch Account</span><span class="cat-amounts">$180 / $800</span></div>
                    <div class="progress-wrap"><div class="progress-bar green" style="width:22%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128640; School Trips</span><span class="cat-amounts">$85 / $200</span></div>
                    <div class="progress-wrap"><div class="progress-bar green" style="width:42%"></div></div>
                </div>

                <div style="margin-top:20px">
                    <div class="content-card-title" style="border-bottom:none;margin-bottom:12px;padding-bottom:0">&#128200; Recent School Payments</div>
                    <div class="list-item"><div class="list-icon purple">&#127979;</div><div class="list-info"><div class="list-name">Q3 Tuition</div><div class="list-sub">Dec 1, 2025</div></div><div class="list-amount negative">&#8722;$6,000</div></div>
                    <div class="list-item"><div class="list-icon orange">&#127829;</div><div class="list-info"><div class="list-name">Lunch Account Top-Up</div><div class="list-sub">Feb 15, 2026</div></div><div class="list-amount negative">&#8722;$100</div></div>
                    <div class="list-item"><div class="list-icon blue">&#128218;</div><div class="list-info"><div class="list-name">Spring Semester Textbooks</div><div class="list-sub">Jan 20, 2026</div></div><div class="list-amount negative">&#8722;$187</div></div>
                </div>
            </div>
        </div>

        <div class="quick-actions">
            <button class="action-btn">&#128179; Pay Tuition</button>
            <button class="action-btn">&#127381; Add to Savings</button>
            <button class="action-btn">&#128197; Payment Calendar</button>
            <button class="action-btn">&#128202; Annual Report</button>
            <button class="action-btn">&#128217; Track Expenses</button>
        </div>
    </main>"""

# ─────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────
UTILITIES_MAIN = """    <main>
        <section class="page-hero">
            <div>
                <div class="sub-hero-badge">&#9889; Utilities Manager</div>
                <h1 class="sub-hero-title">Household Utilities Hub</h1>
                <p class="sub-hero-tagline">Never miss a bill again</p>
                <p class="sub-hero-desc">Track all your household bills — electric, water, gas, internet, and more. Set auto-pay, monitor usage, and stay ahead of every due date.</p>
            </div>
            <div>
                <img class="sub-hero-img" src="https://cdn.pixabay.com/photo/2016/10/28/12/18/electricity-1776246_640.jpg" alt="Utilities">
            </div>
        </section>

        <div class="stats-bar">
            <div class="stat-card navy"><span class="stat-icon">&#128176;</span><div class="stat-label">Total Monthly</div><div class="stat-value">$554</div><div class="stat-sub">All 6 utilities combined</div></div>
            <div class="stat-card blue"><span class="stat-icon">&#128197;</span><div class="stat-label">Due This Week</div><div class="stat-value">$127</div><div class="stat-sub">Electric bill due Mar 5</div></div>
            <div class="stat-card green"><span class="stat-icon">&#9989;</span><div class="stat-label">Auto-Pay Active</div><div class="stat-value">5 / 6</div><div class="stat-sub">Internet needs attention</div></div>
            <div class="stat-card orange"><span class="stat-icon">&#128200;</span><div class="stat-label">Avg Daily Cost</div><div class="stat-value">$18.48</div><div class="stat-sub">Based on 30-day month</div></div>
        </div>

        <div class="section-sub">Your Bills <span>+ Add Bill</span></div>
        <div class="bill-grid">
            <div class="bill-card">
                <div class="bill-header">
                    <div class="bill-icon">&#9889;</div>
                    <div><div class="bill-name">Electricity</div><div class="bill-provider">Duke Energy</div></div>
                </div>
                <div><div class="bill-amount">$127.50</div><div class="bill-due">Due Mar 5 &mdash; 5 days away &bull; 892 kWh used</div></div>
                <div class="bill-footer">
                    <span class="badge badge-orange">Due Soon</span>
                    <label class="toggle-wrap">Auto-Pay
                        <label class="toggle"><input type="checkbox" checked><span class="toggle-slider"></span></label>
                    </label>
                </div>
            </div>

            <div class="bill-card">
                <div class="bill-header">
                    <div class="bill-icon">&#128167;</div>
                    <div><div class="bill-name">Water</div><div class="bill-provider">City Water Works</div></div>
                </div>
                <div><div class="bill-amount">$45.00</div><div class="bill-due">Due Mar 8 &mdash; 4,200 gallons used</div></div>
                <div class="bill-footer">
                    <span class="badge badge-blue">Upcoming</span>
                    <label class="toggle-wrap">Auto-Pay
                        <label class="toggle"><input type="checkbox" checked><span class="toggle-slider"></span></label>
                    </label>
                </div>
            </div>

            <div class="bill-card">
                <div class="bill-header">
                    <div class="bill-icon">&#128293;</div>
                    <div><div class="bill-name">Natural Gas</div><div class="bill-provider">National Gas Co.</div></div>
                </div>
                <div><div class="bill-amount">$89.00</div><div class="bill-due">Due Mar 10 &mdash; 42 therms used</div></div>
                <div class="bill-footer">
                    <span class="badge badge-blue">Upcoming</span>
                    <label class="toggle-wrap">Auto-Pay
                        <label class="toggle"><input type="checkbox" checked><span class="toggle-slider"></span></label>
                    </label>
                </div>
            </div>

            <div class="bill-card">
                <div class="bill-header">
                    <div class="bill-icon">&#128246;</div>
                    <div><div class="bill-name">Internet</div><div class="bill-provider">Comcast Xfinity</div></div>
                </div>
                <div><div class="bill-amount">$79.99</div><div class="bill-due">Due Mar 12 &mdash; 500 Mbps plan</div></div>
                <div class="bill-footer">
                    <span class="badge badge-red">Manual Pay</span>
                    <label class="toggle-wrap">Auto-Pay
                        <label class="toggle"><input type="checkbox"><span class="toggle-slider"></span></label>
                    </label>
                </div>
            </div>

            <div class="bill-card">
                <div class="bill-header">
                    <div class="bill-icon">&#128241;</div>
                    <div><div class="bill-name">Cell Phone</div><div class="bill-provider">Verizon Wireless</div></div>
                </div>
                <div><div class="bill-amount">$165.00</div><div class="bill-due">Due Mar 15 &mdash; 4 lines, unlimited</div></div>
                <div class="bill-footer">
                    <span class="badge badge-gray">Scheduled</span>
                    <label class="toggle-wrap">Auto-Pay
                        <label class="toggle"><input type="checkbox" checked><span class="toggle-slider"></span></label>
                    </label>
                </div>
            </div>

            <div class="bill-card">
                <div class="bill-header">
                    <div class="bill-icon">&#127916;</div>
                    <div><div class="bill-name">Streaming Bundle</div><div class="bill-provider">Netflix + Hulu + Spotify</div></div>
                </div>
                <div><div class="bill-amount">$47.97</div><div class="bill-due">Due Mar 20 &mdash; 3 services bundled</div></div>
                <div class="bill-footer">
                    <span class="badge badge-gray">Scheduled</span>
                    <label class="toggle-wrap">Auto-Pay
                        <label class="toggle"><input type="checkbox" checked><span class="toggle-slider"></span></label>
                    </label>
                </div>
            </div>
        </div>

        <div class="two-col">
            <div class="content-card">
                <div class="content-card-title">&#128200; Usage vs Last Month</div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#9889; Electricity</span><span class="cat-amounts">892 kWh &mdash; &#9660; 8% vs Feb</span></div>
                    <div class="progress-wrap"><div class="progress-bar green" style="width:74%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128167; Water</span><span class="cat-amounts">4,200 gal &mdash; &#9650; 3% vs Feb</span></div>
                    <div class="progress-wrap"><div class="progress-bar" style="width:60%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128293; Natural Gas</span><span class="cat-amounts">42 therms &mdash; &#9660; 15% vs Feb</span></div>
                    <div class="progress-wrap"><div class="progress-bar green" style="width:55%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128246; Internet Data</span><span class="cat-amounts">847 GB &mdash; &#9650; 12% vs Feb</span></div>
                    <div class="progress-wrap"><div class="progress-bar" style="width:85%"></div></div>
                </div>
            </div>

            <div class="content-card">
                <div class="content-card-title">&#128200; Payment History</div>
                <div class="list-item"><div class="list-icon green">&#9889;</div><div class="list-info"><div class="list-name">Duke Energy &mdash; Electricity</div><div class="list-sub">Feb 5, 2026 &bull; Auto-Pay</div></div><div class="list-amount negative">&#8722;$134.20</div></div>
                <div class="list-item"><div class="list-icon blue">&#128167;</div><div class="list-info"><div class="list-name">City Water Works</div><div class="list-sub">Feb 8, 2026 &bull; Auto-Pay</div></div><div class="list-amount negative">&#8722;$43.50</div></div>
                <div class="list-item"><div class="list-icon orange">&#128293;</div><div class="list-info"><div class="list-name">National Gas Co.</div><div class="list-sub">Feb 10, 2026 &bull; Auto-Pay</div></div><div class="list-amount negative">&#8722;$104.75</div></div>
                <div class="list-item"><div class="list-icon purple">&#128246;</div><div class="list-info"><div class="list-name">Comcast Xfinity</div><div class="list-sub">Feb 12, 2026 &bull; Manual</div></div><div class="list-amount negative">&#8722;$79.99</div></div>
                <div class="list-item"><div class="list-icon teal">&#128241;</div><div class="list-info"><div class="list-name">Verizon Wireless</div><div class="list-sub">Feb 15, 2026 &bull; Auto-Pay</div></div><div class="list-amount negative">&#8722;$165.00</div></div>
                <div class="list-item"><div class="list-icon gray">&#127916;</div><div class="list-info"><div class="list-name">Streaming Bundle</div><div class="list-sub">Feb 20, 2026 &bull; Auto-Pay</div></div><div class="list-amount negative">&#8722;$47.97</div></div>
            </div>
        </div>

        <div class="quick-actions">
            <button class="action-btn">&#10133; Add Bill</button>
            <button class="action-btn">&#9989; Enable All Auto-Pay</button>
            <button class="action-btn">&#128200; Usage Report</button>
            <button class="action-btn">&#128176; Set Budget Alerts</button>
            <button class="action-btn">&#128197; View Calendar</button>
        </div>
    </main>"""

# ─────────────────────────────────────────────────────────────
#  WORK
# ─────────────────────────────────────────────────────────────
WORK_MAIN = """    <main>
        <section class="page-hero">
            <div>
                <div class="sub-hero-badge">&#128188; Work Finance</div>
                <h1 class="sub-hero-title">Professional Finance Hub</h1>
                <p class="sub-hero-tagline">Track income, expenses &amp; tax deductions</p>
                <p class="sub-hero-desc">Manage your professional earnings, log business expenses, track mileage, and maximize tax deductions — your complete work finance command center.</p>
            </div>
            <div>
                <img class="sub-hero-img" src="https://cdn.pixabay.com/photo/2020/01/09/09/22/office-4751416_640.jpg" alt="Professional Finance">
            </div>
        </section>

        <!-- Income Card -->
        <div class="income-card">
            <div class="income-label">&#128200; Monthly Gross Income</div>
            <div class="income-amount">$8,500</div>
            <div class="income-period">March 2026 &bull; Annual: $102,000/yr</div>
            <div class="income-row">
                <div class="income-item">
                    <span class="income-label">Base Salary</span>
                    <strong>$7,500</strong>
                </div>
                <div class="income-item">
                    <span class="income-label">Performance Bonus</span>
                    <strong>$1,000</strong>
                </div>
                <div class="income-item">
                    <span class="income-label">YTD Total</span>
                    <strong>$22,500</strong>
                </div>
            </div>
        </div>

        <div class="stats-bar">
            <div class="stat-card red"><span class="stat-icon">&#128202;</span><div class="stat-label">Business Expenses</div><div class="stat-value">$1,247</div><div class="stat-sub">This month so far</div></div>
            <div class="stat-card green"><span class="stat-icon">&#128176;</span><div class="stat-label">Tax Deductions</div><div class="stat-value">$620</div><div class="stat-sub">Estimated this month</div></div>
            <div class="stat-card blue"><span class="stat-icon">&#128664;</span><div class="stat-label">Mileage Tracked</div><div class="stat-value">245 mi</div><div class="stat-sub">$164 deductible @$0.67/mi</div></div>
            <div class="stat-card teal"><span class="stat-icon">&#128176;</span><div class="stat-label">Net Earnings</div><div class="stat-value">$7,253</div><div class="stat-sub">After business expenses</div></div>
        </div>

        <div class="two-col">
            <div class="content-card">
                <div class="content-card-title">&#128202; Expenses by Category</div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128187; Software &amp; Tools</span><span class="cat-amounts">$127 &mdash; <span style="color:#059669">100% deductible</span></span></div>
                    <div class="progress-wrap"><div class="progress-bar teal" style="width:100%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#127829; Business Meals</span><span class="cat-amounts">$187 &mdash; <span style="color:#D97706">50% deductible</span></span></div>
                    <div class="progress-wrap"><div class="progress-bar" style="width:100%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128664; Travel &amp; Mileage</span><span class="cat-amounts">$164 &mdash; <span style="color:#059669">100% deductible</span></span></div>
                    <div class="progress-wrap"><div class="progress-bar teal" style="width:100%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128187; Equipment &amp; Tech</span><span class="cat-amounts">$299 &mdash; <span style="color:#059669">100% deductible</span></span></div>
                    <div class="progress-wrap"><div class="progress-bar teal" style="width:100%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#127891; Professional Dev</span><span class="cat-amounts">$199 &mdash; <span style="color:#059669">100% deductible</span></span></div>
                    <div class="progress-wrap"><div class="progress-bar teal" style="width:100%"></div></div>
                </div>
                <div class="cat-row">
                    <div class="cat-header"><span class="cat-name">&#128203; Office Supplies</span><span class="cat-amounts">$87 &mdash; <span style="color:#059669">100% deductible</span></span></div>
                    <div class="progress-wrap"><div class="progress-bar teal" style="width:100%"></div></div>
                </div>

                <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--gray-100)">
                    <div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:8px"><span style="font-weight:600;color:var(--text-dark)">Total Business Expenses</span><span style="font-weight:700">$1,063</span></div>
                    <div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:8px"><span style="color:var(--gray-500)">Non-deductible (meals 50%)</span><span style="color:#DC2626">$93.75</span></div>
                    <div style="display:flex;justify-content:space-between;font-size:15px;font-weight:700;color:#059669"><span>Total Tax Deductions</span><span>$969.25</span></div>
                </div>
            </div>

            <div class="content-card">
                <div class="content-card-title">&#128200; Recent Work Expenses</div>

                <div class="list-item">
                    <div class="list-icon teal">&#128187;</div>
                    <div class="list-info"><div class="list-name">Adobe Creative Cloud</div><div class="list-sub">Mar 1 &bull; Software &bull; <span style="color:#059669">Deductible</span></div></div>
                    <div><div class="list-amount negative">&#8722;$54.99</div></div>
                </div>
                <div class="list-item">
                    <div class="list-icon orange">&#127829;</div>
                    <div class="list-info"><div class="list-name">Client Lunch &mdash; Morton's Steakhouse</div><div class="list-sub">Feb 28 &bull; Business Meal &bull; <span style="color:#D97706">50% deductible</span></div></div>
                    <div><div class="list-amount negative">&#8722;$127.50</div></div>
                </div>
                <div class="list-item">
                    <div class="list-icon teal">&#128187;</div>
                    <div class="list-info"><div class="list-name">Ergonomic Laptop Stand</div><div class="list-sub">Feb 25 &bull; Equipment &bull; <span style="color:#059669">Deductible</span></div></div>
                    <div><div class="list-amount negative">&#8722;$149.00</div></div>
                </div>
                <div class="list-item">
                    <div class="list-icon purple">&#127891;</div>
                    <div class="list-info"><div class="list-name">LinkedIn Premium</div><div class="list-sub">Feb 24 &bull; Professional Dev &bull; <span style="color:#059669">Deductible</span></div></div>
                    <div><div class="list-amount negative">&#8722;$39.99</div></div>
                </div>
                <div class="list-item">
                    <div class="list-icon blue">&#128664;</div>
                    <div class="list-info"><div class="list-name">Client Office Parking</div><div class="list-sub">Feb 22 &bull; Travel &bull; <span style="color:#059669">Deductible</span></div></div>
                    <div><div class="list-amount negative">&#8722;$25.00</div></div>
                </div>
                <div class="list-item">
                    <div class="list-icon gray">&#128203;</div>
                    <div class="list-info"><div class="list-name">Amazon Office Supplies</div><div class="list-sub">Feb 20 &bull; Office &bull; <span style="color:#059669">Deductible</span></div></div>
                    <div><div class="list-amount negative">&#8722;$87.00</div></div>
                </div>

                <!-- Mileage tracker -->
                <div style="margin-top:16px;padding:16px;background:var(--gray-50);border-radius:var(--radius-sm)">
                    <div style="font-size:14px;font-weight:700;margin-bottom:8px">&#128664; Mileage Log &mdash; March 2026</div>
                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;font-size:13px">
                        <div><div style="color:var(--gray-500)">Miles Driven</div><div style="font-weight:700;font-size:18px">245</div></div>
                        <div><div style="color:var(--gray-500)">IRS Rate</div><div style="font-weight:700;font-size:18px">$0.67</div></div>
                        <div><div style="color:var(--gray-500)">Deduction</div><div style="font-weight:700;font-size:18px;color:#059669">$164.15</div></div>
                    </div>
                </div>
            </div>
        </div>

        <div class="quick-actions">
            <button class="action-btn">&#10133; Log Expense</button>
            <button class="action-btn">&#128664; Log Miles</button>
            <button class="action-btn">&#128176; Tax Summary</button>
            <button class="action-btn">&#128228; Export for CPA</button>
            <button class="action-btn">&#128200; Income Report</button>
        </div>
    </main>"""

# Write files
files = [
    ("groceries.html", "groceries", GROCERIES_MAIN),
    ("school.html",    "school",    SCHOOL_MAIN),
    ("utilities.html", "utilities", UTILITIES_MAIN),
    ("work.html",      "work",      WORK_MAIN),
]

for filename, active_tab, main_content in files:
    html = HEAD(active_tab.capitalize()) + "\n" + nav(active_tab) + "\n" + main_content + "\n" + FOOT
    with open(filename, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  wrote {filename}")

print("All done!")
