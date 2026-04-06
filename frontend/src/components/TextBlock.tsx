interface Props {
  text: string;
  isStreaming?: boolean;
}

export function TextBlock({ text, isStreaming = false }: Props) {
  return (
    <div className="text-block">
      <span className="text-block-content">{text}</span>
      {isStreaming && <span className="typing-cursor" aria-hidden="true">▌</span>}
    </div>
  );
}
