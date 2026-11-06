// The installable app: registers the service worker, takes the page full screen on the player's taps, and keeps the
// browser's install offer for the title menu (homeScreen shows "Install app" while there is one).
//
// - Every tap that lands while the page is not full screen asks for full screen, on phones and desktops alike (the
//   browser bars hide). Full screen needs the activation of a tap, so it waits for the first one.
// - Where the browser offers an install (`beforeinstallprompt`: Chrome, Edge, Samsung Internet), a phone's first tap
//   opens the browser's own install dialog instead; the dialog uses up that tap, so full screen follows on the next.
//   On a desktop the offer waits for the menu.
// - iPhone and iPad Safari have neither an install API nor page full screen: the menu entry explains Share, then
//   "Add to Home Screen", and the manifest and apple-mobile-web-app tags make that launch open without browser bars.
//
// Nothing runs inside an iframe (an arcade embed) or once the game is installed. The service worker registers only
// over https, so a local `tessaract dev` never caches.
import { toast } from "./dom.js";

const ua = navigator.userAgent;
const iOS = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
const mobile = iOS || /Android/.test(ua);
const framed = window.self !== window.top;

/** True once the game runs as an installed app (its own window, no browser bars). */
export const standalone = () =>
  matchMedia("(display-mode: fullscreen)").matches || matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

if ("serviceWorker" in navigator && location.protocol === "https:") {
  const register = () => { navigator.serviceWorker.register("./sw.js").catch(() => { /* no sw.js, or private mode */ }); };
  if (document.readyState === "complete") register(); else addEventListener("load", register);
}

let deferred = null;
const listeners = new Set();
const changed = () => { for (const fn of listeners) fn(); };
addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; changed(); });
addEventListener("appinstalled", () => { deferred = null; changed(); });

/** What the menu can offer: "prompt" (the browser's install dialog), "ios" (Add to Home Screen steps) or null. */
export function installOffer() {
  if (framed || standalone()) return null;
  if (deferred) return "prompt";
  return iOS ? "ios" : null;
}

/** Calls fn whenever the install offer appears or goes; returns the unsubscribe. */
export function onInstallChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

/** Opens the browser's install dialog, or on iOS says how to add the game to the home screen. */
export async function install() {
  if (deferred) {
    const ev = deferred;
    deferred = null;
    changed();
    try { await ev.prompt(); await ev.userChoice; } catch { /* already used, or the browser declined to show it */ }
    return;
  }
  if (iOS) toast("Tap Share, then “Add to Home Screen” to play full screen");
}

const fullscreen = () => !!(document.fullscreenElement ?? document.webkitFullscreenElement);

function enterFullscreen() {
  const root = document.documentElement;
  try {
    if (root.requestFullscreen) root.requestFullscreen({ navigationUI: "hide" }).catch(() => { /* not allowed here */ });
    else root.webkitRequestFullscreen?.(); // iPadOS before 16.4
  } catch { /* iPhone Safari: no page full screen */ }
}

if (!framed && !standalone()) {
  addEventListener("pointerup", (e) => {
    if (standalone()) return;
    // the install entry runs its own dialog on this tap: leave the activation to it
    if (e.target instanceof Element && e.target.closest("[data-install]")) return;
    if (mobile && deferred) { void install(); return; }
    if (!fullscreen()) enterFullscreen();
  }, { passive: true, capture: true });
}
