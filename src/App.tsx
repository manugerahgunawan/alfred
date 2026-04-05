/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Home, 
  MessageSquare, 
  Users, 
  Bell, 
  Plus, 
  Send, 
  ChevronRight, 
  Briefcase, 
  Heart,
  Clock,
  AlertCircle
} from 'lucide-react';

// --- Types ---

type Tab = 'home' | 'chat' | 'family' | 'alerts';

interface Task {
  id: string;
  title: string;
  time: string;
  domain: 'work' | 'family';
}

interface FamilyMember {
  id: string;
  name: string;
  role: 'Parent' | 'Child' | 'Helper' | 'Spouse';
  upcomingNeed: string;
}

interface Message {
  id: string;
  sender: 'user' | 'alfred';
  text: string;
  timestamp: Date;
}

// --- Mock Data ---

const INITIAL_TASKS: Task[] = [
  { id: '1', title: 'Review Q3 Strategy', time: '10:00 AM', domain: 'work' },
  { id: '2', title: 'Board Meeting Prep', time: '2:30 PM', domain: 'work' },
  { id: '3', title: 'School Pick-up', time: '3:30 PM', domain: 'family' },
  { id: '4', title: 'Grocery Run', time: '5:00 PM', domain: 'family' },
];

const INITIAL_FAMILY: FamilyMember[] = [
  { id: '1', name: 'Eleanor', role: 'Spouse', upcomingNeed: 'Anniversary dinner prep' },
  { id: '2', name: 'Arthur', role: 'Child', upcomingNeed: 'Piano lesson at 4pm' },
  { id: '3', name: 'Maria', role: 'Helper', upcomingNeed: 'Grocery list update' },
  { id: '4', name: 'Grandma', role: 'Parent', upcomingNeed: 'Clinic visit Thursday' },
];

const INITIAL_MESSAGES: Message[] = [
  { id: '1', sender: 'user', text: "Dad's physio clashes with my presentation Thursday.", timestamp: new Date() },
  { id: '2', sender: 'alfred', text: "I've moved Dad's physio to Friday 9am and notified the helper. Anything else?", timestamp: new Date() },
];

// --- Components ---

const AlfredMonogram = () => (
  <div className="w-8 h-8 rounded-full bg-amber flex items-center justify-center text-white font-serif font-bold text-sm shadow-sm">
    A
  </div>
);

const SectionHeader = ({ title }: { title: string }) => (
  <h2 className="text-lg font-serif font-semibold text-charcoal mb-3">{title}</h2>
);

const TaskCard = ({ task }: { task: Task; key?: string }) => (
  <motion.div 
    whileTap={{ scale: 0.98 }}
    className="bg-white p-4 rounded-2xl shadow-sm mb-3 flex items-center justify-between border border-transparent active:border-amber/20 transition-colors"
  >
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-xl ${task.domain === 'work' ? 'bg-navy/5 text-navy' : 'bg-amber/5 text-amber'}`}>
        {task.domain === 'work' ? <Briefcase size={18} /> : <Heart size={18} />}
      </div>
      <div>
        <h3 className="font-medium text-charcoal text-sm">{task.title}</h3>
        <div className="flex items-center gap-1 text-xs text-charcoal/50 mt-0.5">
          <Clock size={12} />
          <span>{task.time}</span>
        </div>
      </div>
    </div>
    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded-full ${task.domain === 'work' ? 'bg-navy/10 text-navy' : 'bg-amber/10 text-amber'}`}>
      {task.domain}
    </span>
  </motion.div>
);

// --- Screens ---

const HomeScreen = () => (
  <div className="p-6 pb-24">
    <header className="mb-8">
      <h1 className="text-2xl font-serif font-bold text-charcoal leading-tight">
        Good morning.<br />
        <span className="text-amber">Here's what needs your attention.</span>
      </h1>
    </header>

    <div className="mb-8">
      <SectionHeader title="Work" />
      {INITIAL_TASKS.filter(t => t.domain === 'work').map(task => (
        <TaskCard key={task.id} task={task} />
      ))}
    </div>

    <div>
      <SectionHeader title="Family" />
      {INITIAL_TASKS.filter(t => t.domain === 'family').map(task => (
        <TaskCard key={task.id} task={task} />
      ))}
    </div>

    <div className="fixed bottom-24 left-6 right-6">
      <div className="bg-white/80 backdrop-blur-md border border-amber/10 rounded-full px-5 py-3 shadow-lg flex items-center gap-3">
        <AlfredMonogram />
        <input 
          type="text" 
          placeholder="Tell Alfred..." 
          className="flex-1 bg-transparent border-none outline-none text-sm text-charcoal placeholder:text-charcoal/30"
        />
        <Send size={18} className="text-amber" />
      </div>
    </div>
  </div>
);

const ChatScreen = () => {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleSend = () => {
    if (!inputValue.trim()) return;

    const newUserMsg: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, newUserMsg]);
    setInputValue('');
    setIsTyping(true);

    // Simulate Alfred's response
    setTimeout(() => {
      const alfredMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'alfred',
        text: "I've noted that down. I'll make sure everything is coordinated perfectly.",
        timestamp: new Date()
      };
      setMessages(prev => [...prev, alfredMsg]);
      setIsTyping(false);
    }, 1500);
  };

  return (
    <div className="flex flex-col h-full bg-cream">
      <header className="p-6 border-b border-amber/10 bg-white/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <AlfredMonogram />
          <div>
            <h2 className="font-serif font-bold text-charcoal">Alfred</h2>
            <p className="text-[10px] text-amber uppercase tracking-widest font-bold">Always at your service</p>
          </div>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6 pb-32">
        {messages.map(msg => (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            key={msg.id} 
            className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-[80%] flex gap-3 ${msg.sender === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              {msg.sender === 'alfred' && <AlfredMonogram />}
              <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${
                msg.sender === 'user' 
                  ? 'bg-navy text-white rounded-tr-none' 
                  : 'bg-white text-charcoal rounded-tl-none'
              }`}>
                {msg.text}
              </div>
            </div>
          </motion.div>
        ))}
        {isTyping && (
          <div className="flex justify-start gap-3">
            <AlfredMonogram />
            <div className="bg-white p-4 rounded-2xl rounded-tl-none shadow-sm flex gap-1">
              <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1 }} className="w-1.5 h-1.5 bg-amber rounded-full" />
              <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1, delay: 0.2 }} className="w-1.5 h-1.5 bg-amber rounded-full" />
              <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1, delay: 0.4 }} className="w-1.5 h-1.5 bg-amber rounded-full" />
            </div>
          </div>
        )}
      </div>

      <div className="fixed bottom-24 left-6 right-6">
        <div className="bg-white border border-amber/10 rounded-2xl p-2 shadow-lg flex items-center gap-2 focus-within:ring-1 ring-amber/20 transition-all">
          <input 
            type="text" 
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type a message..." 
            className="flex-1 bg-transparent border-none outline-none px-3 py-2 text-sm text-charcoal placeholder:text-charcoal/30"
          />
          <motion.button 
            whileTap={{ scale: 0.9 }}
            onClick={handleSend}
            className="bg-amber text-white p-2 rounded-xl shadow-sm"
          >
            <Send size={18} />
          </motion.button>
        </div>
      </div>
    </div>
  );
};

const FamilyScreen = () => (
  <div className="p-6 pb-24">
    <header className="mb-8 flex justify-between items-end">
      <div>
        <h1 className="text-2xl font-serif font-bold text-charcoal">Household</h1>
        <p className="text-sm text-charcoal/50">Managing 4 members</p>
      </div>
      <motion.button 
        whileTap={{ scale: 0.9 }}
        className="bg-amber text-white p-2 rounded-full shadow-md"
      >
        <Plus size={24} />
      </motion.button>
    </header>

    <div className="grid gap-4">
      {INITIAL_FAMILY.map(member => (
        <motion.div 
          key={member.id}
          whileTap={{ scale: 0.98 }}
          className="bg-white p-5 rounded-2xl shadow-sm border border-transparent hover:border-amber/10 transition-all"
        >
          <div className="flex justify-between items-start mb-3">
            <div>
              <h3 className="font-serif font-bold text-charcoal text-lg">{member.name}</h3>
              <span className="text-[10px] uppercase tracking-widest font-bold text-amber bg-amber/5 px-2 py-0.5 rounded-full">
                {member.role}
              </span>
            </div>
            <div className="w-10 h-10 rounded-full bg-cream flex items-center justify-center text-amber">
              <Users size={20} />
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-charcoal/60 bg-cream/50 p-3 rounded-xl">
            <AlertCircle size={14} className="text-amber" />
            <span>Next: {member.upcomingNeed}</span>
          </div>
        </motion.div>
      ))}
    </div>
  </div>
);

const AlertsScreen = () => (
  <div className="p-6 pb-24">
    <header className="mb-8">
      <h1 className="text-2xl font-serif font-bold text-charcoal">Alerts</h1>
      <p className="text-sm text-charcoal/50">Alfred's proactive updates</p>
    </header>

    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="bg-amber/10 border border-amber/20 p-6 rounded-2xl mb-8"
    >
      <div className="flex gap-4 mb-4">
        <div className="bg-amber text-white p-2 rounded-xl h-fit">
          <AlertCircle size={20} />
        </div>
        <div>
          <h3 className="font-serif font-bold text-charcoal leading-tight mb-1">Schedule Conflict</h3>
          <p className="text-sm text-charcoal/80 leading-relaxed">
            Your board meeting clashes with Grandma's clinic on Thursday. Resolve now?
          </p>
        </div>
      </div>
      <div className="flex gap-3">
        <motion.button 
          whileTap={{ scale: 0.95 }}
          className="flex-1 bg-amber text-white py-2.5 rounded-xl text-sm font-bold shadow-sm"
        >
          Resolve
        </motion.button>
        <motion.button 
          whileTap={{ scale: 0.95 }}
          className="flex-1 bg-white text-charcoal py-2.5 rounded-xl text-sm font-bold border border-amber/20"
        >
          Later
        </motion.button>
      </div>
    </motion.div>

    <SectionHeader title="Recent Actions" />
    <div className="space-y-4">
      {[
        { action: "Moved Physio Appointment", time: "2h ago", target: "Grandma" },
        { action: "Updated Grocery List", time: "4h ago", target: "Maria" },
        { action: "Confirmed School Run", time: "Yesterday", target: "Arthur" },
      ].map((log, i) => (
        <div key={i} className="flex items-center justify-between p-4 bg-white rounded-2xl shadow-sm border border-transparent">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-amber/30" />
            <div>
              <p className="text-sm font-medium text-charcoal">{log.action}</p>
              <p className="text-[10px] text-charcoal/40 uppercase tracking-wider font-bold">{log.target}</p>
            </div>
          </div>
          <span className="text-xs text-charcoal/30 italic">{log.time}</span>
        </div>
      ))}
    </div>
  </div>
);

// --- Main App ---

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');

  const renderScreen = () => {
    switch (activeTab) {
      case 'home': return <HomeScreen />;
      case 'chat': return <ChatScreen />;
      case 'family': return <FamilyScreen />;
      case 'alerts': return <AlertsScreen />;
      default: return <HomeScreen />;
    }
  };

  return (
    <div className="min-h-screen bg-cream font-sans selection:bg-amber/20 flex justify-center">
      {/* Mobile Container Emulator */}
      <div className="w-full max-w-[390px] bg-cream min-h-screen relative shadow-2xl overflow-hidden flex flex-col">
        
        {/* Content Area */}
        <main className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              {renderScreen()}
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Bottom Navigation */}
        <nav className="fixed bottom-0 w-full max-w-[390px] bg-white/80 backdrop-blur-xl border-t border-amber/10 px-6 py-4 flex justify-between items-center z-50">
          <NavButton 
            active={activeTab === 'home'} 
            onClick={() => setActiveTab('home')} 
            icon={<Home size={22} />} 
            label="Home" 
          />
          <NavButton 
            active={activeTab === 'chat'} 
            onClick={() => setActiveTab('chat')} 
            icon={<MessageSquare size={22} />} 
            label="Alfred" 
          />
          <NavButton 
            active={activeTab === 'family'} 
            onClick={() => setActiveTab('family')} 
            icon={<Users size={22} />} 
            label="Family" 
          />
          <NavButton 
            active={activeTab === 'alerts'} 
            onClick={() => setActiveTab('alerts')} 
            icon={<Bell size={22} />} 
            label="Alerts" 
          />
        </nav>
      </div>
    </div>
  );
}

const NavButton = ({ active, onClick, icon, label }: { active: boolean, onClick: () => void, icon: React.ReactNode, label: string }) => (
  <button 
    onClick={onClick}
    className={`flex flex-col items-center gap-1 transition-all duration-300 ${active ? 'text-amber scale-110' : 'text-charcoal/30'}`}
  >
    {icon}
    <span className={`text-[10px] font-bold uppercase tracking-widest ${active ? 'opacity-100' : 'opacity-0'}`}>
      {label}
    </span>
  </button>
);
