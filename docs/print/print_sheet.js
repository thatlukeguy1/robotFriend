// Turns check-sheet.html into check-sheet.pdf at exactly A4, actual size, plus a PNG per page.
//   python docs/print/make_check_sheet.py && node docs/print/print_sheet.js
const { chromium } = require("playwright");
const path = require("path");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 794, height: 1123 }, deviceScaleFactor: 2 });
  await page.goto("file://" + path.join(__dirname, "check-sheet.html"));
  await page.pdf({ path: path.join(__dirname, "check-sheet.pdf"), format: "A4", printBackground: true });
  const pages = await page.$$("svg.page");
  for (let i = 0; i < pages.length; i++) await pages[i].screenshot({ path: path.join(__dirname, `check-sheet-${i + 1}.png`) });
  console.log("Wrote", path.join(__dirname, "check-sheet.pdf"));
  await browser.close();
})();
