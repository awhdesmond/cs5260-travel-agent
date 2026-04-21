import React from 'react';

interface OptionCardProps {
  isSelected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

export default function OptionCard({ isSelected, onClick, children }: OptionCardProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter') onClick(); }}
      className={`p-4 rounded-xl border transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-900 focus-visible:ring-offset-2 ${
        isSelected
          ? 'border-primary bg-stone-900 text-white shadow-md'
          : 'border-stone-200 bg-white hover:border-stone-300 hover:shadow-md hover:-translate-y-0.5'
      }`}
    >
      {children}
    </div>
  );
}
