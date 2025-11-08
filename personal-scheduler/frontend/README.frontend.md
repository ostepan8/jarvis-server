# Personal Scheduler Frontend

A modern React TypeScript frontend for the Personal Scheduler application.

## Features

- **Calendar View**: Monthly calendar with event visualization
- **Event Management**: Create, edit, and delete events
- **Dashboard**: Quick overview of upcoming events and statistics  
- **Responsive Design**: Works on desktop and mobile devices
- **Real-time Updates**: Automatic refresh when events change

## Getting Started

### Prerequisites

- Node.js 16+ and npm
- Personal Scheduler API server running on port 8080

### Installation

1. Install dependencies:
```bash
npm install
```

2. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API server URL and key
```

3. Start the development server:
```bash
npm start
```

The application will be available at http://localhost:3000

### Environment Variables

- `REACT_APP_API_URL`: Backend API server URL (default: http://localhost:8080)
- `REACT_APP_API_KEY`: API authentication key (default: changeme)

## Usage

### Calendar Navigation
- Use arrow buttons to navigate between months
- Click on any date to create a new event
- Click on existing events to edit or delete them
- Use the "New Event" button to create events for today

### Event Creation
- Fill in the event title, description, date/time, duration, and category
- Categories include: Personal, Work, Meeting, Task
- Events are automatically saved to the backend API

### Dashboard
- View your next upcoming event
- See today's schedule at a glance  
- Track weekly statistics and trends

## Technology Stack

- **React 18** with TypeScript
- **Tailwind CSS** for styling
- **date-fns** for date manipulation
- **Lucide React** for icons
- **Fetch API** for backend communication

## Available Scripts

- `npm start`: Start development server
- `npm build`: Build for production
- `npm test`: Run tests
- `npm run eject`: Eject from Create React App

## Architecture

```
src/
├── components/          # React components
│   ├── Calendar.tsx    # Main calendar view
│   ├── Dashboard.tsx   # Dashboard widgets
│   └── EventModal.tsx  # Event creation/editing form
├── services/           # API communication
│   └── api.ts         # API client
├── types/             # TypeScript definitions
│   └── index.ts       # Event and API types
└── App.tsx            # Main application component
```

## Integration with Backend

The frontend communicates with the C++ backend API server through:

- **GET /events**: Fetch events (with optional expansion and date filters)
- **POST /events**: Create new events
- **PUT /events/:id**: Update existing events  
- **DELETE /events/:id**: Delete events
- **GET /events/next**: Get next upcoming event
- **GET /stats**: Get event statistics
- **GET /availability/free-slots**: Find available time slots

All API requests include authentication headers as configured in the environment.