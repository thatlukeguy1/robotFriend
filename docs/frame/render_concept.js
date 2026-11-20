// Turns concept.svg into concept.png.  Usage: node docs/frame/render_concept.js
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2 });
  await page.goto("file://" + path.join(__dirname, "concept.svg"));
  await page.screenshot({ path: path.join(__dirname, "concept.png") });
  await browser.close();
  console.log("Wrote", path.join(__dirname, "concept.png"));
})();
