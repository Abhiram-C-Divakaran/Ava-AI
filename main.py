# main.py
import os
import time
import uuid
import json
import shutil
import zipfile
import io
import re
import secrets
import aiohttp
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
from io import BytesIO

from llm import call_llm, call_llm_streaming, call_llm_with_constraints
from MLpipeline import SentimentAnalyzer, IntentClassifier, FrustrationDetector
import database as db
import search
import memory
import powers

from dotenv import load_dotenv
load_dotenv()

# OAuth
from authlib.integrations.starlette_client import OAuth, OAuthError

try:
    from pptx import Presentation
    PPT_AVAILABLE = True
except ImportError:
    PPT_AVAILABLE = False

try:
    import replicate
    REPLICATE_AVAILABLE = True
except ImportError:
    REPLICATE_AVAILABLE = False

# ─── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield

app = FastAPI(title="Ava AI", version="2.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", str(uuid.uuid4())))

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="Admin authentication required")

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
)

sentiment_analyzer = SentimentAnalyzer()
intent_classifier = IntentClassifier()
frustration_detector = FrustrationDetector()

def is_support_issue(message: str, intent: str) -> bool:
    support_intents = ["billing_issue", "login_issue", "app_crash", "performance_issue",
                       "data_loss", "connectivity", "installation", "escalation_request"]
    if intent in support_intents:
        return True
    support_keywords = ["error", "crash", "not working", "broken", "help", "issue",
                        "problem", "can't", "doesn't", "failed", "login", "password",
                        "refund", "payment"]
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in support_keywords)

# Language name lookup for common codes
_LANG_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ru": "Russian", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi",
    "nl": "Dutch", "pl": "Polish", "tr": "Turkish", "sv": "Swedish",
    "da": "Danish", "fi": "Finnish", "no": "Norwegian", "uk": "Ukrainian",
    "vi": "Vietnamese", "th": "Thai", "id": "Indonesian", "ms": "Malay",
    "ro": "Romanian", "cs": "Czech", "hu": "Hungarian", "el": "Greek",
}

def _detect_translation(message: str) -> dict | None:
    msg = message.strip().lower()
    m = re.search(
        r"\b(translate|convert|render)\b.*?\bto\b\s+([a-z]+)", msg, re.IGNORECASE
    )
    if m:
        tgt_word = m.group(2).strip().title()
        src_m = re.search(r"\bfrom\b\s+([a-z]+)", msg, re.IGNORECASE)
        src_word = src_m.group(1).strip().title() if src_m else "auto-detect"
        return {"src": src_word, "tgt": tgt_word}
    m2 = re.search(
        r"\b(how do you say|what is|what'?s|say it|write it)\b.*?\bin\b\s+([a-z]+)", msg, re.IGNORECASE
    )
    if m2:
        tgt_word = m2.group(2).strip().title()
        return {"src": "auto-detect", "tgt": tgt_word}
    return None

# ─── Pydantic models ────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    doc_id: Optional[str] = None
    image_base64: Optional[str] = None
    image_mime: Optional[str] = "image/jpeg"
    file_context: Optional[str] = None
    file_name: Optional[str] = None
    mode: Optional[str] = "flash"
    web_search: Optional[bool] = False

class FeedbackRequest(BaseModel):
    user_id: str
    session_id: str
    message_id: str
    helpful: bool

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    terms_accepted: Optional[bool] = False

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SuggestionRequest(BaseModel):
    user_id: str
    current_input: str

class PPTRequest(BaseModel):
    user_id: str
    topic: str
    slides: int = 5

class ImageRequest(BaseModel):
    user_id: str
    prompt: str

class PreferencesUpdate(BaseModel):
    custom_instructions: Optional[str] = None
    personality: Optional[str] = None
    theme: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None

class RenameRequest(BaseModel):
    new_title: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class TermsAcceptRequest(BaseModel):
    terms_accepted: bool

# ─── Auth ──────────────────────────────────────────────────────────────
@app.post("/api/auth/signup")
def signup(req: SignupRequest):
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if db.email_exists(req.email):
        raise HTTPException(status_code=409, detail="Email already exists")
    
    user_id = str(uuid.uuid4())
    db.create_user(
        user_id=user_id, 
        name=req.name.strip(), 
        email=req.email, 
        password=req.password,
        terms_accepted=req.terms_accepted
    )
    
    return {
        "user_id": user_id, 
        "name": req.name.strip(), 
        "email": req.email.lower(),
        "terms_accepted": req.terms_accepted,
        "is_admin": False
    }

@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    user = db.get_user_by_email(req.email)
    if not user or not db.verify_password(req.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session["user_id"] = user["user_id"]
    is_admin = user.get("is_admin", 0) == 1
    if is_admin:
        request.session["is_admin"] = True
        request.session["admin_verified"] = True
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "is_admin": is_admin,
        "terms_accepted": bool(user.get("terms_accepted", 0))
    }

@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "logged out"}

# ─── Google OAuth ──────────────────────────────────────────────────────
@app.get("/api/auth/google")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/auth/google/callback")
async def google_auth(request: Request):
    """
    Google OAuth callback handler.
    Uses userinfo endpoint as fallback when id_token is not available.
    """
    try:
        # Get the token from the request
        token = await oauth.google.authorize_access_token(request)
        
        # Debug: log token keys
        print(f"Token keys: {list(token.keys()) if token else 'No token'}")
        
        # Try to get user info from id_token first
        user_info = None
        
        if 'id_token' in token:
            try:
                user_info = await oauth.google.parse_id_token(request, token)
                print(f"Got user info from id_token: {user_info.get('email') if user_info else 'None'}")
            except Exception as e:
                print(f"Failed to parse id_token: {e}")
                user_info = None
        
        # If no id_token or parsing failed, use userinfo endpoint
        if not user_info:
            access_token = token.get('access_token')
            if not access_token:
                raise HTTPException(status_code=400, detail="No access token received")
            
            print(f"Using userinfo endpoint with access token")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://openidconnect.googleapis.com/v1/userinfo',
                    headers={'Authorization': f'Bearer {access_token}'}
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        print(f"Userinfo error: {resp.status} - {error_text}")
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Failed to get user info: {resp.status}"
                        )
                    user_info = await resp.json()
                    print(f"Got user info from userinfo: {user_info.get('email') if user_info else 'None'}")
        
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user information")
        
        email = user_info.get('email')
        if not email:
            raise HTTPException(status_code=400, detail="No email provided by Google")
        
        name = user_info.get('name', email.split('@')[0])
        # Handle Google accounts with no name
        if not name or name.strip() == '':
            name = email.split('@')[0]
        
        # Check if user exists
        user = db.get_user_by_email(email)
        if not user:
            # Create new user
            user_id = str(uuid.uuid4())
            temp_pw = secrets.token_urlsafe(16)
            db.create_user(
                user_id=user_id, 
                name=name, 
                email=email, 
                password=temp_pw, 
                terms_accepted=True
            )
            print(f"Created new user: {email}")
        else:
            user_id = user['user_id']
            print(f"Existing user: {email}")
        
        # Return HTML with user data
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Authentication Complete</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #0F0A2A;
                    color: #F0EEFF;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                    background: rgba(255,255,255,0.05);
                    border-radius: 16px;
                    border: 1px solid rgba(255,255,255,0.1);
                    max-width: 400px;
                    width: 100%;
                }}
                .spinner {{
                    width: 40px;
                    height: 40px;
                    border: 3px solid rgba(255,255,255,0.1);
                    border-top-color: #54E6F2;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    to {{ transform: rotate(360deg); }}
                }}
                .success {{
                    color: #4ADE80;
                    font-size: 2.5rem;
                    margin-bottom: 10px;
                }}
                h2 {{
                    font-weight: 600;
                    margin: 0 0 8px 0;
                }}
                p {{
                    color: #B8B0D8;
                    margin: 8px 0;
                }}
                .sub {{
                    color: #7A6F9A;
                    font-size: 0.8rem;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✅</div>
                <h2>Authentication Successful!</h2>
                <p>Welcome, {name}!</p>
                <div class="spinner"></div>
                <p>Redirecting to chat...</p>
                <p class="sub">You will be redirected automatically.</p>
            </div>
            <script>
                // Store user data in localStorage
                const userData = {{
                    user_id: '{user_id}',
                    name: '{name.replace("'", "\\'")}',
                    email: '{email}',
                    terms_accepted: true,
                    is_oauth: true
                }};
                localStorage.setItem('neurosupport_user', JSON.stringify(userData));
                localStorage.setItem('ava-terms-accepted', 'true');
                localStorage.setItem('ava-terms-accepted-date', new Date().toISOString());
                
                // Redirect after a short delay
                setTimeout(() => {{
                    window.location.href = '/chat.html';
                }}, 1500);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
        
    except OAuthError as e:
        print(f"OAuth Error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")
    except KeyError as e:
        print(f"KeyError: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Missing expected field: {str(e)}")
    except aiohttp.ClientError as e:
        print(f"HTTP Client Error: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Failed to contact Google: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in google_auth: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

# ─── Admin auth ──────────────────────────────────────────────────────
@app.post("/api/auth/admin-verify")
async def admin_verify(request: Request, payload: dict):
    password = payload.get("admin_password")
    if not password:
        raise HTTPException(status_code=400, detail="Missing admin_password")
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin password not configured")
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    request.session["is_admin"] = True
    request.session["admin_verified"] = True
    return {"status": "ok"}

@app.get("/api/auth/admin-status")
async def admin_status(request: Request):
    return {
        "is_admin": bool(request.session.get("is_admin")),
        "admin_verified": bool(request.session.get("admin_verified"))
    }

@app.post("/api/auth/admin-logout")
async def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    request.session.pop("admin_verified", None)
    return {"status": "ok"}

# ─── Image vision via Groq ─────────────────────────────────────────────────────
def call_llm_with_vision(user_message: str, image_base64: str, image_mime: str = "image/jpeg",
                          system_prompt: str = "", file_context: str = "") -> str:
    import os as _os, requests as _req
    api_key = _os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return "[Vision requires GROQ_API_KEY to be set]"
    content_parts = []
    if file_context:
        content_parts.append({"type": "text", "text": f"[Attached document:]\n{file_context[:6000]}\n\n"})
    content_parts.append({"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_base64}"}})
    content_parts.append({"type": "text", "text": user_message or "Describe and analyse this image in detail."})
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content_parts})
    payload = {"model": "meta-llama/llama-4-scout-17b-16e-instruct", "messages": messages, "max_tokens": 1500, "temperature": 0.5}
    try:
        r = _req.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                      json=payload, timeout=45)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        return f"[Vision API error {r.status_code}: {r.text[:200]}]"
    except Exception as e:
        return f"[Vision error: {str(e)}]"

# ─── Chat (non‑streaming) ──────────────────────────────────────────────
@app.post("/api/chat")
def chat(req: ChatRequest):
    # Debug: log the received mode
    print(f"🔍 [Non-streaming] Received mode: {req.mode}")

    # ─── Memory storage command ──────────────────────────────────────────────
    memory_code_match = re.match(r"^Remember this code:\s*(.+)$", req.message, re.IGNORECASE)
    if memory_code_match:
        code = memory_code_match.group(1).strip()
        response_text = f"Got it. I'll remember the code {code} for this conversation."
        message_id = str(uuid.uuid4())
        session_id = req.session_id or str(uuid.uuid4())
        if not req.session_id:
            db.create_session(session_id, req.user_id, title=req.message[:50])
        db.save_message(
            message_id=message_id,
            session_id=session_id,
            user_id=req.user_id,
            user_message=req.message,
            agent_response=response_text,
            intent="memory_storage",
            sentiment={"label": "neutral", "score": 0.5},
            frustration=0.0,
            latency_ms=0,
        )
        memory.maybe_refresh_user_memory(req.user_id, session_id, req.message, response_text)
        return {
            "response": response_text,
            "message_id": message_id,
            "session_id": session_id,
            "metadata": {"intent": "memory_storage", "sentiment": {"label": "neutral"}, "frustration_score": 0.0}
        }

    prefs = db.get_user_preferences(req.user_id)
    custom_instructions = prefs.get("custom_instructions", "")
    personality = prefs.get("personality", "friendly")

    # Build memory context without cross-session conversation bleed.
    # Session history is scoped to the active chat and summarized by memory.py;
    # durable user facts are stored separately and intentionally carried across chats.
    session_context = memory.get_session_context(req.user_id, req.session_id) if req.session_id else ""
    user_memory_context = memory.get_user_memory_context(req.user_id)
    context = "\n".join(
        part.strip()
        for part in (user_memory_context, session_context)
        if part and part.strip()
    )

    sentiment = sentiment_analyzer.analyze(req.message)
    intent = intent_classifier.classify(req.message)
    frustration = frustration_detector.score(req.user_id, req.message)

    failed = db.get_failed_solutions(req.user_id)
    failed_note = "Previously attempted solutions that didn't work: " + "; ".join(failed) if failed else ""

    translation_langs = _detect_translation(req.message)
    support_flag = is_support_issue(req.message, intent)

    file_context = req.file_context or ""
    if req.doc_id and not file_context:
        try:
            doc = db.get_document(req.doc_id)
            if doc: file_context = doc.get("extracted_text", "")[:8000]
        except Exception: pass

    from llm import build_system_prompt as _bsp
    _base = _bsp(custom_instructions, personality, req.mode or "flash")
    print(f"🔍 [Non-streaming] Using mode for system prompt: {req.mode or 'flash'}")

    system_override, aug_meta = powers.build_augmented_system_prompt(
        base_prompt=_base,
        user_message=req.message,
        conversation_context=context,
        file_context=file_context,
        failed_note=failed_note,
        sentiment_label=sentiment["label"],
        frustration=frustration,
        translation_langs=translation_langs,
        support_flag=support_flag,
        web_search_enabled=getattr(req, "web_search", False),
    )

    # DeepL translation path
    if translation_langs and translation_langs.get("tgt"):
        text_to_translate = powers.extract_text_to_translate(req.message)
        if text_to_translate:
            deepl_result = powers.translate_deepl(
                text_to_translate,
                target_lang_name=translation_langs["tgt"],
                source_lang_name=translation_langs.get("src", "auto"),
            )
            if deepl_result:
                response = f"{deepl_result['translated']}\n\n*Translated from {deepl_result['source_lang']} → {deepl_result['target_lang']} via DeepL*"
                aug_meta["deepl_used"] = True
                message_id = str(uuid.uuid4())
                session_id = req.session_id or str(uuid.uuid4())
                if not req.session_id:
                    db.create_session(session_id, req.user_id, title=req.message[:50])
                db.save_message(message_id=message_id, session_id=session_id, user_id=req.user_id,
                    user_message=req.message, agent_response=response, intent=intent,
                    sentiment=sentiment, frustration=frustration, latency_ms=0)
                memory.maybe_refresh_user_memory(req.user_id, session_id, req.message, response)
                return {"response": response, "message_id": message_id, "session_id": session_id,
                    "metadata": {"intent": intent, "sentiment": sentiment, "frustration_score": frustration}}

    start_time = time.time()
    try:
        if req.image_base64:
            response = call_llm_with_vision(
                req.message, req.image_base64, req.image_mime or "image/jpeg",
                system_prompt=system_override, file_context=file_context
            )
        else:
            response = call_llm_with_constraints(
                req.message,
                base_system_prompt=system_override,
                custom_instructions=custom_instructions,
                personality=personality,
                max_tokens=1200,
                mode=req.mode or "flash",
            )
    except Exception as e:
        response = f"I'm sorry, I encountered an error: {str(e)}"

    latency_ms = int((time.time() - start_time) * 1000)
    message_id = str(uuid.uuid4())
    session_id = req.session_id or str(uuid.uuid4())
    if not req.session_id:
        db.create_session(session_id, req.user_id, title=req.message[:50])
    db.save_message(message_id=message_id, session_id=session_id, user_id=req.user_id,
        user_message=req.message, agent_response=response, intent=intent,
        sentiment=sentiment, frustration=frustration, latency_ms=latency_ms)
    memory.maybe_refresh_user_memory(req.user_id, session_id, req.message, response)

    return {"response": response, "message_id": message_id, "session_id": session_id,
        "metadata": {"intent": intent, "sentiment": sentiment, "frustration_score": frustration,
                     "searched": aug_meta.get("searched", False)}}

# ─── Chat streaming ─────────────────────────────────────────────────────
@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    # Debug: log the received mode
    print(f"🔍 [Streaming] Received mode: {req.mode}")

    def generate():
        # ─── Memory storage command ──────────────────────────────────────────────
        memory_code_match = re.match(r"^Remember this code:\s*(.+)$", req.message, re.IGNORECASE)
        if memory_code_match:
            code = memory_code_match.group(1).strip()
            response_text = f"Got it. I'll remember the code {code} for this conversation."
            yield f"data: {json.dumps({'chunk': response_text})}\n\n"
            latency_ms = 0
            message_id = str(uuid.uuid4())
            session_id = req.session_id or str(uuid.uuid4())
            if not req.session_id:
                db.create_session(session_id, req.user_id, title=req.message[:50])
            db.save_message(
                message_id=message_id,
                session_id=session_id,
                user_id=req.user_id,
                user_message=req.message,
                agent_response=response_text,
                intent="memory_storage",
                sentiment={"label": "neutral", "score": 0.5},
                frustration=0.0,
                latency_ms=latency_ms,
            )
            memory.maybe_refresh_user_memory(req.user_id, session_id, req.message, response_text)
            yield f"data: {json.dumps({'done': True, 'message_id': message_id, 'session_id': session_id, 'metadata': {'intent': 'memory_storage', 'sentiment': {'label': 'neutral'}, 'frustration_score': 0.0}})}\n\n"
            return

        prefs = db.get_user_preferences(req.user_id)
        custom_instructions = prefs.get("custom_instructions", "")
        personality = prefs.get("personality", "friendly")

        # Build memory context without cross-session conversation bleed.
        # Session history is scoped to the active chat and summarized by memory.py;
        # durable user facts are stored separately and intentionally carried across chats.
        session_context = memory.get_session_context(req.user_id, req.session_id) if req.session_id else ""
        user_memory_context = memory.get_user_memory_context(req.user_id)
        context = "\n".join(
            part.strip()
            for part in (user_memory_context, session_context)
            if part and part.strip()
        )

        sentiment = sentiment_analyzer.analyze(req.message)
        intent = intent_classifier.classify(req.message)
        frustration = frustration_detector.score(req.user_id, req.message)

        failed = db.get_failed_solutions(req.user_id)
        failed_note = "Previously attempted solutions that didn't work: " + "; ".join(failed) if failed else ""

        translation_langs = _detect_translation(req.message)
        support_flag = is_support_issue(req.message, intent)

        file_context = req.file_context or ""
        if req.doc_id and not file_context:
            try:
                doc = db.get_document(req.doc_id)
                if doc: file_context = doc.get("extracted_text", "")[:8000]
            except Exception: pass

        from llm import build_system_prompt as _bsp
        _base = _bsp(custom_instructions, personality, req.mode or "flash")
        print(f"🔍 [Streaming] Using mode for system prompt: {req.mode or 'flash'}")

        system_override, aug_meta = powers.build_augmented_system_prompt(
            base_prompt=_base,
            user_message=req.message,
            conversation_context=context,
            file_context=file_context,
            failed_note=failed_note,
            sentiment_label=sentiment["label"],
            frustration=frustration,
            translation_langs=translation_langs,
            support_flag=support_flag,
            web_search_enabled=getattr(req, "web_search", False),
        )

        if aug_meta.get("searched"):
            yield f"data: {json.dumps({'status': '🔍 Searching the web…', 'searching': True})}\n\n"

        start_time = time.time()
        full_response = ""

        run_cmd = powers.detect_run_command(req.message)
        if run_cmd:
            _run_lang = run_cmd["lang"]
            _run_status = json.dumps({"status": f"⚙️ Running {_run_lang} code…"})
            yield f"data: {_run_status}\n\n"
            result = powers.execute_code(run_cmd["lang"], run_cmd["code"])
            full_response = powers.format_execution_result(run_cmd["lang"], run_cmd["code"], result)
            yield f"data: {json.dumps({'chunk': full_response})}\n\n"

        elif translation_langs and translation_langs.get("tgt"):
            text_to_translate = powers.extract_text_to_translate(req.message)
            if text_to_translate:
                yield f"data: {json.dumps({'status': '🌐 Translating…'})}\n\n"
                deepl_result = powers.translate_deepl(
                    text_to_translate,
                    target_lang_name=translation_langs["tgt"],
                    source_lang_name=translation_langs.get("src", "auto"),
                )
                if deepl_result:
                    full_response = f"{deepl_result['translated']}\n\n*Translated from {deepl_result['source_lang']} → {deepl_result['target_lang']} via DeepL*"
                    aug_meta["deepl_used"] = True
                    yield f"data: {json.dumps({'chunk': full_response})}\n\n"
                else:
                    pass

            if not full_response:
                stream = call_llm_streaming(
                    req.message,
                    custom_instructions=custom_instructions,
                    personality=personality,
                    system_prompt_override=system_override,
                    mode=req.mode or "flash"
                )
                for chunk in stream:
                    full_response += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        elif req.image_base64:
            vision_resp = call_llm_with_vision(
                req.message, req.image_base64, req.image_mime or "image/jpeg",
                system_prompt=system_override, file_context=file_context
            )
            full_response = vision_resp
            yield f"data: {json.dumps({'chunk': vision_resp})}\n\n"

        else:
            from llm import _detect_word_count_constraint
            word_target = _detect_word_count_constraint(req.message)
            if word_target is not None:
                constrained_resp = call_llm_with_constraints(
                    req.message,
                    base_system_prompt=system_override,
                    custom_instructions=custom_instructions,
                    personality=personality,
                    max_tokens=1200,
                    mode=req.mode or "flash",
                )
                full_response = constrained_resp
                yield f"data: {json.dumps({'chunk': constrained_resp})}\n\n"
            else:
                try:
                    stream = call_llm_streaming(
                        req.message,
                        custom_instructions=custom_instructions,
                        personality=personality,
                        system_prompt_override=system_override,
                        mode=req.mode or "flash"
                    )
                    for chunk in stream:
                        full_response += chunk
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                except Exception as e:
                    full_response = f"I encountered an error: {str(e)}"
                    yield f"data: {json.dumps({'chunk': full_response})}\n\n"

        latency_ms = int((time.time() - start_time) * 1000)
        message_id = str(uuid.uuid4())
        session_id = req.session_id or str(uuid.uuid4())
        if not req.session_id:
            db.create_session(session_id, req.user_id, title=req.message[:50])
        db.save_message(
            message_id=message_id,
            session_id=session_id,
            user_id=req.user_id,
            user_message=req.message,
            agent_response=full_response,
            intent=intent,
            sentiment=sentiment,
            frustration=frustration,
            latency_ms=latency_ms
        )
        memory.maybe_refresh_user_memory(req.user_id, session_id, req.message, full_response)

        yield f"data: {json.dumps({'done': True, 'message_id': message_id, 'session_id': session_id, 'metadata': {'intent': intent, 'sentiment': sentiment, 'frustration_score': frustration, 'searched': aug_meta.get('searched', False), 'deepl_used': aug_meta.get('deepl_used', False)}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# ─── Voice transcription ─────────────────────────────────────────────────
@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not set")
    audio_bytes = await audio.read()
    if len(audio_bytes) < 1000:
        raise HTTPException(status_code=400, detail="Audio too short")
    content_type = audio.content_type or "audio/webm"
    ext = "webm" if "webm" in content_type else "ogg" if "ogg" in content_type else "m4a" if "m4a" in content_type else "webm"
    filename = f"recording.{ext}"
    try:
        import requests as _req
        response = _req.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, content_type)},
            data={"model": "whisper-large-v3", "response_format": "json", "language": "en"},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            return {"text": data.get("text", "").strip()}
        else:
            raise HTTPException(status_code=response.status_code, detail=f"Groq Whisper error: {response.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

# ─── Code execution ─────────────────────────────────────────────────────
class RunRequest(BaseModel):
    lang: str = "python"
    code: str
    stdin: str = ""

@app.post("/api/run")
def run_code(req: RunRequest):
    result = powers.execute_code(req.lang, req.code, req.stdin)
    formatted = powers.format_execution_result(req.lang, req.code, result)
    return {"output": formatted, "raw": result}

# ─── Suggestions ──────────────────────────────────────────────────────
@app.post("/api/suggestions")
def get_suggestions(req: SuggestionRequest):
    past = db.get_similar_past_queries(req.user_id, req.current_input)
    return {"suggestions": past}

# ─── PPT ──────────────────────────────────────────────────────────────
@app.post("/api/generate-ppt")
async def generate_ppt(req: PPTRequest):
    if not PPT_AVAILABLE:
        raise HTTPException(status_code=501, detail="python-pptx not installed")
    prompt = f"Generate exactly {req.slides} slides for a presentation about \"{req.topic}\". Return ONLY a JSON array of objects with keys: \"title\", \"content\". Example: [{{\"title\": \"Intro\", \"content\": \"...\"}}]"
    try:
        llm_resp = call_llm(prompt, mode="flash")
        start = llm_resp.find('[')
        end = llm_resp.rfind(']') + 1
        if start == -1 or end == 0:
            slides_data = [{"title": req.topic, "content": llm_resp[:200]}]
        else:
            slides_data = json.loads(llm_resp[start:end])
    except:
        slides_data = [{"title": req.topic, "content": f"Presentation about {req.topic}"}]
    prs = Presentation()
    for slide in slides_data[:req.slides]:
        slide_layout = prs.slide_layouts[1]
        s = prs.slides.add_slide(slide_layout)
        s.shapes.title.text = slide.get("title", "Slide")
        s.placeholders[1].text = slide.get("content", "")
    ppt_bytes = BytesIO()
    prs.save(ppt_bytes)
    ppt_bytes.seek(0)
    return FileResponse(ppt_bytes, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        filename=f"{req.topic.replace(' ', '_')}.pptx")

# ─── Image Generation ─────────────────────────────────────────────────
@app.post("/api/generate-image")
async def generate_image(req: ImageRequest):
    if not REPLICATE_AVAILABLE or not os.getenv("REPLICATE_API_KEY"):
        return {"image_url": "https://placekitten.com/512/512", "mock": True}
    try:
        output = replicate.run(
            "stability-ai/stable-diffusion:db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",
            input={"prompt": req.prompt, "width": 512, "height": 512}
        )
        url = output[0] if isinstance(output, list) else output
        return {"image_url": url, "mock": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Feedback ─────────────────────────────────────────────────────────
@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    db.save_feedback(req.user_id, req.session_id, req.message_id, req.helpful)
    if not req.helpful:
        sol = db.get_last_agent_response(req.user_id, req.session_id)
        if sol:
            db.save_failed_solution(req.user_id, req.session_id, sol)
    return {"status": "recorded"}

# ─── Sessions ─────────────────────────────────────────────────────────
@app.get("/api/sessions/{user_id}")
def list_sessions(user_id: str):
    return {"sessions": db.get_sessions_for_user(user_id)}

@app.get("/api/sessions/{user_id}/{session_id}/messages")
def session_messages(user_id: str, session_id: str):
    return {"messages": db.get_session_messages(session_id)}

@app.delete("/api/sessions/{user_id}/{session_id}")
def delete_session(user_id: str, session_id: str):
    deleted = db.delete_session(user_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}

@app.put("/api/sessions/{user_id}/{session_id}/rename")
def rename_session(user_id: str, session_id: str, req: RenameRequest):
    success = db.update_session_title(user_id, session_id, req.new_title.strip())
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "updated"}

@app.post("/api/sessions/{user_id}/{session_id}/pin")
def pin_session(user_id: str, session_id: str, pinned: bool):
    db.set_pin(user_id, session_id, pinned)
    return {"status": "ok"}

@app.get("/api/search/{user_id}")
def search_sessions(user_id: str, q: str):
    return {"sessions": db.search_sessions(user_id, q)}

# ─── User Preferences ──────────────────────────────────────────────────
@app.get("/api/user/preferences/{user_id}")
def get_preferences(user_id: str):
    prefs = db.get_user_preferences(user_id)
    if not prefs:
        prefs = {"custom_instructions": "", "personality": "friendly", "theme": "light"}
    return prefs

@app.put("/api/user/preferences/{user_id}")
def update_preferences(user_id: str, req: PreferencesUpdate):
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    db.update_user_preferences(user_id, update_data)
    return {"status": "updated"}

# ─── Password Change ───────────────────────────────────────────────────
@app.put("/api/user/password/{user_id}")
def change_password(user_id: str, req: ChangePasswordRequest):
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not db.verify_password(req.current_password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    db.update_password(user_id, req.new_password)
    return {"status": "updated"}

# ─── Terms Acceptance ───────────────────────────────────────────────────
@app.get("/api/user/terms/{user_id}")
def get_terms_status(user_id: str):
    """Check if a user has accepted the terms and privacy policy."""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "terms_accepted": bool(user.get("terms_accepted", 0)),
        "terms_accepted_date": user.get("terms_accepted_date")
    }

@app.put("/api/user/terms/{user_id}")
def update_terms_acceptance(user_id: str, req: TermsAcceptRequest):
    """Update terms acceptance status for a user."""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.update_terms_acceptance(user_id, req.terms_accepted)
    
    return {
        "terms_accepted": req.terms_accepted,
        "terms_accepted_date": datetime.now(timezone.utc).isoformat() if req.terms_accepted else None
    }

# ─── Document Upload ──────────────────────────────────────────────────
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload-document")
async def upload_document(
    user_id: str = Form(...),
    file: UploadFile = File(...)
):
    doc_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1].lower()
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}{file_ext}")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    text = ""
    if file_ext == ".pdf":
        try:
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
        except Exception as e:
            text = f"[PDF extraction error: {str(e)}]"
    elif file_ext == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            text = f"[DOCX extraction error: {str(e)}]"
    elif file_ext in [".xlsx", ".xls"]:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True)
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values=True):
                    text += " ".join(str(cell) for cell in row if cell) + "\n"
        except Exception as e:
            text = f"[Excel extraction error: {str(e)}]"
    elif file_ext == ".pptx":
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
        except Exception as e:
            text = f"[PPTX extraction error: {str(e)}]"
    elif file_ext in [".csv", ".tsv"]:
        try:
            import csv as csv_module
            delimiter = "\t" if file_ext == ".tsv" else ","
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv_module.reader(f, delimiter=delimiter)
                rows = list(reader)
            if rows:
                headers = rows[0]
                data_rows = rows[1:]
                row_count = len(data_rows)
                col_count = len(headers)
                text = f"[CSV DATA — {row_count} rows × {col_count} columns]\n"
                text += f"Columns: {', '.join(headers)}\n\n"
                preview_rows = data_rows[:200]
                text += "\n".join([",".join(r) for r in [headers] + preview_rows])
                if row_count > 200:
                    text += f"\n\n[... {row_count - 200} more rows not shown. Total rows: {row_count}]"
        except Exception as e:
            text = f"[CSV extraction error: {str(e)}]"
    elif file_ext in [".txt", ".md", ".log"]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()[:50000]
        except Exception as e:
            text = f"[Text extraction error: {str(e)}]"

    db.save_document(doc_id, user_id, file.filename, file_path, text)
    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "text_preview": text[:300]
    }

# ─── Share ────────────────────────────────────────────────────────────
@app.get("/api/share/{session_id}")
def get_share_link(session_id: str, user_id: str):
    token = db.get_or_create_share_token(session_id, user_id)
    return {"share_url": f"/share/{token}"}

@app.get("/share/{token}")
async def view_shared_chat(token: str):
    data = db.get_shared_session_data(token)
    if not data:
        raise HTTPException(status_code=404, detail="Share link invalid or expired")
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Shared Chat - Ava AI</title>
    <style>body{{font-family:Inter,sans-serif;background:#f5f4ff;padding:20px;max-width:760px;margin:40px auto;color:#1d1230;}}
    .bubble{{padding:12px 18px;border-radius:18px;margin-bottom:12px;line-height:1.6;}}
    .user{{background:#e3cdfb;border-radius:18px 18px 4px 18px;}}
    .ava{{background:#ffffff;border:1px solid #ece2fb;border-radius:18px 18px 18px 4px;}}
    .meta{{font-size:0.8rem;color:#9a8db8;margin-top:6px;}}
    </style>
    </head>
    <body>
    <h1 style="font-family:Sora,sans-serif;">Shared Conversation</h1>
    <div id="messages">
    """
    for msg in data:
        html += f"""
        <div class="bubble user"><strong>User:</strong> {msg['user_message']}</div>
        <div class="bubble ava"><strong>Ava:</strong> {msg['agent_response']}</div>
        <div class="meta">Sentiment: {msg.get('sentiment_label','N/A')} • Intent: {msg.get('intent','N/A')}</div>
        """
    html += "</div></body></html>"
    return HTMLResponse(content=html)

@app.get("/api/share-data")
def share_data(token: str):
    data = db.get_shared_session_data(token)
    if not data:
        raise HTTPException(status_code=404, detail="Invalid share link")
    return data

# ─── Export ────────────────────────────────────────────────────────────
@app.get("/api/export/{user_id}")
def export_data(user_id: str):
    user = db.get_user_by_id(user_id)
    sessions = db.get_sessions_for_user(user_id)
    messages = db.get_all_messages(user_id)
    feedback = db.get_feedback(user_id)
    docs = db.get_user_documents(user_id)
    data = {
        "user": user,
        "sessions": sessions,
        "messages": messages,
        "feedback": feedback,
        "documents": docs
    }
    json_str = json.dumps(data, indent=2, default=str)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("ava_export.json", json_str)
    zip_buffer.seek(0)
    return FileResponse(zip_buffer, media_type="application/zip", filename="ava_export.zip")

# ─── Web Search ────────────────────────────────────────────────────────
@app.get("/api/web-search")
def web_search(query: str):
    results = search.web_search(query)
    return {"results": results}

# ─── Memory ───────────────────────────────────────────────────────────
@app.get("/api/memory/{user_id}")
def get_memory(user_id: str):
    stats = db.get_user_stats(user_id)
    recent = db.get_recent_messages(user_id, limit=5)
    user_mem = db.get_user_memory(user_id)
    return {"stats": stats, "recent": recent, "remembered_facts": user_mem["memory_text"]}

@app.delete("/api/memory/{user_id}")
def clear_memory(user_id: str):
    db.delete_user_data(user_id)
    return {"message": "Data cleared"}

# ─── Cross-session user memory ──────────────────────────────────────
@app.get("/api/user-memory/{user_id}")
def get_user_memory(user_id: str):
    return db.get_user_memory(user_id)

@app.delete("/api/user-memory/{user_id}")
def clear_user_memory(user_id: str):
    db.clear_user_memory(user_id)
    return {"status": "cleared"}

# ─── Reviews ──────────────────────────────────────────────────────────
REVIEW_IMAGE_DIR = "review_images"
os.makedirs(REVIEW_IMAGE_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

@app.post("/api/reviews")
async def submit_review(payload: dict):
    try:
        rating = payload.get("rating")
        comment = payload.get("comment", "")
        user_id = payload.get("user_id")

        if rating is None or rating < 1 or rating > 5:
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

        reviewer_name = "Guest"
        if user_id:
            user = db.get_user_by_id(user_id)
            if user:
                reviewer_name = user["name"]

        review_id = str(uuid.uuid4())
        db.create_review(
            review_id=review_id,
            reviewer_name=reviewer_name,
            reviewer_title=None,
            rating=rating,
            review_text=comment,
            image_path=None
        )
        return {"review_id": review_id, "status": "submitted"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Review submission error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _serialize_review_for_public(r: dict) -> dict:
    return {
        "rating": r["rating"],
        "comment": r["review_text"] or "",
        "user_id": r["reviewer_name"] or "Guest",
        "created_at": r["created_at"]
    }

@app.get("/api/reviews")
def list_public_reviews():
    reviews = db.get_public_reviews()
    return [_serialize_review_for_public(r) for r in reviews]

@app.get("/api/reviews/public")
def public_reviews_alias():
    return list_public_reviews()

# ─── Admin review endpoints ─────────────────────────────────────────
@app.get("/api/admin/reviews")
def admin_list_reviews(request: Request):
    require_admin(request)
    reviews = db.get_all_reviews()
    result = []
    for r in reviews:
        result.append({
            "id": r["review_id"],
            "rating": r["rating"],
            "comment": r["review_text"] or "",
            "user_id": r["reviewer_name"] or "Guest",
            "created_at": r["created_at"],
            "status": r["status"],
            "featured": bool(r["featured"]),
            "reviewer_name": r["reviewer_name"],
            "review_text": r["review_text"] or ""
        })
    return {"reviews": result}

class ReviewStatusUpdate(BaseModel):
    status: str

@app.patch("/api/admin/reviews/{review_id}/status")
def admin_update_review_status(review_id: str, req: ReviewStatusUpdate, request: Request):
    require_admin(request)
    if req.status not in ("approved", "hidden", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if not db.get_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found")
    db.update_review_status(review_id, req.status)
    return {"status": "updated"}

class ReviewFeaturedUpdate(BaseModel):
    featured: bool

@app.patch("/api/admin/reviews/{review_id}/featured")
def admin_update_review_featured(review_id: str, req: ReviewFeaturedUpdate, request: Request):
    require_admin(request)
    if not db.get_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found")
    db.set_review_featured(review_id, req.featured)
    return {"status": "updated"}

@app.delete("/api/admin/reviews/{review_id}")
def admin_delete_review(review_id: str, request: Request):
    require_admin(request)
    review = db.delete_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.get("image_path") and os.path.exists(review["image_path"]):
        try:
            os.remove(review["image_path"])
        except OSError:
            pass
    return {"status": "deleted"}

# ─── Analytics ────────────────────────────────────────────────────────
@app.get("/api/analytics")
def analytics():
    return db.get_global_analytics()

@app.get("/api/analytics/{user_id}")
def user_analytics(user_id: str):
    return db.get_user_stats(user_id)

# ─── Static ───────────────────────────────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# ─── Cache-busting route for admin.html ──────────────────────────────
@app.get("/admin.html")
async def admin_page():
    return FileResponse(
        os.path.join(STATIC_DIR, "admin.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )