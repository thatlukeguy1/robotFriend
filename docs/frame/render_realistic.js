// Renders render.html (Riley in 3D) to render.png with headless Chromium.
//   python docs/frame/make_render.py && node docs/frame/render_realistic.js [hero|front|close]
// The page's files are served straight from this folder, and three.js from a local copy if
// there is one (npm install three@0.160.0), otherwise from the internet.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
const view = process.argv[2] || "hero";
const local = [path.join(HERE, "node_modules/three"), process.env.THREE_DIR].filter(Boolean).find((d) => fs.existsSync(d));

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({ viewport: { width: 2400, height: 1600 } });
  page.on("pageerror", (e) => console.error("page error:", e.message));
  page.on("console", (m) => { if (m.type() === "error") console.error("console:", m.text()); });
  await page.route("http://riley.local/**", (route) => {
    const file = path.join(HERE, new URL(route.request().url()).pathname);
    const type = file.endsWith(".html") ? "text/html" : file.endsWith(".json") ? "application/json" : "image/png";
    route.fulfill({ body: fs.readFileSync(file), contentType: type });
  });
  if (local) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.160.0/**", (route) => {
      const rel = new URL(route.request().url()).pathname.replace("/npm/three@0.160.0/", "");
      route.fulfill({ body: fs.readFileSync(path.join(local, rel)), contentType: "text/javascript" });
    });
  }
  await page.goto(`http://riley.local/render.html?view=${view}`);
  await page.waitForFunction("window.renderDone === true", null, { timeout: 600000 });
  const out = path.join(HERE, view === "hero" ? "render.png" : `render-${view}.png`);
  const png = await page.evaluate(() => document.querySelector("body > canvas").toDataURL("image/png"));
  fs.writeFileSync(out, Buffer.from(png.split(",")[1], "base64"));
  console.log("Wrote", out);
  await browser.close();
})();
