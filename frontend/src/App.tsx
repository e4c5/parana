import { useChat } from './useChat';
import { useSession } from './useSession';
import { useAuth } from './useAuth';
import { ChatPanel } from './components/ChatPanel';
import { AuthForm } from './components/AuthForm';
import './index.css';

function App() {
  const sessionId = useSession();
  const { token, isAuthenticated, login, register, logout, error } = useAuth();
  const { messages, isStreaming, sendMessage } = useChat(sessionId, token);

  if (!isAuthenticated) {
    return (
      <div className="app-root">
        <header className="app-header">
          <h1 className="app-title">Parana — Coverage Chat</h1>
        </header>
        <main className="app-main">
          <AuthForm onLogin={login} onRegister={register} error={error} />
        </main>
      </div>
    );
  }

  return (
    <div className="app-root">
      <header className="app-header">
        <h1 className="app-title">Parana — Coverage Chat</h1>
        <button className="logout-button" onClick={logout}>
          Logout
        </button>
      </header>
      <main className="app-main">
        <ChatPanel
            messages={messages}
            isStreaming={isStreaming}
            onSend={(text) => { sendMessage(text).catch(console.error); }}
          />
      </main>
    </div>
  );
}

export default App;
