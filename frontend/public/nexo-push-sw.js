self.addEventListener('install', (event) => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = {}
  }
  const title = data.title || 'NEXO — New ride request'
  const body = data.message || 'Open NEXO to view and respond.'
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      data: {
        url: data.url || '/driver',
        type: data.type || 'marketplace_request_created',
        ride_id: data.ride_id,
      },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl =
    (event.notification.data && event.notification.data.url) || '/driver'
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (String(client.url).includes('/driver') && 'focus' in client) {
            return client.focus()
          }
        }
        for (const client of clientList) {
          if ('focus' in client) {
            return client.focus()
          }
        }
        if (self.clients.openWindow) {
          return self.clients.openWindow(targetUrl)
        }
        return undefined
      }),
  )
})
