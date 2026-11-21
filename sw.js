// Guarda a "casca" do aplicativo (ecrã de abertura e ícones) no telemóvel.
// Os dados da granja vêm sempre do servidor, por isso não ficam guardados aqui.
const CACHE = "gestav-casca-v2";
const FICHEIROS = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png",
                   "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FICHEIROS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  // Primeiro tenta a rede (para receber actualizações); sem rede, usa a cópia guardada
  e.respondWith(
    fetch(e.request)
      .then((r) => { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copia)); return r; })
      .catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
  );
});
