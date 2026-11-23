/*
 * LESSON: Stickers
 * ================
 * Riley's hat and thinking hand are PICTURES ("stickers"), not shapes worked
 * out in code. Each is drawn as an SVG (a drawing made of curves, which can be
 * any size without going blurry) and turned into a PNG (a picture with a
 * see-through background) by this script, using the Chromium web browser.
 * The face code (web/face.js and pi/bolt_body/face.py) only places, tilts and
 * fades them, so the same pictures show on the Pi and in the browser.
 *
 * stickers.json says where each one goes. To change a drawing: edit its .svg,
 * then run this (on a computer with Node and Playwright), and commit the .png:
 *
 *     cd web/stickers && node make_stickers.js
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  for (const file of fs.readdirSync(__dirname).filter((f) => f.endsWith(".svg"))) {
    const svg = fs.readFileSync(path.join(__dirname, file), "utf8");
    const width = +svg.match(/width="(\d+)"/)[1], height = +svg.match(/height="(\d+)"/)[1];
    const page = await browser.newPage({ viewport: { width, height } });
    await page.setContent(`<body style="margin:0;background:transparent">${svg}</body>`);
    const out = file.replace(/\.svg$/, ".png");
    await page.screenshot({ path: path.join(__dirname, out), omitBackground: true });
    console.log(`${file} -> ${out} (${width} x ${height})`);
    await page.close();
  }
  await browser.close();
})();
