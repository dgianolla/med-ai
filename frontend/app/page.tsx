import { SessionBoard } from "@/components/SessionBoard";
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="Atend Já" className="h-8 w-auto object-contain" />
            <div>
              <p className="font-semibold text-gray-900 text-sm leading-none">Atend Já</p>
            </div>
          </div>
          
          <nav className="flex gap-4 pt-1 flex-1 px-8">
            <Link href="/" className="text-sm font-medium text-green-600 border-b-2 border-green-600 py-4">Atendimentos</Link>
            <Link href="/confirmacoes" className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors py-4">Confirmações</Link>
          </nav>

          <span className="flex items-center gap-1.5 text-xs text-green-600 font-medium">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            LIA ativa
          </span>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <SessionBoard />
      </div>
    </main>
  );
}
