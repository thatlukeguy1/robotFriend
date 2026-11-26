// Draws the neck's flat-pack instructions (neck-instructions.html), one PNG per step, and
// binds them into neck-instructions.pdf.
//   node docs/frame/make_instructions.js
// three.js comes from a local copy if there is one (THREE_DIR or docs/frame/node_modules/three).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
const OUT = path.join(HERE, "neck-instructions");
const local = [path.join(HERE, "node_modules/three"), process.env.THREE_DIR].filter(Boolean).find((d) => fs.existsSync(d));
const STEPS = 12;

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const page = await browser.newPage({ viewport: { width: 2000, height: 1414 } });
  page.on("pageerror", (e) => console.error("page error:", e.message));
  page.on("console", (m) => { if (m.type() === "error") console.error("console:", m.text()); });
  await page.route("http://riley.local/**", (route) => {
    const file = path.join(HERE, new URL(route.request().url()).pathname);
    route.fulfill({ body: fs.readFileSync(file), contentType: file.endsWith(".html") ? "text/html" : "application/octet-stream" });
  });
  if (local) {
    await page.route("https://cdn.jsdelivr.net/npm/three@0.160.0/**", (route) => {
      const rel = new URL(route.request().url()).pathname.replace("/npm/three@0.160.0/", "");
      route.fulfill({ body: fs.readFileSync(path.join(local, rel)), contentType: "text/javascript" });
    });
  }
  fs.mkdirSync(OUT, { recursive: true });
  const files = [];
  for (let s = 0; s < STEPS; s++) {
    await page.goto(`http://riley.local/neck-instructions.html?step=${s}`);
    await page.waitForFunction("window.done === true", null, { timeout: 300000 });
    const png = await page.evaluate(() => document.getElementById("page").toDataURL("image/png"));
    const file = path.join(OUT, `step-${String(s).padStart(2, "0")}.png`);
    fs.writeFileSync(file, Buffer.from(png.split(",")[1], "base64"));
    files.push(file);
    console.log("Wrote", file);
  }
  // bind the pages into one PDF: one image per A4 landscape page
  const book = await browser.newPage();
  const html = `<!doctype html><style>@page{size:A4 landscape;margin:0}body{margin:0}img{width:297mm;height:210mm;display:block;break-after:page}</style>` +
    files.map((f) => `<img src="data:image/png;base64,${fs.readFileSync(f).toString("base64")}">`).join("");
  await book.setContent(html);
  await book.pdf({ path: path.join(HERE, "neck-instructions.pdf"), format: "A4", landscape: true, printBackground: true });
  console.log("Wrote", path.join(HERE, "neck-instructions.pdf"));
  await browser.close();
})();
