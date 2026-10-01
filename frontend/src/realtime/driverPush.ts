import { getVapidPublicKey, registerPushSubscription } from '../api/push'

const SW_URL = '/nexo-push-sw.js'

function urlBase64ToUint8Array(base64String: string): BufferSource {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  const output = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i)
  }
  return output
}

function pushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  )
}

export async function registerDriverPush(): Promise<void> {
  if (!pushSupported()) return

  try {
    const { vapid_public_key: vapidPublicKey } = await getVapidPublicKey()
    if (!vapidPublicKey) return

    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return

    const registration = await navigator.serviceWorker.register(SW_URL)
    await navigator.serviceWorker.ready

    let subscription = await registration.pushManager.getSubscription()
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
      })
    }

    const json = subscription.toJSON()
    const endpoint = json.endpoint
    const p256dh = json.keys?.p256dh
    const auth = json.keys?.auth
    if (!endpoint || !p256dh || !auth) return

    await registerPushSubscription({
      endpoint,
      keys: { p256dh, auth },
    })
  } catch {
    // Best-effort. Existing WebSocket and polling continue unchanged.
  }
}
