# CS5260 Travel Planner — Frontend

Welcome to the CS5260 Travel Planner dashboard. This modern, AI-powered travel application is built with **React**, **Vite**, **TypeScript**, and **Tailwind CSS**. It is optimized to run efficiently using **Bun**.

## 🚀 Getting Started with Bun

Bun is a fast all-in-one JavaScript runtime and package manager. Follow these steps to set up the project locally:

### 1. Prerequisites
Ensure you have Bun installed. If not, run:
```bash
curl -fsSL https://bun.sh/install | bash
```

### 2. Install Dependencies
Navigate to the `frontend` directory and install the necessary packages:
```bash
bun install
```

### 3. Environment Setup
Create a `.env` file in the `frontend` directory if you need to override the backend API URL:
```bash
VITE_API_URL=http://localhost:8000
```

### 4. Run Development Server
Start the development server with Hot Module Replacement (HMR):
```bash
bun run dev
```
The application should now be accessible at `http://localhost:5173`.

### 5. Build for Production
To create an optimized production build:
```bash
bun run build
```

---

## 🛠 Features

- **Agentic Planning**: Integrated with the CS5260 backend to provide real-time itinerary generation.
- **2-Pass Selection**: Supports interactive options for flights, hotels, and activities before finalization.
- **Streaming UI**: Watch the AI agents' reasoning process as it happens via SSE (Server-Sent Events).
- **Responsive Dashboard**: A premium, minimalist interface built for high-end travel planning.
- **Itinerary History**: Review and manage your past journeys at a glance.

## 📁 Project Structure

- `src/apis/`: Standardized modules for backend communication.
- `src/pages/`: Main application views (Home, Trip details).
- `src/components/`: Reusable UI elements.
- `src/context/`: State management (User authentication).

## 🧪 Linting
To keep the code clean and follow best practices:
```bash
bun run lint
```
