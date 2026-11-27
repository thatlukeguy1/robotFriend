// Turns power-instructions.html into one PNG per page and an A4 landscape PDF.
//   python docs/power/make_power_instructions.py && node docs/power/print_power.js
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
const OUT = path.join(HERE, "power-instructions");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1123, height: 794 }, deviceScaleFactor: 2 });
  await page.goto("file://" + path.join(HERE, "power-instructions.html"));
  fs.mkdirSync(OUT, { recursive: true });
  const pages = await page.$$("svg.page");
  for (let i = 0; i < pages.length; i++) {
    const file = path.join(OUT, `page-${String(i + 1).padStart(2, "0")}.png`);
    await pages[i].screenshot({ path: file });
    console.log("Wrote", file);
  }
  await page.pdf({ path: path.join(HERE, "power-instructions.pdf"), format: "A4", landscape: true, printBackground: true });
  console.log("Wrote", path.join(HERE, "power-instructions.pdf"));
  await browser.close();
})();
