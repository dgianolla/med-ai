import { SessionBoard } from "@/components/SessionBoard";
import Link from "next/link";

export default function AtendimentosPage() {
  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="Atend Já" className="h-8 w-auto object-contain" />
            <div>
              <p className="font-semibold text-gray-900 dark:text-gray-100 text-sm leading-none">Atend Já</p>
            </div>
          </div>

          <nav className="flex gap-4 pt-1 flex-1 px-8">
            <Link href="/atendimentos" className="text-sm font-medium text-green-600 dark:text-green-500 border-b-2 border-green-600 dark:border-green-500 py-4">Atendimentos</Link>
            <Link href="/leads" className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors py-4">Leads</Link>
            <Link href="/leads/encaixe" className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors py-4">Encaixe</Link>
            <Link href="/confirmacoes" className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors py-4">Confirmações</Link>
          </nav>

          <span className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-500 font-medium">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            LIA ativa
          </span>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <SessionBoard />
      </div>
    </main>
  );
}
