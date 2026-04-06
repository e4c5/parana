import { useChat } from './useChat';
import { useSession } from './useSession';
import { ChatPanel } from './components/ChatPanel';
import './index.css';

function App() {
  const sessionId = useSession();
  const { messages, isStreaming, sendMessage } = useChat(sessionId);

  return (
    <div className="app-root">
      <header className="app-header">
        <h1 className="app-title">Parana — Coverage Chat</h1>
      </header>
      <main className="app-main">
        <ChatPanel messages={messages} isStreaming={isStreaming} onSend={sendMessage} />
      </main>
    </div>
  );
}

export default App;
