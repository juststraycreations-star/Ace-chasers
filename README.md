# ⛳ Ace Chasers

A disc golf dating and social app built with React, Tailwind CSS, and modern web technologies. Connect with fellow disc golf players, discover matches, and arrange rounds together.

## Features

- **Discovery**: Swipe through player profiles to find your ace match
- **Messaging**: Chat with players you match with to arrange rounds
- **Profiles**: Create and customize your player profile with skill level, location, and interests
- **Authentication**: User registration and login

## Tech Stack

- **Frontend**: React 18 + React Router DOM
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **HTTP Client**: Axios
- **Build Tool**: Vite (with react-scripts fallback)

## Project Structure

```
src/
├── components/        # Reusable UI components
│   ├── Navigation.jsx
│   └── PlayerCard.jsx
├── pages/            # Page components
│   ├── Discovery.jsx
│   ├── Messages.jsx
│   ├── Profile.jsx
│   ├── Login.jsx
│   └── SignUp.jsx
├── store/            # Zustand state management
│   ├── authStore.js
│   ├── matchStore.js
│   └── messageStore.js
├── App.jsx           # Main app component
├── main.jsx          # Entry point
└── index.css         # Global styles
```

## Getting Started

### Prerequisites

- Node.js 16+ 
- npm or yarn

### Installation

1. Clone the repository:
```bash
git clone https://github.com/juststraycreations-star/Ace-chasers.git
cd Ace-chasers
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```

The app will open at `http://localhost:3000`

## Available Scripts

- `npm start` - Start development server
- `npm build` - Build for production
- `npm test` - Run tests
- `npm eject` - Eject from create-react-app (not reversible)

## Pages

### Discovery Page
Browse and swipe through player profiles. Like or pass on players to build your match list.

### Messages Page
View all conversations and chat with players you've matched with. Real-time messaging support.

### Profile Page
View and edit your player profile including name, age, skill level, location, and bio.

### Authentication
- **Login Page**: Sign in with email and password
- **Sign Up Page**: Create a new account with profile information

## Color Scheme

- **Disc Green**: `#2d5016` - Primary brand color
- **Disc Gold**: `#fbbf24` - Accent color for highlights
- **Disc Purple**: `#9333ea` - Secondary accent

## API Integration

Currently using mock data. To integrate with a backend:

1. Update the API endpoints in each page/component
2. Replace mock data calls with axios requests to your backend
3. Update Zustand stores to handle API responses

## Future Enhancements

- [ ] Location-based player discovery
- [ ] Match notifications
- [ ] Real-time messaging with WebSockets
- [ ] Course information and ratings
- [ ] Tournament/round organization
- [ ] Photo uploads for profiles
- [ ] Player reviews and ratings
- [ ] Advanced filters (age, skill level, location radius)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT

## Support

For issues or questions, please open an issue on GitHub.

---

Happy disc golfing! ⛳
