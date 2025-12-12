# Financial Analyst Frontend

Modern React + TypeScript web interface for the Financial Analysis Agents.

## Features

- 🎨 Clean, minimalist design inspired by modern chat applications
- ⚡ Real-time streaming responses using Server-Sent Events
- 📱 Fully responsive design (desktop, tablet, mobile)
- 🎯 Multiple specialized agents (DCF, Equity Analyst, Research Assistant, Market Analyst)
- 📝 Markdown support for formatted responses
- 🔄 Auto-scrolling chat interface
- 💡 Example prompts to get started quickly

## Tech Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first styling
- **Lucide React** - Modern icon library
- **React Markdown** - Markdown rendering
- **Axios** - HTTP client

## Getting Started

### Install Dependencies

```bash
npm install
```

### Start Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:3000`

### Build for Production

```bash
npm run build
```

Production files will be in the `dist/` folder.

### Preview Production Build

```bash
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── AgentSelector.tsx    # Agent switcher dropdown
│   │   ├── Chat.tsx              # Main chat interface
│   │   ├── ChatInput.tsx         # Message input component
│   │   └── Message.tsx           # Individual message display
│   ├── api.ts                    # API client and utilities
│   ├── types.ts                  # TypeScript type definitions
│   ├── App.tsx                   # Main app component
│   ├── main.tsx                  # React entry point
│   └── index.css                 # Global styles + Tailwind
├── index.html                    # HTML entry point
├── vite.config.ts                # Vite configuration
├── tailwind.config.js            # Tailwind CSS configuration
├── tsconfig.json                 # TypeScript configuration
└── package.json                  # Dependencies and scripts
```

## Configuration

### API Endpoint

The frontend proxies API requests to the backend server. Configuration in `vite.config.ts`:

```typescript
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, '')
    }
  }
}
```

For production, set the API URL via environment variable:

```bash
VITE_API_URL=https://your-backend-api.com npm run build
```

### Styling

The app uses Tailwind CSS with a custom color palette defined in `tailwind.config.js`.

Primary colors are based on blue shades for a professional financial look.

## Key Components

### App.tsx
Main application component that:
- Loads available agents from backend
- Manages selected agent state
- Renders header, agent selector, and chat interface

### Chat.tsx
Chat interface that:
- Manages message history
- Handles user input and agent responses
- Implements SSE streaming
- Shows welcome screen with example prompts
- Auto-scrolls to latest message

### Message.tsx
Individual message component that:
- Renders user and assistant messages differently
- Supports markdown formatting for assistant messages
- Shows timestamps and agent info

### ChatInput.tsx
Message input component with:
- Auto-expanding textarea
- Send button with loading state
- Keyboard shortcuts (Enter to send, Shift+Enter for new line)
- Attachment button (placeholder)

### AgentSelector.tsx
Dropdown component for switching agents:
- Shows current agent with icon and name
- Lists all available agents with descriptions
- Smooth transitions and animations

## Streaming Implementation

The chat uses Server-Sent Events (SSE) for streaming responses:

```typescript
// In api.ts
export const streamMessage = async (
  request: ChatRequest,
  onMessage: (event: StreamEvent) => void,
  onError: (error: string) => void
): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    // Parse SSE events and call onMessage callback
  }
};
```

Event types:
- `start` - Agent started processing
- `content` - Partial response chunk
- `end` - Response complete
- `error` - Error occurred

## Customization

### Adding New Agents

1. Backend should expose the agent in `/agents` endpoint
2. Frontend will automatically display it in the agent selector
3. Add agent-specific example prompts in `Chat.tsx`

### Changing Colors

Edit `tailwind.config.js` to customize the color scheme:

```javascript
theme: {
  extend: {
    colors: {
      primary: {
        // Your custom colors
      }
    }
  }
}
```

### Adding New Features

Common enhancements:
- File upload support
- Conversation export (PDF, Markdown)
- Conversation history/sessions
- User authentication
- Dark mode toggle
- Chart/graph rendering for financial data

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Modern mobile browsers

Requires JavaScript enabled and supports:
- ES2020 features
- CSS Grid and Flexbox
- Server-Sent Events (EventSource)

## Performance

The app is optimized for performance:
- Code splitting with React lazy loading (can be added)
- Tailwind CSS purges unused styles in production
- Vite provides fast HMR in development
- React 18 concurrent features for smooth UX

## Accessibility

The interface includes:
- Semantic HTML elements
- ARIA labels where needed
- Keyboard navigation support
- High contrast text for readability
- Focus indicators for interactive elements

## Development Tips

1. **Hot Reload**: Vite provides instant HMR - changes appear immediately
2. **Type Checking**: Run `tsc --noEmit` to check types without building
3. **Linting**: Use `npm run lint` to check code quality
4. **Component Dev**: Test components in isolation before integration
5. **Browser DevTools**: Use React DevTools for component debugging

## Known Issues

1. **Markdown Tables**: Complex tables may overflow on mobile (use horizontal scroll)
2. **Long Messages**: Very long responses may cause scroll performance issues
3. **SSE Reconnection**: Page refresh required if SSE connection drops

## Contributing

When adding features:
1. Follow existing component structure
2. Use TypeScript for type safety
3. Follow Tailwind CSS conventions
4. Test on multiple browsers
5. Ensure responsive design

## License

Same as main project (MIT License)
