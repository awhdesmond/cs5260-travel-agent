import { Outlet } from "react-router-dom";

import Header from '../components/Header';

export default function Layout() {

  return (
    <main className="flex flex-col relative min-h-screen">
      <Header />
      <div className="flex-1">
        <Outlet />
      </div>
      <footer className="w-full text-center py-4 mt-auto text-stone-400 text-sm">
        NUS CS5260 2026 Agentic Application
      </footer>
    </main>
  )
}