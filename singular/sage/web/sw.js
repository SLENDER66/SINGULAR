// Le service worker existe pour une seule raison : sans lui, iOS ne considère
// pas la page comme installable. Il ne met rien en cache.
//
// C'est délibéré. Un journal servi depuis un cache montrerait les chiffres
// d'hier avec l'assurance de ceux d'aujourd'hui, et « 0 décision à trancher »
// serait faux au moment précis où ça compte. Une app hors ligne qui ment est
// pire qu'une app qui dit qu'elle n'a pas de réseau.
self.addEventListener("install", (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
