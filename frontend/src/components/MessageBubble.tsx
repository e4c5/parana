import type { Message } from '../types';
import { TextBlock } from './TextBlock';
import { DynamicResult } from './DynamicResult';

interface Props {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming = false }: Props) {
  const isUser = message.role === 'user';
  const isActiveStream = isStreaming && message.role === 'assistant' && !message.result;

  return (
    <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
      <div className="bubble-content">
        <TextBlock text={message.text} isStreaming={isActiveStream} />
        {message.result && <DynamicResult result={message.result} />}
      </div>
    </div>
  );
}
