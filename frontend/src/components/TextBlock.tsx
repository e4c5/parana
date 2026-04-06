interface Props {
  text: string;
  isStreaming?: boolean;
}

export function TextBlock({ text, isStreaming = false }: Props) {
  return (
    <div className="text-block">
      <pre className="text-block-content">{text}</pre>
      {isStreaming && <span className="typing-cursor" aria-hidden="true">▌</span>}
    </div>
  );
}
