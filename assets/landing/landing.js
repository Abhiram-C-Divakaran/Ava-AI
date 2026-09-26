'use strict';
// Marketing placeholders from the design brief. Replace with verified metrics,
// consented customer testimonials, and official social URLs before publication.
const marketingContent = {
  stats: [['users','100K+','Users worldwide'],['star','4.9/5','Average rating'],['file','1M+','Conversations per month'],['shield','99.9%','Uptime & reliability']],
  testimonials: [
    {name:'Sarah Chen',role:'Product Designer',initials:'SC',quote:'AvaAI remembers the little things that matter. It feels like it truly understands me.'},
    {name:'Marcus Rivera',role:'Software Engineer',initials:'MR',quote:"It's like having a brilliant assistant who never forgets. AvaAI has made me so much more productive."},
    {name:'Emily Carter',role:'Startup Founder',initials:'EC',quote:'Beautiful, intuitive, and incredibly helpful. AvaAI is a game-changer for our team.'}
  ],
  // No official social destinations exist in the repository. Disabled until configured.
  socials: [{name:'Twitter / X',label:'𝕏',url:null},{name:'LinkedIn',label:'in',url:null},{name:'YouTube',label:'▶',url:null},{name:'Discord',label:'◉',url:null}]
};
const features = [
 ['brain','Understand Context','Reads tone, intent, and nuance in every conversation.'],
 ['database','Remember Preferences','Learns what matters to you and keeps it in memory.'],
 ['bolt','Real-time Assistance','Get instant, accurate responses whenever you need them.'],
 ['user','Personalized Replies','Tailored answers based on your unique needs and style.'],
 ['devices','Multi-device Access','Seamless experience across web, mobile, and desktop.'],
 ['shield','Secure Conversations','Your data stays private and protected, always.']
];
const faqs = [
 ['Is Ava really free?','Yes! Ava is completely free to use. No credit card required, no hidden fees. We believe in making AI accessible to everyone.'],
 ['Does Ava remember my conversations?','Yes. Ava stores your conversation history and uses the recent messages in your active chat for context. It also remembers selected facts and preferences across sessions and adapts from your feedback. You can review and clear saved memory in your account settings.'],
 ['Can Ava write and run code?','Ava can help write, explain, and debug code. Running code depends on the server configuration and execution service availability. Execution is enabled by default in development and disabled by default in production unless explicitly enabled by the operator.'],
 ['What languages does Ava support?','Ava can converse and help translate in multiple languages through its AI model; quality varies by language. When configured, DeepL provides translation for supported languages, with an AI fallback.']
];
const demos = [
 {icon:'chat',title:'Chat Naturally',subtitle:'Have real conversations',question:'Help me plan a productive week',intro:"Here's a personalized plan based on your goals and past conversations:",items:['Focus on deep work (Mon–Wed)','Schedule exercise and breaks','Set aside time for creative projects','Review and plan next week on Friday']},
 {icon:'file',title:'Get Things Done',subtitle:'From ideas to execution',question:'Help me turn my idea into a plan',intro:"Let's make your next project feel manageable:",items:['Define the outcome that matters','Break it into small, clear milestones','Choose one task to start today','Review progress and adjust together']},
 {icon:'bulb',title:'Learn & Grow',subtitle:'Personalized guidance',question:'Help me understand something new',intro:"We'll find a learning approach that works for you:",items:['Start with what you already know','Explore the idea with an example','Try a small practice exercise','Build on what you learned']},
 {icon:'star',title:'Be More You',subtitle:'An AI that gets you',question:'I prefer clear, concise explanations',intro:"I'll keep your preferences in mind as we talk:",items:['Lead with the answer','Use everyday language','Keep examples practical','Go deeper whenever you ask']}
];
const paths = {
 brain:'M9 18V5a3 3 0 0 0-5-1 3 3 0 0 0-2 5 4 4 0 0 0 0 6 3 3 0 0 0 4 5 3 3 0 0 0 3-2Zm6 0V5a3 3 0 0 1 5-1 3 3 0 0 1 2 5 4 4 0 0 1 0 6 3 3 0 0 1-4 5 3 3 0 0 1-3-2ZM5 8l4 2m-5 5 5-1m10-6-4 2m5 5-5-1M9 6h6m-6 11h6',
 database:'M20 5c0 2-16 2-16 0s16-2 16 0ZM4 5v14c0 3 16 3 16 0V5M4 10c0 3 16 3 16 0M4 15c0 3 16 3 16 0',
 bolt:'m14 2-11 12h8l-1 8 11-13h-8l1-7Z',
 user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-3a8 6 0 0 1 16 0v3Z',
 users:'M10 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM1 21v-3a6 5 0 0 1 12 0v3ZM16 4a3 3 0 0 1 0 6m0 4a6 5 0 0 1 6 5v2h-5',
 devices:'M9 2h11v18H9ZM13 17h3M2 7h7v15H2Zm3 12h1',
 shield:'M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6ZM8 12l3 3 5-6',
 heart:'M20 4c-3-2-6 0-8 3-2-3-5-5-8-3-7 5 1 12 8 17 7-5 15-12 8-17Z',
 chart:'M3 14h3v7H3Zm8-6h3v13h-3Zm8-6h3v19h-3Z',
 file:'M5 2h10l5 5v15H5ZM14 2v6h6M9 12h7m-7 4h7',
 bulb:'M8 16a7 7 0 1 1 8 0v3H8ZM9 22h6',
 check:'M9 3H3v18h18V11M8 10l4 4L22 3',
 sparkles:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3ZM3 2v4M1 4h4m15 14v5m-2-2h5',
 chat:'M21 11a9 9 0 0 1-9 9H3v-5a9 9 0 1 1 18-4ZM7 9h10M7 13h7',
 settings:'m9 3 1-2h4l1 2 3 2 2 1v4l-2 2 1 3-2 3-3-1-2 3H8l-1-3-3-1-2-3 2-3V7l3-1ZM15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
 star:'m12 2 3 6 7 1-5 5 1 8-6-4-6 4 1-8-5-5 7-1Z',
 card:'M2 5h20v15H2ZM2 10h20M5 15h5',
 play:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM10 7l7 5-7 5Z',
 moon:'M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12Z',
 menu:'M3 6h18M3 12h18M3 18h18',
 send:'m3 3 19 9-19 9 4-9-4-9Zm4 9h15',
 clip:'m8 17 8-8a3 3 0 0 0-4-4l-8 8a5 5 0 0 0 7 7l9-9a7 7 0 0 0-10-10'
};
function icon(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.sparkles}"/></svg>`;}
function icons(root=document){root.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=icon(el.dataset.icon);});}
const $=s=>document.querySelector(s);
$('#feature-grid').innerHTML=features.map(([ic,title,copy])=>`<article class="feature-card glass"><i>${icon(ic)}</i><h3>${title}</h3><p>${copy}</p></article>`).join('');
$('#stats').innerHTML=marketingContent.stats.map(([ic,value,label])=>`<div class="stat"><i>${icon(ic)}</i><div><strong>${value}</strong><span>${label}</span></div></div>`).join('');
let reviewOffset=0;
function renderReviews(){const entries=marketingContent.testimonials;$('#testimonials').innerHTML=entries.map((_,i)=>{const r=entries[(i+reviewOffset)%entries.length];return `<article class="testimonial glass"><div class="avatar" aria-hidden="true">${r.initials}</div><div><blockquote>“${r.quote}”</blockquote><strong>${r.name}</strong><small>${r.role}</small></div></article>`;}).join('');}
$('#reviews-prev').onclick=()=>{reviewOffset=(reviewOffset+2)%3;renderReviews();};$('#reviews-next').onclick=()=>{reviewOffset=(reviewOffset+1)%3;renderReviews();};renderReviews();
$('#socials').innerHTML=marketingContent.socials.map(s=>s.url?`<a href="${s.url}" aria-label="${s.name}" rel="noopener noreferrer">${s.label}</a>`:`<button disabled aria-label="${s.name} — coming soon" title="Official ${s.name} link coming soon">${s.label}</button>`).join('');
$('#faq-list').innerHTML=faqs.map(([q,a],i)=>`<article class="faq-item ${i===0?'active':''}"><h3><button class="faq-question" id="faq-question-${i}" aria-expanded="${i===0}" aria-controls="faq-answer-${i}">${q}<span aria-hidden="true">+</span></button></h3><div class="faq-answer" id="faq-answer-${i}" role="region" aria-labelledby="faq-question-${i}" aria-hidden="${i!==0}"><div><p>${a}</p></div></div></article>`).join('');
document.querySelectorAll('.faq-question').forEach(button=>button.onclick=()=>{const open=button.getAttribute('aria-expanded')!=='true';document.querySelectorAll('.faq-item').forEach(item=>{const active=item.contains(button)&&open;item.classList.toggle('active',active);item.querySelector('button').setAttribute('aria-expanded',String(active));item.querySelector('.faq-answer').setAttribute('aria-hidden',String(!active));});});
let demoIndex=0;
$('.demo-tabs').innerHTML=demos.map((d,i)=>`<button class="demo-tab" role="tab" id="demo-tab-${i}" aria-controls="demo-panel" aria-selected="${i===0}" tabindex="${i===0?0:-1}"><i>${icon(d.icon)}</i><span><strong>${d.title}</strong><small>${d.subtitle}</small></span></button>`).join('');
function setDemo(i){demoIndex=i;const d=demos[i];$('#demo-question').textContent=d.question;$('#demo-intro').textContent=d.intro;$('#demo-checklist').innerHTML=d.items.map(t=>`<li>${t}</li>`).join('');$('#demo-panel').setAttribute('aria-label',`${d.title} example`);$('#demo-panel').setAttribute('aria-labelledby',`demo-tab-${i}`);document.querySelectorAll('.demo-tab').forEach((b,n)=>{b.setAttribute('aria-selected',String(n===i));b.tabIndex=n===i?0:-1;});}
document.querySelectorAll('.demo-tab').forEach((b,i)=>{b.onclick=()=>setDemo(i);b.onkeydown=e=>{let n=i;if(['ArrowDown','ArrowRight'].includes(e.key))n=(i+1)%4;else if(['ArrowUp','ArrowLeft'].includes(e.key))n=(i+3)%4;else if(e.key==='Home')n=0;else if(e.key==='End')n=3;else return;e.preventDefault();setDemo(n);$(`#demo-tab-${n}`).focus();};});$('#demo-more').onclick=()=>setDemo((demoIndex+1)%4);setDemo(0);
icons();
// Storage is optional (private mode / policy restrictions must not break the page).
const storage={get(k){try{return localStorage.getItem(k);}catch{return null;}},set(k,v){try{localStorage.setItem(k,v);}catch{}},remove(k){try{localStorage.removeItem(k);}catch{}}};
function readUser(){try{return JSON.parse(storage.get('neurosupport_user')||'null');}catch{return null;}}
function setTheme(light){document.body.classList.toggle('light-mode',light);$('#theme-toggle').setAttribute('aria-pressed',String(light));$('#theme-toggle').setAttribute('aria-label',`Switch to ${light?'dark':'light'} theme`);storage.set('ava-theme',light?'light':'dark');}
setTheme(storage.get('ava-theme')==='light');$('#theme-toggle').onclick=()=>setTheme(!document.body.classList.contains('light-mode'));
function closeMenu(){$('#nav-links').classList.remove('open');$('#menu-toggle').setAttribute('aria-expanded','false');$('#menu-toggle').setAttribute('aria-label','Open navigation');}
$('#menu-toggle').onclick=()=>{const open=$('#nav-links').classList.toggle('open');$('#menu-toggle').setAttribute('aria-expanded',String(open));$('#menu-toggle').setAttribute('aria-label',open?'Close navigation':'Open navigation');};document.querySelectorAll('.nav-links a').forEach(a=>a.onclick=closeMenu);
// CTA authentication is validated by the server rather than trusting stored UI state.
async function destination(){const user=readUser();if(!user?.user_id)return '/auth.html?mode=signup';try{const res=await fetch(`/api/sessions/${encodeURIComponent(user.user_id)}`,{credentials:'same-origin'});return res.ok?'/chat.html':'/auth.html?mode=signup';}catch{return '/auth.html?mode=signup';}}
document.querySelectorAll('[data-start]').forEach(a=>a.addEventListener('click',async e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();a.setAttribute('aria-busy','true');location.href=await destination();}));
const video=$('#video-dialog');$('#watch-video').onclick=()=>video.showModal();$('.modal-close').onclick=()=>video.close();$('#explore-demo').onclick=()=>{video.close();$('#solutions').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});$('#demo-tab-0').focus({preventScroll:true});};video.addEventListener('close',()=>$('#watch-video').focus());
const drawer=$('#chat-drawer'),history=$('#chat-history'),form=$('#chat-form'),input=$('#chat-input');
let activeUser=null,sessionId=null,busy=false,initialized=false,opening=false,returnFocus=null;
function message(text,kind='assistant'){const el=document.createElement('div');el.className=`chat-message ${kind}`;el.textContent=text;history.append(el);history.scrollTop=history.scrollHeight;return el;}
function signedOut(){activeUser=null;sessionId=null;form.hidden=true;$('#chat-auth').hidden=false;$('#chat-status').textContent='Sign in to chat';}
async function openChat(prompt=''){
 returnFocus=document.activeElement;drawer.hidden=false;$('#chat-launcher').setAttribute('aria-expanded','true');$('#chat-close').focus();if(prompt)input.value=prompt;if(opening)return;
 const user=readUser();if(initialized&&activeUser?.user_id===user?.user_id){if(activeUser)input.focus();return;}
 opening=true;form.hidden=true;$('#chat-auth').hidden=true;history.replaceChildren();message('Hello! I’m Ava. What would you like to explore today?');$('#chat-status').textContent='Connecting…';
 try{
  if(!user?.user_id){signedOut();initialized=true;return;}
  const response=await fetch(`/api/sessions/${encodeURIComponent(user.user_id)}`,{credentials:'same-origin'});
  if(response.status===401||response.status===403){signedOut();initialized=true;return;}
  if(!response.ok)throw new Error('Unable to connect. Please close the panel and try again.');
  activeUser=user;sessionId=storage.get(`ava-landing-session:${user.user_id}`);form.hidden=false;$('#chat-auth').hidden=true;$('#chat-status').textContent='Online';
  if(sessionId){const res=await fetch(`/api/sessions/${encodeURIComponent(user.user_id)}/${encodeURIComponent(sessionId)}/messages`,{credentials:'same-origin'});if(res.ok){const data=await res.json();if(data.messages?.length){history.replaceChildren();data.messages.forEach(m=>{message(m.user_message,'user');const el=message(m.agent_response);addFeedback(el,m.message_id);});}}else if(res.status===404){storage.remove(`ava-landing-session:${user.user_id}`);sessionId=null;}else if(res.status===401||res.status===403){signedOut();}else{throw new Error('Could not load your saved conversation. Please reopen the panel to retry.');}}
  initialized=true;if(activeUser&&!drawer.hidden)input.focus();
 }catch(error){$('#chat-status').textContent='Connection unavailable';message(error.message,'error');initialized=false;form.hidden=true;}finally{opening=false;}
}
function closeChat(){drawer.hidden=true;$('#chat-launcher').setAttribute('aria-expanded','false');(returnFocus?.isConnected?returnFocus:$('#chat-launcher')).focus();}
$('#chat-launcher').onclick=()=>drawer.hidden?openChat():closeChat();$('#chat-close').onclick=closeChat;document.querySelectorAll('[data-open-chat]').forEach(b=>b.onclick=()=>openChat());document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>openChat(b.dataset.prompt));
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();if(!drawer.hidden){e.preventDefault();closeChat();}}});
// Keep keyboard traversal inside the open conversation while retaining its trigger.
drawer.addEventListener('keydown',e=>{if(e.key!=='Tab')return;const controls=[...drawer.querySelectorAll('button,a,textarea')].filter(el=>!el.disabled&&el.getClientRects().length);const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}});
function addFeedback(el,id){if(!id)return;const row=document.createElement('div');row.className='feedback-actions';for(const [label,helpful] of [['Helpful',true],['Not helpful',false]]){const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('aria-pressed','false');button.onclick=async()=>{button.disabled=true;try{const res=await fetch('/api/feedback',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:activeUser.user_id,session_id:sessionId,message_id:id,helpful})});if(!res.ok)throw new Error('Feedback could not be saved. Try again.');row.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}catch(error){message(error.message,'error');}finally{button.disabled=false;}};row.append(button);}el.append(row);}
input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();form.requestSubmit();}});
form.addEventListener('submit',async e=>{
 e.preventDefault();const text=input.value.trim();if(!text||busy||!activeUser)return;
 if(readUser()?.user_id!==activeUser.user_id){initialized=false;await openChat(text);return;}
 busy=true;input.value='';input.disabled=true;$('#chat-send').disabled=true;$('#chat-status').textContent='Thinking…';message(text,'user');const reply=message('Thinking…');let full='',complete=false;
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),120000);
 try{
  const response=await fetch('/api/chat/stream',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:activeUser.user_id,message:text,session_id:sessionId,mode:'flash',web_search:false}),signal:controller.signal});
  if(response.status===401||response.status===403){signedOut();throw new Error('Your session has expired. Sign in to continue.');}
  if(response.status===404){storage.remove(`ava-landing-session:${activeUser.user_id}`);sessionId=null;throw new Error('This conversation is no longer available. Send your message again to start a new one.');}
  if(!response.ok)throw new Error(response.status===429?'Please wait a moment before sending another message.':'Ava could not respond. Please try again.');
  if(!response.body)throw new Error('Streaming is unavailable in this browser. Use the full workspace.');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  function consume(event){for(const line of event.split('\n')){if(!line.startsWith('data:'))continue;const data=JSON.parse(line.slice(5).trim());if(data.error)throw new Error(data.error);if(data.chunk){full+=data.chunk;reply.textContent=full;$('#chat-status').textContent='Responding…';}if(data.status&&!full)reply.textContent=data.status;if(data.done){complete=true;sessionId=data.session_id;storage.set(`ava-landing-session:${activeUser.user_id}`,sessionId);reply.textContent=full||'Response completed.';addFeedback(reply,data.message_id);}history.scrollTop=history.scrollHeight;}}
  while(true){const {done,value}=await reader.read();if(done){buffer+=decoder.decode();if(buffer.trim())consume(buffer);break;}buffer+=decoder.decode(value,{stream:true});buffer=buffer.replace(/\r\n/g,'\n');const events=buffer.split('\n\n');buffer=events.pop()||'';events.forEach(consume);}
  if(!complete)throw new Error('The connection ended before the response was saved. Please try again.');
 }catch(error){reply.textContent=(full?`${full}\n\n`:'')+(error.name==='AbortError'?'The response took too long. Please try again.':error.message);reply.classList.add('error');if(!full)input.value=text;}finally{clearTimeout(timeout);busy=false;input.disabled=false;$('#chat-send').disabled=false;$('#chat-status').textContent=activeUser?'Online':'Sign in to chat';if(activeUser&&!drawer.hidden)input.focus();}
});
