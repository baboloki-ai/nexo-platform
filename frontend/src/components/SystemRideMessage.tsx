import type { RideSystemMessage } from '../types/ride'
import { formatWhen } from '../utils/format'

export function SystemRideMessage({
  messages,
}: {
  messages: RideSystemMessage[] | undefined
}) {
  if (!messages?.length) return null
  return (
    <div className="stack">
      {messages.map((message, index) => (
        <article key={`${message.body}-${index}`} className="system-message">
          <p className="eyebrow">{message.label ?? 'NEXO system message'}</p>
          <p className="system-message-body">{message.body}</p>
          <p className="muted">
            Automatically generated. The driver did not type this.
            {message.created_at ? ` · ${formatWhen(message.created_at)}` : ''}
          </p>
        </article>
      ))}
    </div>
  )
}
