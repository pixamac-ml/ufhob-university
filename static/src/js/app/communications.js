(() => {
  const host = document.querySelector('[data-conversation-id]');
  if (!host || !window.WebSocket) return;
  const feed = document.getElementById('conversation-messages');
  const conversationId = host.dataset.conversationId;
  if (!/^\d+$/.test(conversationId)) return;
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  let socket;
  try {
    socket = new WebSocket(`${scheme}//${window.location.host}/ws/messages/${conversationId}/`);
  } catch (_) {
    return; // HTMX polling stays enabled.
  }
  socket.addEventListener('message', (event) => {
    try {
      if (JSON.parse(event.data).type === 'conversation.changed' && feed && window.htmx) {
        window.htmx.trigger(feed, 'refreshMessages');
      }
    } catch (_) { /* Ignore malformed events; the HTTP fallback remains active. */ }
  });
})();
