import { ExpirationPlugin } from 'workbox-expiration';
import { precacheAndRoute } from 'workbox-precaching';
import { offlineFallback } from 'workbox-recipes';
import { setDefaultHandler, registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, NetworkOnly } from 'workbox-strategies';
import {CacheableResponsePlugin} from 'workbox-cacheable-response';
// import { warmStrategyCache } from 'workbox-recipes';

//precache
precacheAndRoute(self.__WB_MANIFEST);

// Offline Page
setDefaultHandler(
    new NetworkOnly()
);

offlineFallback({
    pageFallback: '/static/offline.html',
    imageFallback: '/static/images/logo_OL-lg.png'
});

function matchFunction({ url }) {
    const pages = ['/', '/account/login', '/account', '/account/books', '/account/loans', '/account/books/already-read/stats'];
    return pages.includes(url.pathname);
}

// runtime caching as the user visits the page
registerRoute(
    matchFunction,
    new NetworkFirst({
        cacheName: 'html-cache',
        plugins: [
            new ExpirationPlugin({
                // Keep at most 50 entries.
                maxEntries: 50,
                // Don't keep any entries for more than 30 days.
                maxAgeSeconds: 30 * 24 * 60 * 60,
                // Automatically cleanup if quota is exceeded.
                purgeOnQuotaError: true,
            }),
            // only cache if it the request returns 0 or 200 status
            new CacheableResponsePlugin({
                statuses: [0, 200],
            }),
        ],
    })
);

//Warm Runtime Cache (not working properly) (Can't use Regex)
// const strategy = new CacheFirst();
// const urls = [
//   '/account/login',
// ];

// warmStrategyCache({urls, strategy});

// covers png cache
registerRoute(
    new RegExp('http://covers.openlibrary.org/b/.+'),
    new NetworkFirst({
        cacheName: 'covers-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 15,
            }),
            new CacheableResponsePlugin({
                statuses: [0, 200],
            })
        ],
    })
);

// works page covers, images from archive.org cache
registerRoute(
    new RegExp('https://archive.org/.+'),
    new NetworkFirst({
        cacheName: 'archive-cache'
    })
);

// assets cache
registerRoute(
    /\.(?:js|css|woff)/,
    new NetworkFirst({
        cacheName: 'assets-cache',
    })
);

// images cache (precache)
registerRoute(
    /\.(?:png|jpg|jpeg|svg|gif)/,
    new CacheFirst({
        cacheName: 'image-cache',
        plugins: [
            new ExpirationPlugin({
                maxAgeSeconds: 7 * 24 * 60 * 60,
            })
        ],
    })
);

// others page html cache
registerRoute(
    new RegExp('/.+'),
    new NetworkFirst({
        cacheName: 'other-html-cache',
        plugins: [
            new ExpirationPlugin({
                // Due to redirect keep the value 2 times.
                maxEntries: 10,
                // Don't keep any entries for more than 30 days.
                maxAgeSeconds: 30 * 24 * 60 * 60,
                // Automatically cleanup if quota is exceeded.
                purgeOnQuotaError: true,
            }),
            new CacheableResponsePlugin({
                statuses: [0, 200],
            }),
        ],
    })
);
