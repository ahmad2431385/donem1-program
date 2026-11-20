// Yayın adımı: sayfadaki betikleri okunamaz hâle getirir (küçültmeden sonra çalışır).
// Kullanım: node tools/obfuscate.js girdi.html çıktı.html   — hata olursa çıkış kodu 1 (yayın küçültülmüş sayfayla sürer)
const fs = require("fs");
const JO = require("javascript-obfuscator");
const [, , inp, out] = process.argv;
const html = fs.readFileSync(inp, "utf8");
const OPT = {
  compact: true, target: "browser", identifierNamesGenerator: "hexadecimal", renameGlobals: false,
  stringArray: true, stringArrayEncoding: ["base64"], stringArrayThreshold: 0.75, stringArrayRotate: true, stringArrayShuffle: true,
  splitStrings: false, controlFlowFlattening: false, deadCodeInjection: false, selfDefending: false,
  transformObjectKeys: false, unicodeEscapeSequence: false, numbersToExpressions: false, simplify: true
};
let n = 0;
const res = html.replace(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi, (m, attrs = "", code) => {
  if (/\bsrc=/i.test(attrs) || /type=["']?(application\/(ld\+)?json|text\/template)/i.test(attrs) || code.trim().length < 40) return m;
  n++;
  const ob = JO.obfuscate(code, { ...OPT, seed: n }).getObfuscatedCode();
  if (/<\/script/i.test(ob)) throw new Error("karıştırılmış kodda </script> geçiyor");
  return `<script${attrs}>${ob}</script>`;
});
fs.writeFileSync(out, res);
console.log(`karıştırılan betik: ${n}; ${html.length} -> ${res.length} bayt`);
