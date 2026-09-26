'use strict';

/**
 * AvaAI Landing Page Application Logic
 *
 * Technical Trust Metrics:
 * - 6 Behavior Dimensions: Formality, Verbosity, Tone, Reasoning, Persona, Autonomy (adaptation.py)
 * - 6 Response Strategies: Direct Answer, Guided Reasoning, Socratic Questioning,
 *   Structured Framework, Expressive Storytelling, Minimal Confirmation
 * - 128+ Automated Tests: Verified backend regression, reliability, security, LLM & adaptation suite
 * - 0 Vector Databases: Ava uses pure structured persistent factual memory without vector DBs or RAG
 */
const trustContent = {
  stats: [
    ['brain', '6', 'Behavior Dimensions'],
    ['sparkles', '6', 'Response Strategies'],
    ['check', '128+', 'Automated Tests'],
    ['database', '0', 'Vector Databases']
  ],
  // Replace with verified user testimonials before public marketing use.
  testimonials: [
    {
      name: 'Sarah Chen',
      role: 'Product Designer',
      initials: 'SC',
      quote: 'AvaAI remembers the little things that matter across sessions. It feels like an assistant that genuinely understands context.'
    },
    {
      name: 'Marcus Rivera',
      role: 'Software Engineer',
      initials: 'MR',
      quote: 'The behavioral adaptation is incredible — Ava matches my preferred explanation depth without me having to repeat instructions.'
    },
    {
      name: 'Emily Carter',
      role: 'Startup Founder',
      initials: 'EC',
      quote: 'Clean, fast, and remarkably helpful. Having persistent memory without heavyweight setup has made our workflow seamless.'
    }
  ],
  socials: [
    { name: 'Twitter / X', label: '𝕏', url: null },
    { name: 'LinkedIn', label: 'in', url: null },
    { name: 'YouTube', label: '▶', url: null },
    { name: 'Discord', label: '◉', url: null }
  ]
};

const features = [
  ['brain', 'Understand Context', 'Reads intent, sentiment, and conversational context.'],
  ['database', 'Remember Preferences', 'Keeps persistent user facts and learned preferences across sessions.'],
  ['bolt', 'Real-time Assistance', 'Fast streaming responses through the existing Ava chat system.'],
  ['user', 'Personalized Replies', "Adapts response style using Ava's behavioral preference engine."],
  ['file', 'Multi-session Memory', 'Carries relevant factual memory across conversations.'],
  ['shield', 'Private & Secure', 'Session authentication, ownership checks, rate limiting, and privacy controls.']
];

const faqs = [
  [
    'Is AvaAI free to use?',
    'AvaAI is currently free to use during our release preview. You can create an account in seconds without a credit card to start chatting.'
  ],
  [
    'Does Ava remember my conversations?',
    'Yes. Ava maintains current-session context, stores persistent factual memory across conversations, and learns behavioral preferences to adapt response styles over time. You retain complete control to review or delete saved memories at any time.'
  ],
  [
    'Can Ava write and run code?',
    'Ava can write, explain, and debug code across numerous programming languages. Code execution is available as a tool, but is disabled by default in production deployments unless explicitly configured by the system administrator.'
  ],
  [
    'What model powers Ava?',
    'Ava is powered by openai/gpt-oss-120b via Groq for high-speed, intelligent, and context-aware responses.'
  ],
  [
    'Does Ava use RAG?',
    "No. Ava's personal memory and behavioral adaptation architecture does not use vector embeddings or a vector database. Instead, Ava uses structured persistent factual memory and feedback-driven strategy learning."
  ],
  [
    'Can I delete my data?',
    'Yes. You have full control over your privacy and data. You can delete individual conversation sessions, clear stored factual memory, or request full account deletion directly within your account settings.'
  ]
];

const demos = [
  {
    icon: 'chat',
    title: 'Chat Naturally',
    subtitle: 'Have real conversations',
    question: 'Help me plan a productive week.',
    intro: "Here's a personalized plan based on your goals and preferences:",
    items: [
      'Focus on deep work during your strongest hours',
      'Schedule exercise and recovery breaks',
      'Reserve time for creative projects',
      'Review the week before planning the next one'
    ],
    followup: 'Would you like me to break this into a daily schedule?'
  },
  {
    icon: 'file',
    title: 'Get Things Done',
    subtitle: 'From ideas to execution',
    question: 'Help me turn my project idea into an executable plan.',
    intro: "Let's structure your project into clear, achievable milestones:",
    items: [
      'Define core objectives and success criteria',
      'Break scope into weekly deliverables and tasks',
      'Identify critical technical dependencies early',
      'Establish a checkpoint cadence to review progress'
    ],
    followup: 'Would you like me to outline the sprint checklist for Week 1?'
  },
  {
    icon: 'bulb',
    title: 'Learn & Grow',
    subtitle: 'Personalized guidance',
    question: 'Help me understand how distributed consensus works.',
    intro: "Here's an intuitive progression tailored to your software background:",
    items: [
      'Start with why single-node state fails under partition',
      'Explore leader election and log replication principles',
      'Walk through how Raft and Paxos ensure consistency',
      'Review real-world edge cases like network split-brains'
    ],
    followup: 'Shall we walk through a visual leader-election scenario?'
  },
  {
    icon: 'sparkles',
    title: 'Personalized Over Time',
    subtitle: 'An AI that adapts to you',
    question: 'How do you adapt to my working style?',
    intro: "Ava continuously refines its response policies based on your feedback:",
    items: [
      'Calibrates verbosity and formality to your style',
      'Selects optimal reasoning and structure strategies',
      'Preserves verified domain facts across conversations',
      'Reinforces winning response tactics automatically'
    ],
    followup: 'Would you like to explore your behavioral adaptation profile?'
  }
];

const paths = {
  brain: 'M9 18V5a3 3 0 0 0-5-1 3 3 0 0 0-2 5 4 4 0 0 0 0 6 3 3 0 0 0 4 5 3 3 0 0 0 3-2Zm6 0V5a3 3 0 0 1 5-1 3 3 0 0 1 2 5 4 4 0 0 1 0 6 3 3 0 0 1-4 5 3 3 0 0 1-3-2ZM5 8l4 2m-5 5 5-1m10-6-4 2m5 5-5-1M9 6h6m-6 11h6',
  database: 'M20 5c0 2-16 2-16 0s16-2 16 0ZM4 5v14c0 3 16 3 16 0V5M4 10c0 3 16 3 16 0M4 15c0 3 16 3 16 0',
  bolt: 'm14 2-11 12h8l-1 8 11-13h-8l1-7Z',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-3a8 6 0 0 1 16 0v3Z',
  users: 'M10 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM1 21v-3a6 5 0 0 1 12 0v3ZM16 4a3 3 0 0 1 0 6m0 4a6 5 0 0 1 6 5v2h-5',
  devices: 'M9 2h11v18H9ZM13 17h3M2 7h7v15H2Zm3 12h1',
  shield: 'M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6ZM8 12l3 3 5-6',
  heart: 'M20 4c-3-2-6 0-8 3-2-3-5-5-8-3-7 5 1 12 8 17 7-5 15-12 8-17Z',
  chart: 'M3 14h3v7H3Zm8-6h3v13h-3Zm8-6h3v19h-3Z',
  file: 'M5 2h10l5 5v15H5ZM14 2v6h6M9 12h7m-7 4h7',
  bulb: 'M8 16a7 7 0 1 1 8 0v3H8ZM9 22h6',
  check: 'M9 3H3v18h18V11M8 10l4 4L22 3',
  sparkles: 'm12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3ZM3 2v4M1 4h4m15 14v5m-2-2h5',
  chat: 'M21 11a9 9 0 0 1-9 9H3v-5a9 9 0 1 1 18-4ZM7 9h10M7 13h7',
  settings: 'm9 3 1-2h4l1 2 3 2 2 1v4l-2 2 1 3-2 3-3-1-2 3H8l-1-3-3-1-2-3 2-3V7l3-1ZM15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  star: 'm12 2 3 6 7 1-5 5 1 8-6-4-6 4 1-8-5-5 7-1Z',
  card: 'M2 5h20v15H2ZM2 10h20M5 15h5',
  play: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM10 7l7 5-7 5Z',
  moon: 'M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12Z',
  menu: 'M3 6h18M3 12h18M3 18h18',
  send: 'm3 3 19 9-19 9 4-9-4-9Zm4 9h15',
  clip: 'm8 17 8-8a3 3 0 0 0-4-4l-8 8a5 5 0 0 0 7 7l9-9a7 7 0 0 0-10-10'
};

function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.sparkles}"/></svg>`;
}

function renderIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach(el => {
    el.innerHTML = icon(el.dataset.icon);
  });
}

const $ = s => document.querySelector(s);

// Render Features
$('#feature-grid').innerHTML = features
  .map(
    ([ic, title, copy]) =>
      `<article class="feature-card glass"><i>${icon(ic)}</i><h3>${title}</h3><p>${copy}</p></article>`
  )
  .join('');

// Render Stats (Truthful verified metrics)
$('#stats').innerHTML = trustContent.stats
  .map(
    ([ic, value, label]) =>
      `<div class="stat"><i>${icon(ic)}</i><div><strong>${value}</strong><span>${label}</span></div></div>`
  )
  .join('');

// Render Testimonials with data-demo-content="true"
let reviewOffset = 0;
function renderReviews() {
  const entries = trustContent.testimonials;
  $('#testimonials').innerHTML = entries
    .map((_, i) => {
      const r = entries[(i + reviewOffset) % entries.length];
      return `<article class="testimonial glass" data-demo-content="true"><div class="avatar" aria-hidden="true">${r.initials}</div><div><blockquote>“${r.quote}”</blockquote><strong>${r.name}</strong><small>${r.role}</small></div></article>`;
    })
    .join('');
}
$('#reviews-prev').onclick = () => {
  reviewOffset = (reviewOffset + 2) % 3;
  renderReviews();
};
$('#reviews-next').onclick = () => {
  reviewOffset = (reviewOffset + 1) % 3;
  renderReviews();
};
renderReviews();

// Social links
$('#socials').innerHTML = trustContent.socials
  .map(s =>
    s.url
      ? `<a href="${s.url}" aria-label="${s.name}" rel="noopener noreferrer">${s.label}</a>`
      : `<button disabled aria-label="${s.name} — coming soon" title="Official ${s.name} link coming soon">${s.label}</button>`
  )
  .join('');

// Render FAQs (Accessible Accordion)
$('#faq-list').innerHTML = faqs
  .map(
    ([q, a], i) =>
      `<article class="faq-item ${i === 0 ? 'active' : ''}"><h3><button class="faq-question" id="faq-question-${i}" aria-expanded="${i === 0}" aria-controls="faq-answer-${i}">${q}<span aria-hidden="true">+</span></button></h3><div class="faq-answer" id="faq-answer-${i}" role="region" aria-labelledby="faq-question-${i}" aria-hidden="${i !== 0}"><div><p>${a}</p></div></div></article>`
  )
  .join('');

document.querySelectorAll('.faq-question').forEach(button => {
  button.onclick = () => {
    const isCurrentlyOpen = button.getAttribute('aria-expanded') === 'true';
    document.querySelectorAll('.faq-item').forEach(item => {
      const isTarget = item.contains(button);
      const shouldOpen = isTarget && !isCurrentlyOpen;
      item.classList.toggle('active', shouldOpen);
      const btn = item.querySelector('.faq-question');
      const ans = item.querySelector('.faq-answer');
      btn.setAttribute('aria-expanded', String(shouldOpen));
      ans.setAttribute('aria-hidden', String(!shouldOpen));
    });
  };
});

// Interactive Product Demo Mockup
let demoIndex = 0;
$('.demo-tabs').innerHTML = demos
  .map(
    (d, i) =>
      `<button class="demo-tab" role="tab" id="demo-tab-${i}" aria-controls="demo-panel" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}"><i>${icon(d.icon)}</i><span><strong>${d.title}</strong><small>${d.subtitle}</small></span></button>`
  )
  .join('');

function setDemo(i) {
  demoIndex = i;
  const d = demos[i];
  $('#demo-question').textContent = d.question;
  $('#demo-intro').textContent = d.intro;
  $('#demo-checklist').innerHTML = d.items.map(t => `<li>${t}</li>`).join('');
  $('#demo-followup').textContent = d.followup;
  $('#demo-panel').setAttribute('aria-label', `${d.title} example`);
  $('#demo-panel').setAttribute('aria-labelledby', `demo-tab-${i}`);
  document.querySelectorAll('.demo-tab').forEach((b, n) => {
    b.setAttribute('aria-selected', String(n === i));
    b.tabIndex = n === i ? 0 : -1;
  });
}

document.querySelectorAll('.demo-tab').forEach((b, i) => {
  b.onclick = () => setDemo(i);
  b.onkeydown = e => {
    let n = i;
    if (['ArrowDown', 'ArrowRight'].includes(e.key)) n = (i + 1) % demos.length;
    else if (['ArrowUp', 'ArrowLeft'].includes(e.key)) n = (i + demos.length - 1) % demos.length;
    else if (e.key === 'Home') n = 0;
    else if (e.key === 'End') n = demos.length - 1;
    else return;
    e.preventDefault();
    setDemo(n);
    $(`#demo-tab-${n}`).focus();
  };
});
$('#demo-more').onclick = () => setDemo((demoIndex + 1) % demos.length);
setDemo(0);

renderIcons();

// Safe storage access
const storage = {
  get(k) {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem(k, v);
    } catch {}
  },
  remove(k) {
    try {
      localStorage.removeItem(k);
    } catch {}
  }
};

function readUser() {
  try {
    return JSON.parse(storage.get('neurosupport_user') || 'null');
  } catch {
    return null;
  }
}

// Theme management
function setTheme(light) {
  document.body.classList.toggle('light-mode', light);
  $('#theme-toggle').setAttribute('aria-pressed', String(light));
  $('#theme-toggle').setAttribute('aria-label', `Switch to ${light ? 'dark' : 'light'} theme`);
  storage.set('ava-theme', light ? 'light' : 'dark');
}
setTheme(storage.get('ava-theme') === 'light');
$('#theme-toggle').onclick = () => setTheme(!document.body.classList.contains('light-mode'));

// Mobile menu toggle
function closeMenu() {
  $('#nav-links').classList.remove('open');
  $('#menu-toggle').setAttribute('aria-expanded', 'false');
  $('#menu-toggle').setAttribute('aria-label', 'Open navigation');
}
$('#menu-toggle').onclick = () => {
  const open = $('#nav-links').classList.toggle('open');
  $('#menu-toggle').setAttribute('aria-expanded', String(open));
  $('#menu-toggle').setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
};
document.querySelectorAll('.nav-links a').forEach(a => (a.onclick = closeMenu));

// Auth-aware CTA routing
async function destination() {
  const user = readUser();
  if (!user?.user_id) return '/auth.html?mode=signup';
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(user.user_id)}`, {
      credentials: 'same-origin'
    });
    return res.ok ? '/chat.html' : '/auth.html?mode=signup';
  } catch {
    return '/auth.html?mode=signup';
  }
}
document.querySelectorAll('[data-start]').forEach(a =>
  a.addEventListener('click', async e => {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    a.setAttribute('aria-busy', 'true');
    location.href = await destination();
  })
);

// Watch Demo dialog
const demoDialog = $('#demo-dialog');
$('#watch-demo').onclick = () => demoDialog.showModal();
demoDialog.querySelector('.modal-close').onclick = () => demoDialog.close();
$('#explore-demo').onclick = () => {
  demoDialog.close();
  $('#solutions').scrollIntoView({
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'
  });
  $('#demo-tab-0').focus({ preventScroll: true });
};
demoDialog.addEventListener('close', () => $('#watch-demo').focus());

// Floating Ava Chatbot Drawer
const drawer = $('#chat-drawer'),
  history = $('#chat-history'),
  form = $('#chat-form'),
  input = $('#chat-input');
let activeUser = null,
  sessionId = null,
  busy = false,
  initialized = false,
  opening = false,
  returnFocus = null;

function appendMessage(text, kind = 'assistant') {
  const el = document.createElement('div');
  el.className = `chat-message ${kind}`;
  el.textContent = text;
  history.append(el);
  history.scrollTop = history.scrollHeight;
  return el;
}

function signedOut() {
  activeUser = null;
  sessionId = null;
  form.hidden = true;
  $('#chat-auth').hidden = false;
  $('#chat-status').textContent = 'Sign in to chat';
}

async function openChat(prompt = '') {
  returnFocus = document.activeElement;
  drawer.hidden = false;
  $('#chat-launcher').setAttribute('aria-expanded', 'true');
  $('#chat-close').focus();
  if (prompt) input.value = prompt;
  if (opening) return;

  const user = readUser();
  if (initialized && activeUser?.user_id === user?.user_id) {
    if (activeUser) input.focus();
    return;
  }

  opening = true;
  form.hidden = true;
  $('#chat-auth').hidden = true;
  history.replaceChildren();
  appendMessage('Hello! I’m Ava. What would you like to explore today?');
  $('#chat-status').textContent = 'Connecting…';

  try {
    if (!user?.user_id) {
      signedOut();
      initialized = true;
      return;
    }
    const response = await fetch(`/api/sessions/${encodeURIComponent(user.user_id)}`, {
      credentials: 'same-origin'
    });
    if (response.status === 401 || response.status === 403) {
      signedOut();
      initialized = true;
      return;
    }
    if (!response.ok) throw new Error('Unable to connect. Please close the panel and try again.');

    activeUser = user;
    sessionId = storage.get(`ava-landing-session:${user.user_id}`);
    form.hidden = false;
    $('#chat-auth').hidden = true;
    $('#chat-status').textContent = 'Online';

    if (sessionId) {
      const res = await fetch(
        `/api/sessions/${encodeURIComponent(user.user_id)}/${encodeURIComponent(sessionId)}/messages`,
        { credentials: 'same-origin' }
      );
      if (res.ok) {
        const data = await res.json();
        if (data.messages?.length) {
          history.replaceChildren();
          data.messages.forEach(m => {
            appendMessage(m.user_message, 'user');
            const el = appendMessage(m.agent_response);
            addFeedback(el, m.message_id);
          });
        }
      } else if (res.status === 404) {
        storage.remove(`ava-landing-session:${user.user_id}`);
        sessionId = null;
      } else if (res.status === 401 || res.status === 403) {
        signedOut();
      } else {
        throw new Error('Could not load your saved conversation. Please reopen the panel to retry.');
      }
    }
    initialized = true;
    if (activeUser && !drawer.hidden) input.focus();
  } catch (error) {
    $('#chat-status').textContent = 'Connection unavailable';
    appendMessage(error.message, 'error');
    initialized = false;
    form.hidden = true;
  } finally {
    opening = false;
  }
}

function closeChat() {
  drawer.hidden = true;
  $('#chat-launcher').setAttribute('aria-expanded', 'false');
  (returnFocus?.isConnected ? returnFocus : $('#chat-launcher')).focus();
}

$('#chat-launcher').onclick = () => (drawer.hidden ? openChat() : closeChat());
$('#chat-close').onclick = closeChat;
$('#chat-minimize').onclick = closeChat;
document.querySelectorAll('[data-open-chat]').forEach(b => (b.onclick = () => openChat()));
document.querySelectorAll('[data-prompt]').forEach(b => (b.onclick = () => openChat(b.dataset.prompt)));

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeMenu();
    if (!drawer.hidden) {
      e.preventDefault();
      closeChat();
    }
  }
});

// Trap focus in open chat drawer
drawer.addEventListener('keydown', e => {
  if (e.key !== 'Tab') return;
  const controls = [...drawer.querySelectorAll('button,a,textarea')].filter(
    el => !el.disabled && el.getClientRects().length
  );
  const first = controls[0],
    last = controls.at(-1);
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
});

// Feedback actions
function addFeedback(el, id) {
  if (!id) return;
  const row = document.createElement('div');
  row.className = 'feedback-actions';
  for (const [label, helpful] of [
    ['👍 Helpful', true],
    ['👎 Not helpful', false]
  ]) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.setAttribute('aria-pressed', 'false');
    button.onclick = async () => {
      button.disabled = true;
      try {
        const res = await fetch('/api/feedback', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: activeUser.user_id,
            session_id: sessionId,
            message_id: id,
            helpful
          })
        });
        if (!res.ok) throw new Error('Feedback could not be saved. Try again.');
        row.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
      } catch (error) {
        appendMessage(error.message, 'error');
      } finally {
        button.disabled = false;
      }
    };
    row.append(button);
  }
  el.append(row);
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// Send message via POST /api/chat/stream
form.addEventListener('submit', async e => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || busy || !activeUser) return;
  if (readUser()?.user_id !== activeUser.user_id) {
    initialized = false;
    await openChat(text);
    return;
  }

  busy = true;
  input.value = '';
  input.disabled = true;
  $('#chat-send').disabled = true;
  $('#chat-status').textContent = 'Thinking…';
  appendMessage(text, 'user');
  const reply = appendMessage('Thinking…');
  let full = '',
    complete = false;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);

  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: activeUser.user_id,
        message: text,
        session_id: sessionId,
        mode: 'flash',
        web_search: false
      }),
      signal: controller.signal
    });

    if (response.status === 401 || response.status === 403) {
      signedOut();
      throw new Error('Your session has expired. Sign in to continue.');
    }
    if (response.status === 404) {
      storage.remove(`ava-landing-session:${activeUser.user_id}`);
      sessionId = null;
      throw new Error('This conversation is no longer available. Send your message again to start a new one.');
    }
    if (!response.ok) {
      throw new Error(
        response.status === 429
          ? 'Please wait a moment before sending another message.'
          : 'Ava could not respond. Please try again.'
      );
    }
    if (!response.body) throw new Error('Streaming is unavailable in this browser. Use the full workspace.');

    const reader = response.body.getReader(),
      decoder = new TextDecoder();
    let buffer = '';

    function consume(event) {
      for (const line of event.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const data = JSON.parse(line.slice(5).trim());
        if (data.error) throw new Error(data.error);
        if (data.chunk) {
          full += data.chunk;
          reply.textContent = full;
          $('#chat-status').textContent = 'Responding…';
        }
        if (data.status && !full) reply.textContent = data.status;
        if (data.done) {
          complete = true;
          sessionId = data.session_id;
          storage.set(`ava-landing-session:${activeUser.user_id}`, sessionId);
          reply.textContent = full || 'Response completed.';
          addFeedback(reply, data.message_id);
        }
        history.scrollTop = history.scrollHeight;
      }
    }

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim()) consume(buffer);
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, '\n');
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';
      events.forEach(consume);
    }
    if (!complete) throw new Error('The connection ended before the response was saved. Please try again.');
  } catch (error) {
    reply.textContent =
      (full ? `${full}\n\n` : '') +
      (error.name === 'AbortError' ? 'The response took too long. Please try again.' : error.message);
    reply.classList.add('error');
    if (!full) input.value = text;
  } finally {
    clearTimeout(timeout);
    busy = false;
    input.disabled = false;
    $('#chat-send').disabled = false;
    $('#chat-status').textContent = activeUser ? 'Online' : 'Sign in to chat';
    if (activeUser && !drawer.hidden) input.focus();
  }
});
