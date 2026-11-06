// Small shared widgets: the wallet chip, the sound button, the shop link, a side crest, and a stat tile.
import { h, icon, toast } from "./dom.js";

const SOUND_NEXT = { on: "fx", fx: "off", off: "on" };
const SOUND_LABEL = { on: "Sound on", fx: "Effects only", off: "Sound off" };
const SOUND_ICON = { on: "sound", fx: "soundFx", off: "mute" };
/** Cycles the sound: everything, effects only, off (S toggles too). `block` makes a labelled menu row. */
export function soundButton(app, { block = false } = {}) {
  const b = h("button", { class: block ? "btn ghost block" : "icon-btn sound-btn", type: "button", data: { sfx: "none" }, on: { click: () => app.setSoundMode(SOUND_NEXT[app.soundMode()]) } });
  const render = () => {
    const m = app.soundMode();
    b.replaceChildren(icon(SOUND_ICON[m]), ...(block ? [SOUND_LABEL[m]] : []));
    b.title = `${SOUND_LABEL[m]} · S`;
    b.setAttribute("aria-label", `${SOUND_LABEL[m]}: change`);
  };
  const off = app.onSound(() => { if (b.isConnected) render(); else off(); });
  render();
  return b;
}

/** Connect button, or address and held count once connected. Keeps itself current. Hidden for a game without a collection. */
export function walletChip(app) {
  const label = h("span", { class: "wc-label" });
  const sub = h("span", { class: "wc-sub tabnum" });
  const chip = h("button", { class: "wallet-chip", type: "button", hidden: !app.hasWallet, on: { click: () => void app.toggleWallet().catch((e) => toast(e.message, "err")) } },
    h("span", { class: "wc-ico" }, icon("wallet")), h("span", { class: "wc-text" }, label, sub));
  const render = () => {
    const addr = app.walletShort();
    chip.classList.toggle("on", !!addr);
    label.textContent = addr || "Connect wallet";
    sub.textContent = addr ? `${app.owned.size} held` : app.snap.collection.network || "Liteforge";
  };
  app.onWallet(render);
  render();
  return chip;
}

/** A link to the game's shop (index.html's tessaract-shop meta) in a new tab, or null when the game has none. */
export function shopLink(app, cls, ...children) {
  if (!app.shop) return null;
  return h("a", { class: cls, href: app.shop.url, target: "_blank", rel: "noopener", on: { click: () => app.leftForShop() } }, ...children);
}

export function crest(side, cls = "") {
  return h("span", { class: `crest ${side === 0 ? "you" : "foe"} ${cls}` }, icon(side === 0 ? "you" : "foe"));
}

export function tile(value, label) {
  return h("div", { class: "tile" }, h("b", { class: "tabnum", text: value }), h("span", { text: label }));
}
