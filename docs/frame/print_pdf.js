// Turns frame-template.html into an exactly-A4 PDF, at actual size.
// Usage (from the project folder):  node docs/frame/print_pdf.js
const { chromium } = require("playwright");
const path = require("path");

(async () => {
  const html = path.join(__dirname, "frame-template.html");
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto("file://" + html);
  await page.pdf({ path: path.join(__dirname, "frame-template.pdf"), format: "A4", printBackground: true,
                   preferCSSPageSize: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  await browser.close();
  console.log("Wrote", path.join(__dirname, "frame-template.pdf"));
})();
