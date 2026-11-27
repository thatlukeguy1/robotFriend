// Draws render.html to PNGs:  node docs/print/render.js [hero front side exploded]
// three.js comes from a local copy if there is one (THREE_DIR or docs/print/node_modules/three).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
const local = [path.join(HERE, "node_modules/three"), process.env.THREE_DIR].filter(Boolean).find((d) => fs.existsSync(d));
// or one part as it sits on the bed:  node docs/print/render.js part=head_front top under
const args = process.argv.slice(2);
const part = (args.find((a) => a.startsWith("part=")) || "").slice(5);
const named = args.filter((a) => !a.startsWith("part="));
const views = named.length ? named : part ? ["top", "under"] : ["hero", "front", "side", "exploded"];

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
  page.on("pageerror", (e) => console.error("page error:", e.message));
  await page.route("http://riley.local/**", (route) => {
    const file = path.join(HERE, new URL(route.request().url()).pathname);
    const type = file.endsWith(".html") ? "text/html" : file.endsWith(".json") ? "application/json" : file.endsWith(".png") ? "image/png" : "application/octet-stream";
    route.fulfill({ body: fs.readFileSync(file), contentType: type });
  });
  if (local) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.160.0/**", (route) => {
      const rel = new URL(route.request().url()).pathname.replace("/npm/three@0.160.0/", "");
      route.fulfill({ body: fs.readFileSync(path.join(local, rel)), contentType: "text/javascript" });
    });
  }
  for (const view of views) {
    await page.goto(`http://riley.local/render.html?view=${view}&w=1600&h=1100${part ? "&part=" + part : ""}`);
    await page.waitForFunction("window.renderDone === true", null, { timeout: 600000 });
    const png = await page.evaluate(() => document.querySelector("canvas").toDataURL("image/png"));
    const out = path.join(HERE, part ? `part-${part}-${view}.png` : `render-${view}.png`);
    fs.writeFileSync(out, Buffer.from(png.split(",")[1], "base64"));
    console.log("Wrote", out);
  }
  await browser.close();
})();
