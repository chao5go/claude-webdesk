// Shared by the server and browser so reconnects and live views agree.
export function applyClaudeEvent(item, event) {
  if (event.session_id) item.threadId = event.session_id;
  if (event.parent_tool_use_id) return;
  const append = (text) => {
    const room = 2_000_000 - item.output.length;
    if (text.length > room) item.truncated = true;
    item.output += text.slice(0, Math.max(0, room));
  };
  if (event.type === 'stream_event') {
    const chunk = event.event;
    if (chunk?.type === 'message_start') item._streamed = false;
    if (chunk?.type === 'content_block_delta' && chunk.delta?.type === 'text_delta') {
      append(chunk.delta.text || '');
      item._streamed = true;
    }
  }
  if (event.type === 'assistant') {
    const text = (event.message?.content || []).filter(b => b.type === 'text').map(b => b.text).join('\n\n');
    if (!item._streamed && text) append(text);
    if (text || item._streamed) append('\n\n');
    item._streamed = false;
  }
  if (event.type === 'result') {
    if (!item.output && typeof event.result === 'string') append(event.result);
    item.costUsd = event.total_cost_usd ?? null;
    item.usage = event.usage || {};
    item.durationMs = event.duration_ms;
    item.turns = event.num_turns;
    item.permissionDenials = event.permission_denials || [];
    if (event.is_error) item.error = (event.errors || []).join('\n') || event.result || event.subtype || 'Claude execution failed';
  }
}
