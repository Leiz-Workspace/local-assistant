const fs = require("node:fs");
const path = require("node:path");

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== "linux") return;
  const sandbox = path.join(context.appOutDir, "chrome-sandbox");
  fs.chmodSync(sandbox, 0o4755);
};
