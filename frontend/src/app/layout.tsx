import type { Metadata } from 'next';
import './globals.css';
import Navigation from '@/components/Navigation';
import QueryProvider from '@/components/QueryProvider';

export const metadata: Metadata = {
  title: 'TRL Rugby — Análisis y Predicción',
  description: 'Estadísticas, predicciones y simulaciones del Torneo Regional del Litoral de Rugby',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark">
      <body>
        <QueryProvider>
          <div className="min-h-screen flex flex-col">
            <Navigation />
            <main className="flex-1 container mx-auto px-4 py-6 max-w-7xl">
              {children}
            </main>
            <footer className="border-t border-gray-800 py-4 text-center text-sm text-gray-500">
              TRL Rugby Analytics · Datos actualizados automáticamente
            </footer>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
