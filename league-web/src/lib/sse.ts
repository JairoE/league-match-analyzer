export type SseEvent = {
  event: string;
  data: string;
};

function parseEventBlock(block: string): SseEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (dataLines.length === 0) return null;
  return {event, data: dataLines.join("\n")};
}

/**
 * Parse a text/event-stream body into SSE events. Used instead of
 * EventSource because the chat endpoint is a POST (the transcript
 * travels in the request body).
 */
export async function* parseSseStream(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const block = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const parsed = parseEventBlock(block);
        if (parsed) yield parsed;
        separatorIndex = buffer.indexOf("\n\n");
      }
    }
    const trailing = parseEventBlock(buffer);
    if (trailing) yield trailing;
  } finally {
    reader.releaseLock();
  }
}
