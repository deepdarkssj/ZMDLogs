import { useState, useEffect } from 'react';
import { 
  Activity, 
  Maximize, 
  ScrollText, 
  Settings, 
  ChevronDown, 
  LogOut, 
  CheckCircle, 
  AlertTriangle, 
  Info,
  X,
  Minus,
  Square,
  Download
} from 'lucide-react';
import { motion } from 'motion/react';

export default function App() {
  const [isCombatLogOpen, setIsCombatLogOpen] = useState(true);

  return (
    <div className="min-h-screen bg-[#f0f0f0] flex items-center justify-center p-4 font-sans selection:bg-primary-container selection:text-on-primary-container">
      {/* Desktop Window Frame */}
      <div className="relative w-full max-w-6xl h-[85vh] bg-white border-[3px] border-[#323123] shadow-2xl flex flex-col overflow-hidden">
        
        {/* Custom Title Bar */}
        <div className="h-8 bg-[#323123] flex items-center justify-between px-3 flex-shrink-0 select-none">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-[#feef00] rounded-none" />
            <span className="text-[10px] font-mono font-bold text-white uppercase tracking-widest">ZMD_LOGS_v1.0.4_STABLE</span>
          </div>
          <div className="flex items-center gap-4">
            <Minus className="w-3 h-3 text-white/50 cursor-pointer hover:text-white" />
            <Square className="w-2.5 h-2.5 text-white/50 cursor-pointer hover:text-white" />
            <X className="w-3 h-3 text-white/50 cursor-pointer hover:text-[#ba1a1a]" />
          </div>
        </div>

        <div className="flex-grow flex overflow-hidden">
          {/* Sidebar Navigation */}
          <aside className="w-64 flex-shrink-0 bg-[#f7f7f7] border-r-[3px] border-[#323123] flex flex-col">
            {/* Logo Section */}
            <div className="p-4 border-b border-black/10">
              <div className="flex items-center justify-center p-2">
                <img 
                  alt="ZMD LOGS" 
                  className="h-12 w-auto object-contain" 
                  src="/logo.png"
                  onError={(e) => {
                    e.currentTarget.src = 'https://via.placeholder.com/180x60?text=ZMD+LOGS';
                  }}
                />
              </div>
            </div>

            {/* Navigation Links */}
            <nav className="flex-grow p-4 flex flex-col gap-1">
              <a className="flex items-center gap-3 px-3 py-2 bg-[#feef00] border border-[#323123] group" href="#">
                <Activity className="w-4 h-4" />
                <span className="font-bold text-xs uppercase tracking-tight">Status</span>
              </a>
              <a className="flex items-center gap-3 px-3 py-2 hover:bg-black/5 transition-colors group" href="#">
                <Maximize className="w-4 h-4 text-[#5e5e5e]" />
                <span className="font-bold text-xs uppercase tracking-tight text-[#5e5e5e]">Floating Window Settings</span>
              </a>
              
              {/* Collapsible Menu Item */}
              <div className="group">
                <button 
                  onClick={() => setIsCombatLogOpen(!isCombatLogOpen)}
                  className="w-full flex items-center justify-between px-3 py-2 hover:bg-black/5 cursor-pointer transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <ScrollText className="w-4 h-4 text-[#5e5e5e]" />
                    <span className="font-bold text-xs uppercase tracking-tight text-[#5e5e5e]">Combat Log List</span>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-[#5e5e5e] transition-transform ${isCombatLogOpen ? 'rotate-180' : ''}`} />
                </button>
                {isCombatLogOpen && (
                  <div className="pl-9 pr-3 py-1 flex flex-col gap-1">
                    {['LOG_20231024_01', 'LOG_20231024_02', 'LOG_20231023_04'].map((log) => (
                      <a key={log} className="text-[10px] font-mono font-medium text-[#5e5e5e] hover:text-black py-1 border-b border-transparent hover:border-[#feef00]" href="#">
                        {log}
                      </a>
                    ))}
                  </div>
                )}
              </div>

              <a className="flex items-center gap-3 px-3 py-2 hover:bg-black/5 transition-colors group" href="#">
                <Settings className="w-4 h-4 text-[#5e5e5e]" />
                <span className="font-bold text-xs uppercase tracking-tight text-[#5e5e5e]">Settings</span>
              </a>
            </nav>

            {/* Bottom Exit/User */}
            <div className="p-4 border-t border-black/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 bg-black/10 border border-black/20" />
                <span className="text-[10px] font-mono font-bold uppercase">SQUAD_01</span>
              </div>
              <LogOut className="w-4 h-4 text-[#5e5e5e] cursor-pointer hover:text-[#ba1a1a]" />
            </div>
          </aside>

          {/* Main Content Area */}
          <main className="flex-grow flex flex-col bg-[#fdfdfd] relative overflow-hidden">
            {/* Header Bar */}
            <header className="flex items-center justify-between px-6 py-4 border-b border-black/5 bg-white">
              <div>
                <h2 className="font-black text-2xl uppercase tracking-tighter">System Status</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className="bg-[#323123] text-[#feef00] px-1.5 py-0.5 text-[8px] font-mono font-bold">LIVE_FEED</span>
                  <span className="text-[8px] font-mono text-[#5e5e5e] font-bold">SECTOR_G_ALPHA</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="px-4 py-2 bg-[#feef00] border border-[#323123] font-bold text-[10px] uppercase shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-y-0.5 active:shadow-none transition-all">
                  Open Log Folder
                </button>
                <button className="px-4 py-2 bg-white border border-[#323123] font-bold text-[10px] uppercase shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-y-0.5 active:shadow-none transition-all">
                  Report Issue
                </button>
              </div>
            </header>

            {/* Content Grid */}
            <div className="p-6 grid grid-cols-12 gap-6 overflow-y-auto flex-grow">
              {/* Game Connection Card */}
              <div className="col-span-7 bg-white border border-[#323123] p-5 shadow-[4px_4px_0px_0px_rgba(0,0,0,0.05)] relative overflow-hidden">
                <div className="absolute top-0 right-0 w-12 h-12 opacity-5 pointer-events-none" style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 8px, #000 8px, #000 10px)' }} />
                <h3 className="font-black text-sm uppercase mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-3 bg-[#feef00]" />
                  Game Connection
                </h3>
                <div className="space-y-3">
                  {[
                    { label: 'Status', value: 'Connected', color: 'text-green-700', icon: <CheckCircle className="w-3 h-3" /> },
                    { label: 'Game', value: 'Combat Protocol X' },
                    { label: 'Player', value: 'factitiously' },
                    { label: 'Server', value: 'Asia_South' }
                  ].map((item) => (
                    <div key={item.label} className="flex justify-between items-center border-b border-dotted border-black/20 pb-1">
                      <span className="font-mono text-[10px] text-[#5e5e5e] font-bold uppercase">{item.label}:</span>
                      <span className={`font-mono text-[10px] font-bold flex items-center gap-1 ${item.color || ''}`}>
                        {item.value} {item.icon}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Log Recording Card */}
              <div className="col-span-5 bg-white border border-[#323123] p-5 shadow-[4px_4px_0px_0px_rgba(0,0,0,0.05)]">
                <h3 className="font-black text-sm uppercase mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-3 bg-[#feef00]" />
                  Log Recording
                </h3>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-[10px] text-[#5e5e5e] font-bold uppercase">Status:</span>
                    <span className="font-mono text-[10px] font-bold uppercase">Active</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-[10px] text-[#5e5e5e] font-bold uppercase">Session Time:</span>
                    <span className="font-mono text-[10px] font-bold">01:45:22</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-[10px] text-[#5e5e5e] font-bold uppercase">Logs Captured:</span>
                    <span className="font-mono text-[10px] font-bold">5,234 events</span>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-black/5">
                  <span className="text-[8px] font-mono text-[#5e5e5e] uppercase block mb-2 font-bold">Events per second</span>
                  <div className="h-12 w-full flex items-end gap-[2px]">
                    {[40, 60, 45, 75, 90, 65, 80, 100].map((h, i) => (
                      <div 
                        key={i} 
                        className={`flex-grow bg-[#feef00] ${i > 4 ? 'opacity-50' : ''}`} 
                        style={{ height: `${h}%` }} 
                      />
                    ))}
                  </div>
                </div>
              </div>

              {/* Performance Monitor */}
              <div className="col-span-8 bg-white border border-[#323123] p-5 shadow-[4px_4px_0px_0px_rgba(0,0,0,0.05)]">
                <h3 className="font-black text-sm uppercase mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-3 bg-[#feef00]" />
                  Performance Monitor
                </h3>
                <div className="flex gap-8 mb-4">
                  <div>
                    <span className="font-mono text-[10px] text-[#5e5e5e] uppercase font-bold">CPU:</span>
                    <span className="font-mono text-lg font-bold ml-2">12%</span>
                  </div>
                  <div>
                    <span className="font-mono text-[10px] text-[#5e5e5e] uppercase font-bold">RAM:</span>
                    <span className="font-mono text-lg font-bold ml-2">350MB</span>
                  </div>
                </div>
                {/* Chart Placeholder */}
                <div className="h-32 w-full bg-black/5 border border-dotted border-black/20 relative overflow-hidden">
                  <svg className="absolute bottom-0 left-0 w-full h-24" preserveAspectRatio="none" viewBox="0 0 100 100">
                    <path 
                      d="M0 100 L0 80 L10 70 L20 85 L30 60 L40 65 L50 40 L60 50 L70 30 L80 35 L90 20 L100 25 L100 100 Z" 
                      fill="rgba(254, 239, 0, 0.3)" 
                      stroke="#feef00" 
                      strokeWidth="1" 
                    />
                  </svg>
                  <div className="absolute inset-0 grid grid-cols-6 grid-rows-4 pointer-events-none opacity-10">
                    {Array.from({ length: 24 }).map((_, i) => (
                      <div key={i} className="border-r border-b border-black" />
                    ))}
                  </div>
                </div>
              </div>

              {/* Recent Alerts */}
              <div className="col-span-4 bg-white border border-[#323123] p-5 shadow-[4px_4px_0px_0px_rgba(0,0,0,0.05)]">
                <h3 className="font-black text-sm uppercase mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-3 bg-[#feef00]" />
                  Recent Alerts
                </h3>
                <div className="flex flex-col gap-3">
                  <div className="flex items-start gap-2 border-l-2 border-[#feef00] pl-2 py-1 bg-[#feef00]/5">
                    <AlertTriangle className="w-3 h-3 text-[#676000] mt-0.5" />
                    <p className="text-[10px] font-mono leading-tight">
                      <span className="font-bold">[!]</span> High CPU usage detected during battle sequence_03
                    </p>
                  </div>
                  <div className="flex items-start gap-2 border-l-2 border-[#feef00] pl-2 py-1 bg-[#feef00]/5">
                    <Info className="w-3 h-3 text-[#676000] mt-0.5" />
                    <p className="text-[10px] font-mono leading-tight">
                      <span className="font-bold">[i]</span> New update v1.4.3 available for download
                    </p>
                  </div>
                  <div className="flex items-start gap-2 border-l-2 border-black/20 pl-2 py-1">
                    <Info className="w-3 h-3 text-[#5e5e5e] mt-0.5" />
                    <p className="text-[10px] font-mono leading-tight text-[#5e5e5e]">
                      <span className="font-bold">[i]</span> Log session 442 closed successfully
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer Strip */}
            <footer className="mt-auto border-t-[3px] border-[#323123] h-10 w-full flex items-center justify-between px-6 relative overflow-hidden" style={{ background: 'repeating-linear-gradient(45deg, #feef00, #feef00 10px, #d4c700 10px, #d4c700 20px)' }}>
              <span className="font-black text-xs text-black uppercase tracking-[0.2em] relative z-10">IN_COMBAT // 战斗中</span>
              <div className="flex items-center gap-4 relative z-10">
                <span className="font-mono text-[9px] font-bold text-black/70 uppercase">v1.0.4_SQUAD_LOG</span>
                <div className="flex gap-1">
                  <div className="w-1.5 h-2 bg-black" />
                  <div className="w-1.5 h-2 bg-black/40" />
                  <div className="w-1.5 h-2 bg-black" />
                </div>
              </div>
            </footer>
          </main>
        </div>

        {/* PySide6 Download Prompt */}
        <div className="absolute top-12 right-6 z-50">
          <motion.div 
            initial={{ x: 100, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            className="bg-[#323123] border border-[#feef00] p-4 shadow-xl flex flex-col gap-3 max-w-xs"
          >
            <div className="flex items-center gap-2">
              <Download className="w-4 h-4 text-[#feef00]" />
              <span className="text-[10px] font-mono font-bold text-white uppercase">Desktop App Ready</span>
            </div>
            <p className="text-[9px] font-mono text-white/70 leading-relaxed">
              The PySide6 version of this dashboard is available in <code className="text-[#feef00]">main.py</code>. 
              Run it locally for a native experience.
            </p>
            <div className="flex flex-col gap-1">
              <span className="text-[8px] font-mono text-[#feef00] uppercase font-bold">Quick Start:</span>
              <code className="text-[8px] font-mono bg-black/30 p-1 text-white/90">pip install PySide6 requests</code>
              <code className="text-[8px] font-mono bg-black/30 p-1 text-white/90">python main.py</code>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
