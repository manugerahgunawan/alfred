/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  LayoutDashboard,
  MessageSquare, 
  Users, 
  User,
  Plus, 
  Send, 
  Briefcase,
  Home,
  CalendarDays,
  MapPin,
  Clock,
  Sparkles,
  PencilLine,
  Bell,
  CheckCircle2,
  Focus,
  LogIn,
  Loader2,
} from 'lucide-react';
import {
  createAlfredSession,
  sendToAlfred,
  startGoogleOAuth,
  parseOAuthFragment,
  fetchUserEmail,
} from './api/alfred';

type Tab = 'dashboard' | 'chat' | 'contacts' | 'profile';
type ContactContext = 'work' | 'home';

interface EventItem {
  id: string;
  title: string;
  day: string;
  time: string;
  context: ContactContext;
  summary: string;
  location?: string;
  relatedContactIds: string[];
}

interface Contact {
  id: string;
  name: string;
  role: string;
  context: ContactContext;
  note?: string;
  gmail?: string;
}

interface AuthState {
  token: string;
  email: string;
  sessionId: string;
  loading: boolean;
  error: string;
}

interface Message {
  id: string;
  sender: 'user' | 'alfred';
  text: string;
  thought?: string;
  timestamp: Date;
}

interface UserProfile {
  name: string;
  role: string;
  onboardingNotes: string;
  defaultContext: ContactContext;
  onboardingDone: boolean;
}

const INITIAL_CONTACTS: Contact[] = [
  { id: 'c1', name: 'Eleanor', role: 'Spouse', context: 'home', note: 'Coordinates dinner plans' },
  { id: 'c2', name: 'Arthur', role: 'Child', context: 'home', note: 'Piano lessons on Tue/Thu' },
  { id: 'c3', name: 'Maria', role: 'House Helper', context: 'home', note: 'Daily errands and groceries' },
  { id: 'c4', name: 'Jonah', role: 'Chief of Staff', context: 'work', note: 'Handles board prep' },
];

const INITIAL_EVENTS: EventItem[] = [
  {
    id: 'e1',
    title: 'Q3 Strategy Review',
    day: 'Mon',
    time: '10:00 AM',
    context: 'work',
    summary: 'Finalize priorities and lock cross-functional owners before Friday.',
    location: 'Wayne Tower - 12F Board Room',
    relatedContactIds: ['c4'],
  },
  {
    id: 'e2',
    title: 'Grandma Clinic Follow-up',
    day: 'Thu',
    time: '11:00 AM',
    context: 'home',
    summary: 'Share last reports with clinic and confirm transport slot with helper.',
    location: 'Gotham General',
    relatedContactIds: ['c3'],
  },
  {
    id: 'e3',
    title: 'Board Meeting Prep',
    day: 'Fri',
    time: '2:30 PM',
    context: 'work',
    summary: 'Rehearse narrative and attach risk appendix for directors.',
    location: 'Virtual',
    relatedContactIds: ['c4'],
  },
  {
    id: 'e4',
    title: 'School Pick-up',
    day: 'Fri',
    time: '3:30 PM',
    context: 'home',
    summary: 'Bring Arthur directly to piano studio after pick-up.',
    location: 'North Gate Campus',
    relatedContactIds: ['c2'],
  },
];

const INITIAL_MESSAGES: Message[] = [
  { id: '1', sender: 'user', text: 'Please prioritize all home reminders for Thursday.', timestamp: new Date() },
  { id: '2', sender: 'alfred', text: 'Done. I flagged home events and drafted reminders for related contacts.', timestamp: new Date() },
];

const AlfredMonogram = () => (
  <div className="w-8 h-8 rounded-full bg-amber flex items-center justify-center text-white font-serif font-bold text-sm shadow-sm">
    A
  </div>
);

const SectionHeader = ({ title, right }: { title: string; right?: React.ReactNode }) => (
  <div className="flex items-center justify-between mb-3">
  <h2 className="text-lg font-serif font-semibold text-charcoal mb-3">{title}</h2>
    {right}
  </div>
);

const classifyContext = (role: string, notes: string): ContactContext => {
  const text = `${role} ${notes}`.toLowerCase();
  const workWords = ['board', 'meeting', 'client', 'deadline', 'project', 'office', 'presentation'];
  const homeWords = ['school', 'family', 'home', 'clinic', 'grocery', 'helper', 'child'];

  const workScore = workWords.filter((w) => text.includes(w)).length;
  const homeScore = homeWords.filter((w) => text.includes(w)).length;

  return workScore > homeScore ? 'work' : 'home';
};

const EventDetails = ({
  event,
  contacts,
  onReschedule,
  onRemind,
  onFocus,
  alfredReply,
  alfredLoading,
}: {
  event: EventItem | null;
  contacts: Contact[];
  onReschedule: (event: EventItem) => void;
  onRemind: (event: EventItem) => void;
  onFocus: (event: EventItem) => void;
  alfredReply?: string;
  alfredLoading?: boolean;
}) => {
  if (!event) {
    return (
      <div className="bg-charcoal/10 border border-amber/20 rounded-2xl p-5 text-sm text-charcoal/70">
        Select an event to see summary, related contacts, location, and actions.
      </div>
    );
  }

  const related = contacts.filter((c) => event.relatedContactIds.includes(c.id));

  return (
    <motion.div
      key={event.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-charcoal/10 border border-amber/25 rounded-2xl p-5"
    >
      <h3 className="font-serif text-lg font-bold text-charcoal mb-2">{event.title}</h3>
      <p className="text-sm text-charcoal/80 mb-3">{event.summary}</p>

      <div className="space-y-2 mb-4 text-xs text-charcoal/70">
        <div className="flex items-center gap-2">
          <CalendarDays size={14} className="text-amber" />
          <span>{event.day}, {event.time}</span>
        </div>
        <div className="flex items-center gap-2">
          <MapPin size={14} className="text-amber" />
          <span>{event.location || 'No location set yet'}</span>
        </div>
      </div>

      <div className="mb-4">
        <p className="text-[10px] uppercase tracking-widest font-bold text-charcoal/50 mb-2">Related contacts</p>
        <div className="flex flex-wrap gap-2">
          {related.map((person) => (
            <span key={person.id} className="px-3 py-1 rounded-full text-xs bg-white/60 border border-amber/20 text-charcoal">
              {person.name} · {person.role}
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => onReschedule(event)}
          className="bg-amber text-white text-sm py-2.5 rounded-xl font-semibold"
        >
          Reschedule
        </button>
        <button
          onClick={() => onRemind(event)}
          className="bg-white/70 border border-amber/20 text-charcoal text-sm py-2.5 rounded-xl font-semibold"
        >
          Send reminder
        </button>
      </div>

      <button
        onClick={() => onFocus(event)}
        className="mt-3 w-full flex items-center justify-center gap-2 bg-navy/10 border border-navy/20 text-navy text-sm py-2.5 rounded-xl font-semibold hover:bg-navy/15 transition-colors"
      >
        <Focus size={14} /> Reserve Focus Time
      </button>

      {(alfredLoading || alfredReply) && (
        <div className="mt-3 bg-white/60 border border-amber/20 rounded-xl p-3 text-xs text-charcoal/80">
          {alfredLoading ? (
            <span className="flex items-center gap-2 text-charcoal/50">
              <Loader2 size={12} className="animate-spin" /> Alfred is working on it…
            </span>
          ) : (
            <span><span className="font-semibold text-amber">Alfred: </span>{alfredReply}</span>
          )}
        </div>
      )}
    </motion.div>
  );
};

const OnboardingPanel = ({
  profile,
  setProfile,
}: {
  profile: UserProfile;
  setProfile: React.Dispatch<React.SetStateAction<UserProfile>>;
}) => {
  const [draftName, setDraftName] = useState(profile.name);
  const [draftRole, setDraftRole] = useState(profile.role);
  const [draftNotes, setDraftNotes] = useState(profile.onboardingNotes);

  const runOnboarding = () => {
    const context = classifyContext(draftRole, draftNotes);
    setProfile({
      name: draftName || 'Bruce',
      role: draftRole || 'Principal',
      onboardingNotes: draftNotes,
      defaultContext: context,
      onboardingDone: true,
    });
  };

  return (
    <div className="bg-charcoal text-white rounded-2xl p-5 mb-6 shadow-lg">
      <div className="flex items-start gap-3 mb-4">
        <Sparkles size={18} className="text-amber mt-1" />
        <div>
          <h3 className="font-serif text-lg font-bold">Onboarding + Profiling Agent</h3>
          <p className="text-xs text-white/70 mt-1">
            Alfred classifies your default context as work or home. You can edit this later in Profile.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <input
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          placeholder="Your name"
          className="w-full rounded-xl bg-white/10 border border-white/20 px-3 py-2 text-sm outline-none"
        />
        <input
          value={draftRole}
          onChange={(e) => setDraftRole(e.target.value)}
          placeholder="Your role"
          className="w-full rounded-xl bg-white/10 border border-white/20 px-3 py-2 text-sm outline-none"
        />
        <textarea
          value={draftNotes}
          onChange={(e) => setDraftNotes(e.target.value)}
          placeholder="Tell Alfred about your typical week"
          rows={3}
          className="w-full rounded-xl bg-white/10 border border-white/20 px-3 py-2 text-sm outline-none resize-none"
        />
      </div>

      <button
        onClick={runOnboarding}
        className="mt-4 w-full bg-amber text-white py-2.5 rounded-xl text-sm font-semibold"
      >
        Use AI onboarding
      </button>
    </div>
  );
};

const DashboardScreen = ({
  profile,
  setProfile,
  events,
  contacts,
  selectedEvent,
  setSelectedEvent,
  addLog,
  dashboardInput,
  setDashboardInput,
  sendDashboardChat,
  onReschedule,
  onRemind,
  onFocus,
  alfredReply,
  alfredLoading,
  dashboardLoading,
  dashboardReply,
}: {
  profile: UserProfile;
  setProfile: React.Dispatch<React.SetStateAction<UserProfile>>;
  events: EventItem[];
  contacts: Contact[];
  selectedEvent: EventItem | null;
  setSelectedEvent: React.Dispatch<React.SetStateAction<EventItem | null>>;
  addLog: (msg: string) => void;
  dashboardInput: string;
  setDashboardInput: React.Dispatch<React.SetStateAction<string>>;
  sendDashboardChat: () => void;
  onReschedule: (event: EventItem) => void;
  onRemind: (event: EventItem) => void;
  onFocus: (event: EventItem) => void;
  alfredReply?: string;
  alfredLoading?: boolean;
  dashboardLoading?: boolean;
  dashboardReply?: string;
}) => {
  const weekTotal = events.length;
  const workCount = events.filter((e) => e.context === 'work').length;
  const homeCount = events.filter((e) => e.context === 'home').length;

  return (
    <div className="p-6 pb-28">
      {!profile.onboardingDone && <OnboardingPanel profile={profile} setProfile={setProfile} />}

      <header className="mb-6">
        <h1 className="text-2xl font-serif font-bold text-charcoal leading-tight">
          Weekly Dashboard
        </h1>
        <p className="text-sm text-charcoal/60 mt-1">
          {profile.onboardingDone ? `${profile.name}, default context: ${profile.defaultContext}` : 'Complete onboarding to personalize prioritization.'}
        </p>
      </header>

      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-charcoal text-white p-3 rounded-2xl">
          <p className="text-[10px] uppercase tracking-wider text-white/60">This week</p>
          <p className="text-xl font-bold mt-1">{weekTotal}</p>
        </div>
        <div className="bg-navy text-white p-3 rounded-2xl">
          <p className="text-[10px] uppercase tracking-wider text-white/60">Work</p>
          <p className="text-xl font-bold mt-1">{workCount}</p>
        </div>
        <div className="bg-amber text-white p-3 rounded-2xl">
          <p className="text-[10px] uppercase tracking-wider text-white/70">Home</p>
          <p className="text-xl font-bold mt-1">{homeCount}</p>
        </div>
      </div>

      <SectionHeader title="Upcoming This Week" />
      <div className="space-y-3 mb-6">
        {events.map((event) => (
          <motion.button
            key={event.id}
            whileTap={{ scale: 0.98 }}
            onClick={() => setSelectedEvent(event)}
            className="w-full text-left bg-white/70 border border-amber/20 rounded-2xl p-4 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-charcoal">{event.title}</h3>
                <p className="text-xs text-charcoal/50 mt-1">{event.day} · {event.time}</p>
              </div>
              <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded-full ${event.context === 'work' ? 'bg-navy/15 text-navy' : 'bg-amber/20 text-amber'}`}>
                {event.context}
              </span>
            </div>
          </motion.button>
        ))}
      </div>

      <SectionHeader title="Event Page" />
      <EventDetails
        event={selectedEvent}
        contacts={contacts}
        onReschedule={onReschedule}
        onRemind={onRemind}
        onFocus={onFocus}
        alfredReply={alfredReply}
        alfredLoading={alfredLoading}
      />

      <SectionHeader title="Quick Chat In Dashboard" />
      <div className="bg-white/70 border border-amber/20 rounded-2xl p-2 shadow-sm flex items-center gap-2 mt-2">
        <input
          value={dashboardInput}
          onChange={(e) => setDashboardInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendDashboardChat()}
          placeholder="Ask Alfred from dashboard"
          className="flex-1 bg-transparent border-none outline-none px-3 py-2 text-sm text-charcoal placeholder:text-charcoal/40"
        />
        <button onClick={sendDashboardChat} disabled={dashboardLoading} className="bg-amber text-white p-2 rounded-xl disabled:opacity-60">
          {dashboardLoading ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
        </button>
      </div>
      {dashboardReply && (
        <div className="mt-3 bg-white/60 border border-amber/20 rounded-xl p-3 text-xs text-charcoal/80">
          <span className="font-semibold text-amber">Alfred: </span>{dashboardReply}
        </div>
      )}
    </div>
  );
};

const ChatScreen = ({
  callAlfred,
  debugMode,
}: {
  callAlfred?: (msg: string) => Promise<{ text: string; thought?: string }>;
  debugMode?: boolean;
}) => {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleSend = async () => {
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

    let replyText = "Acknowledged. I mapped this to your current priorities and prepared the next action.";
    let replyThought: string | undefined;
    if (callAlfred) {
      try {
        const response = await callAlfred(newUserMsg.text);
        replyText = response.text;
        replyThought = response.thought;
      } catch {
        replyText = "I encountered an issue connecting to Alfred. Please check your connection.";
      }
    }

    const alfredMsg: Message = {
      id: (Date.now() + 1).toString(),
      sender: 'alfred',
      text: replyText,
      thought: replyThought,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, alfredMsg]);
    setIsTyping(false);
  };

  return (
    <div className="flex flex-col h-full bg-cream">
      <header className="p-6 border-b border-amber/20 bg-charcoal/10 backdrop-blur-sm sticky top-0 z-10">
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
                  : 'bg-white/75 text-charcoal rounded-tl-none'
              }`}>
                {debugMode && msg.sender === 'alfred' && msg.thought && (
                  <details className="mb-2 text-xs opacity-70 border-b border-current/10 pb-2">
                    <summary className="cursor-pointer text-[10px] uppercase tracking-widest font-bold mb-1">💭 Thought</summary>
                    <pre className="whitespace-pre-wrap break-all text-[10px] leading-relaxed max-h-40 overflow-y-auto">
                      {(() => { try { return atob(msg.thought || ''); } catch { return msg.thought || ''; } })()}
                    </pre>
                  </details>
                )}
                {msg.text}
              </div>
            </div>
          </motion.div>
        ))}
        {isTyping && (
          <div className="flex justify-start gap-3">
            <AlfredMonogram />
            <div className="bg-white/75 p-4 rounded-2xl rounded-tl-none shadow-sm flex gap-1">
              <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1 }} className="w-1.5 h-1.5 bg-amber rounded-full" />
              <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1, delay: 0.2 }} className="w-1.5 h-1.5 bg-amber rounded-full" />
              <motion.div animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1, delay: 0.4 }} className="w-1.5 h-1.5 bg-amber rounded-full" />
            </div>
          </div>
        )}
      </div>

      <div className="fixed bottom-24 left-1/2 z-40 w-[calc(100%-3rem)] max-w-[342px] -translate-x-1/2">
        <div className="bg-charcoal/10 border border-amber/20 rounded-2xl p-2 shadow-lg backdrop-blur-md flex items-center gap-2 focus-within:ring-1 ring-amber/20 transition-all">
          <input 
            type="text" 
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
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

const ContactsScreen = ({
  contacts,
  onAdd,
}: {
  contacts: Contact[];
  onAdd: (contact: Omit<Contact, 'id'>) => void;
}) => {
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [gmail, setGmail] = useState('');
  const [context, setContext] = useState<ContactContext>('home');

  const submit = () => {
    if (!name.trim() || !role.trim()) return;
    onAdd({ name, role, context, gmail: gmail.trim() || undefined });
    setName('');
    setRole('');
    setGmail('');
    setContext('home');
  };

  return (
    <div className="p-6 pb-28">
      <header className="mb-6">
        <h1 className="text-2xl font-serif font-bold text-charcoal">Household Members</h1>
        <p className="text-sm text-charcoal/60">Add family or colleague profiles for home/work contacts.</p>
      </header>

      <div className="bg-white/70 border border-amber/20 rounded-2xl p-4 mb-6">
        <SectionHeader
          title="Add Contact"
          right={
            <button onClick={submit} className="bg-amber text-white p-2 rounded-xl">
              <Plus size={16} />
            </button>
          }
        />
        <div className="space-y-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full rounded-xl bg-cream/70 border border-amber/20 px-3 py-2 text-sm outline-none" />
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role" className="w-full rounded-xl bg-cream/70 border border-amber/20 px-3 py-2 text-sm outline-none" />
          <input value={gmail} onChange={(e) => setGmail(e.target.value)} placeholder="Gmail (optional, for reminders)" type="email" className="w-full rounded-xl bg-cream/70 border border-amber/20 px-3 py-2 text-sm outline-none" />
          <div className="flex gap-2">
            <button onClick={() => setContext('home')} className={`flex-1 py-2 rounded-xl text-sm font-semibold ${context === 'home' ? 'bg-amber text-white' : 'bg-charcoal/10 text-charcoal'}`}>
              Home
            </button>
            <button onClick={() => setContext('work')} className={`flex-1 py-2 rounded-xl text-sm font-semibold ${context === 'work' ? 'bg-navy text-white' : 'bg-charcoal/10 text-charcoal'}`}>
              Work
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {contacts.map((person) => (
          <div key={person.id} className="bg-white/70 border border-amber/20 p-4 rounded-2xl flex items-center justify-between">
            <div>
              <p className="font-semibold text-charcoal">{person.name}</p>
              <p className="text-xs text-charcoal/60">{person.role}</p>
            </div>
            <span className={`text-[10px] uppercase tracking-widest font-bold px-2 py-1 rounded-full ${person.context === 'work' ? 'bg-navy/15 text-navy' : 'bg-amber/20 text-amber'}`}>
              {person.context}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const ProfileScreen = ({
  profile,
  setProfile,
  actionLog,
}: {
  profile: UserProfile;
  setProfile: React.Dispatch<React.SetStateAction<UserProfile>>;
  actionLog: string[];
}) => {
  const [name, setName] = useState(profile.name);
  const [role, setRole] = useState(profile.role);
  const [notes, setNotes] = useState(profile.onboardingNotes);

  useEffect(() => {
    setName(profile.name);
    setRole(profile.role);
    setNotes(profile.onboardingNotes);
  }, [profile]);

  const saveProfile = () => {
    setProfile((prev) => ({
      ...prev,
      name,
      role,
      onboardingNotes: notes,
      defaultContext: classifyContext(role, notes),
      onboardingDone: true,
    }));
  };

  return (
    <div className="p-6 pb-28">
      <header className="mb-6">
        <h1 className="text-2xl font-serif font-bold text-charcoal">Profile</h1>
        <p className="text-sm text-charcoal/60">Editable anytime. Onboarding preferences can be refined later.</p>
      </header>

      <div className="bg-white/70 border border-amber/20 rounded-2xl p-4 mb-6 space-y-3">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider font-bold text-charcoal/50">
          <PencilLine size={14} /> Profile Settings
        </div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full rounded-xl bg-cream/70 border border-amber/20 px-3 py-2 text-sm outline-none" />
        <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role" className="w-full rounded-xl bg-cream/70 border border-amber/20 px-3 py-2 text-sm outline-none" />
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Preferences and constraints" className="w-full rounded-xl bg-cream/70 border border-amber/20 px-3 py-2 text-sm outline-none resize-none" />

        <div className="flex items-center justify-between bg-charcoal/10 rounded-xl px-3 py-2">
          <span className="text-xs text-charcoal/70">AI default context</span>
          <span className={`text-[10px] uppercase tracking-widest font-bold px-2 py-1 rounded-full ${profile.defaultContext === 'work' ? 'bg-navy/15 text-navy' : 'bg-amber/20 text-amber'}`}>
            {profile.defaultContext}
          </span>
        </div>

        <button onClick={saveProfile} className="w-full bg-amber text-white rounded-xl py-2.5 text-sm font-semibold">
          Save Profile
        </button>
      </div>

      <SectionHeader title="Recent Actions" right={<CheckCircle2 size={16} className="text-amber" />} />
      <div className="space-y-2">
        {actionLog.length === 0 && <p className="text-xs text-charcoal/50">No actions yet.</p>}
        {actionLog.map((entry, idx) => (
          <div key={`${entry}-${idx}`} className="bg-white/70 border border-amber/20 rounded-xl px-3 py-2 text-xs text-charcoal/80">
            {entry}
          </div>
        ))}
      </div>
    </div>
  );
};

const ConnectBanner = ({
  auth,
  onConnect,
  onPasteToken,
}: {
  auth: AuthState;
  onConnect: () => void;
  onPasteToken: (token: string) => void;
}) => {
  const [showPaste, setShowPaste] = useState(false);
  const [pasteValue, setPasteValue] = useState('');

  if (auth.token && auth.sessionId && !auth.loading) return null;

  return (
    <div className="mx-6 mt-4 mb-2 bg-charcoal text-white rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <LogIn size={16} className="text-amber" />
        <span className="text-sm font-semibold font-serif">Connect Google to use live Alfred</span>
      </div>
      {auth.loading ? (
        <div className="flex items-center gap-2 text-xs text-white/60">
          <Loader2 size={12} className="animate-spin" />
          {auth.sessionId ? 'Session ready' : auth.email ? 'Creating Alfred session…' : 'Signing in…'}
        </div>
      ) : (
        <>
          {auth.error && <p className="text-xs text-red-400 mb-2">{auth.error}</p>}
          <button
            onClick={onConnect}
            className="w-full bg-amber text-white py-2 rounded-xl text-sm font-semibold mb-2"
          >
            Sign in with Google
          </button>
          <button
            onClick={() => setShowPaste(v => !v)}
            className="w-full text-xs text-white/50 underline"
          >
            {showPaste ? 'Hide' : 'Or paste access token (demo mode)'}
          </button>
          {showPaste && (
            <div className="mt-2 flex gap-2">
              <input
                value={pasteValue}
                onChange={e => setPasteValue(e.target.value)}
                placeholder="Paste Google access token"
                className="flex-1 bg-white/10 border border-white/20 rounded-xl px-3 py-2 text-xs outline-none"
              />
              <button
                onClick={() => { onPasteToken(pasteValue); setPasteValue(''); setShowPaste(false); }}
                className="bg-amber text-white px-3 py-2 rounded-xl text-xs font-semibold"
              >
                Use
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [debugMode] = useState(() => new URLSearchParams(window.location.search).has('debug'));
  const [profile, setProfile] = useState<UserProfile>({
    name: 'Bruce',
    role: 'Principal',
    onboardingNotes: '',
    defaultContext: 'work',
    onboardingDone: false,
  });
  const [contacts, setContacts] = useState<Contact[]>(INITIAL_CONTACTS);
  const [events, setEvents] = useState<EventItem[]>(INITIAL_EVENTS);
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(INITIAL_EVENTS[0]);
  const [actionLog, setActionLog] = useState<string[]>([]);
  const [dashboardInput, setDashboardInput] = useState('');

  // ─── Auth State ─────────────────────────────────────────────────────────────
  const [auth, setAuth] = useState<AuthState>(() => ({
    token: localStorage.getItem('alfred_token') ?? '',
    email: localStorage.getItem('alfred_email') ?? '',
    sessionId: localStorage.getItem('alfred_session') ?? '',
    loading: false,
    error: '',
  }));

  // ─── Alfred action reply state ───────────────────────────────────────────────
  const [alfredReply, setAlfredReply] = useState('');
  const [alfredLoading, setAlfredLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardReply, setDashboardReply] = useState('');

  // ─── Parse OAuth fragment on mount ───────────────────────────────────────────
  useEffect(() => {
    const token = parseOAuthFragment();
    if (!token) return;
    // Clear hash from URL
    history.replaceState(null, '', window.location.pathname);
    localStorage.setItem('alfred_token', token);
    setAuth(prev => ({ ...prev, token, sessionId: '', loading: true, error: '' }));
    fetchUserEmail(token)
      .then(email => {
        localStorage.setItem('alfred_email', email);
        setAuth(prev => ({ ...prev, email, loading: false }));
      })
      .catch(() => setAuth(prev => ({ ...prev, loading: false })));
  }, []);

  // ─── Create ADK session when token ready but no session ─────────────────────
  useEffect(() => {
    if (!auth.token || !auth.email || auth.sessionId || auth.loading) return;
    setAuth(prev => ({ ...prev, loading: true, error: '' }));
    createAlfredSession(auth.email, auth.token)
      .then(sessionId => {
        localStorage.setItem('alfred_session', sessionId);
        setAuth(prev => ({ ...prev, sessionId, loading: false }));
      })
      .catch(err => {
        setAuth(prev => ({ ...prev, loading: false, error: String(err) }));
      });
  }, [auth.token, auth.email, auth.sessionId, auth.loading]);

  // ─── callAlfred helper ───────────────────────────────────────────────────────
  const callAlfred = useCallback(async (msg: string): Promise<{ text: string; thought?: string }> => {
    if (!auth.sessionId || !auth.email) {
      return { text: "Please connect your Google account first to use Alfred's live features." };
    }
    return sendToAlfred(auth.email, auth.sessionId, msg);
  }, [auth.email, auth.sessionId]);

  // ─── Logging ─────────────────────────────────────────────────────────────────
  const addLog = (entry: string) => {
    setActionLog((prev) => [`${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${entry}`, ...prev].slice(0, 8));
  };

  const addContact = (contact: Omit<Contact, 'id'>) => {
    setContacts((prev) => [...prev, { ...contact, id: `c${Date.now()}` }]);
    addLog(`Added ${contact.context} contact: ${contact.name}.`);
  };

  // ─── Event action handlers ────────────────────────────────────────────────────
  const handleReschedule = async (event: EventItem) => {
    addLog(`Requesting reschedule for ${event.title}…`);
    setAlfredReply('');
    setAlfredLoading(true);
    try {
      const { text: reply } = await callAlfred(
        `Please reschedule "${event.title}" on ${event.day} at ${event.time}. Find the next available free slot in the next 7 days and update the calendar.`
      );
      setAlfredReply(reply);
      addLog(`Reschedule requested: ${event.title}`);
    } catch {
      setAlfredReply('Alfred could not complete the reschedule request.');
    }
    setAlfredLoading(false);
  };

  const handleRemind = async (event: EventItem) => {
    const related = contacts.filter(c => event.relatedContactIds.includes(c.id));
    const emails = related.map(c => c.gmail ?? c.name).join(', ');
    addLog(`Requesting reminder for ${event.title}…`);
    setAlfredReply('');
    setAlfredLoading(true);
    try {
      const { text: reply } = await callAlfred(
        `Send a reminder email for "${event.title}" on ${event.day} at ${event.time}${event.location ? ` at ${event.location}` : ''}. ${emails ? `Recipients: ${emails}.` : ''} Keep it brief and professional.`
      );
      setAlfredReply(reply);
      addLog(`Reminder sent for ${event.title}`);
    } catch {
      setAlfredReply('Alfred could not send the reminder.');
    }
    setAlfredLoading(false);
  };

  const handleFocus = async (event: EventItem) => {
    addLog(`Requesting focus block for ${event.title}…`);
    setAlfredReply('');
    setAlfredLoading(true);
    try {
      const { text: reply } = await callAlfred(
        `Block 1 hour of focus time before "${event.title}" on ${event.day} at ${event.time}. Mark it as busy and add a note saying it's pre-${event.title} prep time.`
      );
      setAlfredReply(reply);
      addLog(`Focus block requested for ${event.title}`);
    } catch {
      setAlfredReply('Alfred could not block focus time.');
    }
    setAlfredLoading(false);
  };

  const sendDashboardChat = async () => {
    if (!dashboardInput.trim()) return;
    const msg = dashboardInput.trim();
    addLog(`Dashboard query: ${msg}`);
    setDashboardInput('');
    setDashboardLoading(true);
    setDashboardReply('');
    try {
      const { text: reply } = await callAlfred(msg);
      setDashboardReply(reply);
    } catch {
      setDashboardReply('Alfred could not respond at this moment.');
    }
    setDashboardLoading(false);
  };

  // ─── Auth connect/disconnect helpers ─────────────────────────────────────────
  const handleConnect = () => {
    try {
      startGoogleOAuth();
    } catch (e) {
      setAuth(prev => ({ ...prev, error: String(e) }));
    }
  };

  const handlePasteToken = (token: string) => {
    localStorage.setItem('alfred_token', token);
    localStorage.removeItem('alfred_session');
    setAuth({ token, email: '', sessionId: '', loading: true, error: '' });
    fetchUserEmail(token)
      .then(email => {
        localStorage.setItem('alfred_email', email);
        setAuth(prev => ({ ...prev, email, loading: false }));
      })
      .catch(() => setAuth(prev => ({ ...prev, email: 'user@gmail.com', loading: false })));
  };

  // ─── Render helpers ───────────────────────────────────────────────────────────
  const renderScreen = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <DashboardScreen
            profile={profile}
            setProfile={setProfile}
            events={events}
            contacts={contacts}
            selectedEvent={selectedEvent}
            setSelectedEvent={setSelectedEvent}
            addLog={addLog}
            dashboardInput={dashboardInput}
            setDashboardInput={setDashboardInput}
            sendDashboardChat={sendDashboardChat}
            onReschedule={handleReschedule}
            onRemind={handleRemind}
            onFocus={handleFocus}
            alfredReply={alfredReply}
            alfredLoading={alfredLoading}
            dashboardLoading={dashboardLoading}
            dashboardReply={dashboardReply}
          />
        );
      case 'chat': return <ChatScreen callAlfred={callAlfred} debugMode={debugMode} />;
      case 'contacts': return <ContactsScreen contacts={contacts} onAdd={addContact} />;
      case 'profile': return <ProfileScreen profile={profile} setProfile={setProfile} actionLog={actionLog} />;
      default: return null;
    }
  };

  return (
    <div className="min-h-screen bg-cream font-sans selection:bg-amber/20 flex justify-center">
      <div className="w-full max-w-[390px] bg-cream/90 min-h-screen relative shadow-2xl overflow-hidden flex flex-col border-x border-charcoal/10">
        <main className="flex-1 overflow-y-auto">
          <ConnectBanner auth={auth} onConnect={handleConnect} onPasteToken={handlePasteToken} />
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

        <nav className="fixed bottom-0 left-1/2 z-50 w-full max-w-[390px] -translate-x-1/2 bg-charcoal/10 backdrop-blur-xl border-t border-amber/20 px-6 py-4 flex justify-between items-center">
          <NavButton 
            active={activeTab === 'dashboard'} 
            onClick={() => setActiveTab('dashboard')} 
            icon={<LayoutDashboard size={22} />} 
            label="Dashboard" 
          />
          <NavButton 
            active={activeTab === 'chat'} 
            onClick={() => setActiveTab('chat')} 
            icon={<MessageSquare size={22} />} 
            label="Alfred" 
          />
          <NavButton 
            active={activeTab === 'contacts'} 
            onClick={() => setActiveTab('contacts')} 
            icon={<Users size={22} />} 
            label="Contacts" 
          />
          <NavButton 
            active={activeTab === 'profile'} 
            onClick={() => setActiveTab('profile')} 
            icon={<User size={22} />} 
            label="Profile" 
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
