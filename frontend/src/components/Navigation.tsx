'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { BarChart2, Calendar, Film, Target, TrendingUp } from 'lucide-react';

const NAV_ITEMS = [
  { href: '/',            label: 'Dashboard',    icon: BarChart2  },
  { href: '/standings',   label: 'Posiciones',   icon: TrendingUp },
  { href: '/matches',     label: 'Partidos',     icon: Calendar   },
  { href: '/simulator',   label: 'Simulador',    icon: Target     },
  { href: '/analysis',    label: 'Análisis',     icon: Film       },
];

export default function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-40 border-b border-gray-800 bg-gray-950/95 backdrop-blur">
      <div className="container mx-auto px-4 max-w-7xl">
        <div className="flex items-center h-14 gap-8">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <span className="text-rugby-gold font-bold text-lg tracking-tight">TRL</span>
            <span className="text-gray-400 text-sm hidden sm:inline">Rugby Analytics</span>
          </Link>

          {/* Nav links */}
          <div className="flex items-center gap-1">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
                  pathname === href
                    ? 'bg-rugby-green text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                )}
              >
                <Icon size={15} />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}
