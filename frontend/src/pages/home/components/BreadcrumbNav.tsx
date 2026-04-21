import React from 'react';
import { ChevronRight } from 'lucide-react';

interface BreadcrumbNavProps {
  destination: string;
  activeDay: number;
  onBack: () => void;
  onHome: () => void;
}

export default function BreadcrumbNav({ destination, activeDay, onBack, onHome }: BreadcrumbNavProps) {
  return (
    <div className="px-6 py-3 bg-stone-50 border-b border-stone-100 flex items-center gap-2 text-xs">
      <span
        className="text-stone-500 hover:text-stone-700 cursor-pointer"
        onClick={onHome}
      >
        Home
      </span>
      <ChevronRight size={14} className="text-stone-300" />
      <span
        className="text-stone-500 hover:text-stone-700 cursor-pointer"
        onClick={onBack}
      >
        {destination}
      </span>
      <ChevronRight size={14} className="text-stone-300" />
      <span className="text-stone-900 font-semibold">Day {activeDay}</span>
    </div>
  );
}
