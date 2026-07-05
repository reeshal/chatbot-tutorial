export function EmptyState() {
  return (
    <div className="empty">
      <div className="empty__icon" aria-hidden="true">◆</div>
      <h2 className="empty__title">Comment puis-je vous aider ?</h2>
      <p className="empty__hint">Posez une question pour démarrer la conversation.</p>
    </div>
  );
}
