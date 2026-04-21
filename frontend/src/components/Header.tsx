import React from 'react';
import { useUser } from '../context/user-context';

function Header() {
  const { user } = useUser();

  return (
    <header className="w-full bg-white px-6 py-4 flex flex-col gap-4 sticky top-0 z-50 shadow-sm border-b border-stone-100">
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-6">
          <a href="/" className="flex items-center gap-2 group transition-opacity hover:opacity-80 no-underline">
            <h1 className="font-headline font-bold text-lg text-primary tracking-tight">CS5260 Travel Planner</h1>
          </a>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex flex-col items-end hidden sm:flex">
            <span className="text-[10px] font-bold text-stone-400 uppercase tracking-tighter">User</span>
            <span className="text-xs font-semibold text-stone-700">{user?.email || 'Logged Out'}</span>
          </div>
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs ring-1 ring-primary/20 shrink-0">
            {user?.email?.charAt(0).toUpperCase() || 'L'}
          </div>
        </div>
      </div>
    </header>
  );
}

export default Header;