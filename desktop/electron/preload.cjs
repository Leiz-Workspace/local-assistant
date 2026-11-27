const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("aevraDesktop", Object.freeze({
  product: "Aevra",
  version: "0.1.0",
}));
