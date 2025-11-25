# Personal AI Assistant - Frontend

Modern Next.js 16 frontend with Tailwind CSS, TypeScript, and React 18.

## Setup

### Development

1. Install dependencies:
```bash
npm install
```

2. Create `.env.local` file (or copy from `.env.example`):
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

3. Run development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

### Production Build

1. Build the application:
```bash
npm run build
```

2. Start production server:
```bash
npm start
```

Or build manually:
```bash
npm run build
npm start
```

## Features

- **Modern React/Next.js Architecture**: App Router, Server Components, TypeScript
- **Tailwind CSS**: Utility-first styling with custom theme
- **Lucide React Icons**: Beautiful, consistent iconography
- **TypeScript**: Full type safety
- **Chat Interface**: Real-time messaging with conversation management
- **Settings Panel**: AI parameters, character cards, user profiles
- **Model Browser**: Search and download models from HuggingFace
- **Debug Panel**: System monitoring and diagnostics
- **Conversation Management**: Multiple conversation tabs with persistence
- **Error Boundaries**: Graceful error handling
- **API Client**: Retry logic, timeout handling, error recovery

## API Integration

The frontend communicates with the FastAPI backend running on `http://localhost:8000` (configurable via `NEXT_PUBLIC_API_URL`).

### API Client

Located in `lib/api.ts`, the API client provides:
- Automatic retry on failures
- Request timeout handling (30s)
- Error message formatting
- Type-safe request/response handling

### Environment Variables

- `NEXT_PUBLIC_API_URL`: Backend API URL (default: `http://localhost:8000`)

## Development

### Scripts

- `npm run dev`: Start development server
- `npm run build`: Build for production
- `npm run start`: Start production server
- `npm run lint`: Run ESLint
- `npm run type-check`: Run TypeScript type checking
- `npm run build:validate`: Type check + build validation

### Project Structure

```
frontend-next/
├── app/                 # Next.js app directory
│   ├── layout.tsx      # Root layout
│   ├── page.tsx        # Home page
│   └── globals.css    # Global styles
├── components/         # React components
│   ├── ChatPanel.tsx
│   ├── ConversationTabs.tsx
│   ├── SettingsPanel.tsx
│   ├── ModelBrowser.tsx
│   ├── DebugPanel.tsx
│   └── ErrorBoundary.tsx
├── lib/                # Utilities
│   └── api.ts         # API client
└── package.json        # Dependencies
```

## Troubleshooting

### Build Errors

1. Run type check: `npm run type-check`
2. Check for missing dependencies: `npm install`
3. Clear Next.js cache: `rm -rf .next` (Linux/Mac) or `rmdir /s .next` (Windows)

### API Connection Issues

1. Verify backend is running on port 8000
2. Check `NEXT_PUBLIC_API_URL` in `.env.local`
3. Verify CORS is configured in backend
4. Check browser console for errors

