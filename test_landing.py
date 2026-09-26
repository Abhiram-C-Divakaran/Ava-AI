import os
import unittest
import re
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class SimpleDOMParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        self.tags.append((tag, attr_dict))
        if "id" in attr_dict:
            self.ids.add(attr_dict["id"])
        if tag == "a" and "href" in attr_dict:
            self.links.append(attr_dict["href"])
        if tag == "img" and "src" in attr_dict:
            self.images.append(attr_dict["src"])


class TestLandingPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_path = os.path.join(BASE_DIR, "index.html")
        cls.css_path = os.path.join(BASE_DIR, "assets", "landing", "landing.css")
        cls.js_path = os.path.join(BASE_DIR, "assets", "landing", "landing.js")
        cls.favicon_path = os.path.join(BASE_DIR, "assets", "landing", "favicon.svg")

        with open(cls.index_path, "r", encoding="utf-8") as f:
            cls.index_html = f.read()

        with open(cls.js_path, "r", encoding="utf-8") as f:
            cls.landing_js = f.read()

        with open(cls.css_path, "r", encoding="utf-8") as f:
            cls.landing_css = f.read()

        cls.parser = SimpleDOMParser()
        cls.parser.feed(cls.index_html)

    def test_01_assets_exist(self):
        """Verify all landing page core asset files exist on disk."""
        self.assertTrue(os.path.exists(self.index_path))
        self.assertTrue(os.path.exists(self.css_path))
        self.assertTrue(os.path.exists(self.js_path))
        self.assertTrue(os.path.exists(self.favicon_path))
        hero_robot = os.path.join(
            BASE_DIR,
            "cute-ai-robot-chatbot-reading-a-book-on-transparent-background-free-png.webp"
        )
        faq_robot = os.path.join(BASE_DIR, "pngegg.png")
        self.assertTrue(os.path.exists(hero_robot))
        self.assertTrue(os.path.exists(faq_robot))

    def test_02_no_v3_branding(self):
        """Ensure obsolete v3.0 branding is absent and v1.0.1 is used."""
        self.assertNotIn("v3.0", self.index_html)
        self.assertIn("v1.0.1", self.index_html)

    def test_03_no_pricing_link_in_navigation(self):
        """Verify pricing page is not implied in navigation."""
        nav_match = re.search(r'<div class="nav-links"[^>]*>(.*?)</div>', self.index_html, re.DOTALL)
        self.assertIsNotNone(nav_match)
        nav_html = nav_match.group(1)
        self.assertNotIn("Pricing", nav_html)
        self.assertNotIn("#pricing", nav_html)

    def test_04_required_section_ids_exist(self):
        """Verify all required landmarks and IDs are present in the DOM."""
        required_ids = [
            "main",
            "nav-links",
            "theme-toggle",
            "menu-toggle",
            "hero-heading",
            "watch-demo",
            "features",
            "feature-grid",
            "how-it-works",
            "solutions",
            "demo-panel",
            "demo-question",
            "demo-intro",
            "demo-checklist",
            "demo-followup",
            "demo-more",
            "stats",
            "testimonials",
            "faq",
            "faq-list",
            "get-started",
            "chat-launcher",
            "chat-drawer",
            "chat-status",
            "chat-history",
            "chat-auth",
            "chat-form",
            "chat-input",
            "chat-send",
            "chat-minimize",
            "chat-close",
            "demo-dialog",
            "explore-demo"
        ]
        for req_id in required_ids:
            self.assertIn(req_id, self.parser.ids, f"Missing required element ID: {req_id}")

    def test_05_hero_copy_exactness(self):
        """Verify exact hero heading, description, trust points, and CTAs."""
        self.assertIn("A KINDER TOMORROW WITH AI", self.index_html)
        self.assertIn("Your Personal", self.index_html)
        self.assertIn('<span class="gradient-text">Intelligence</span>', self.index_html)
        self.assertIn("Platform", self.index_html)
        self.assertIn("Ava understands context, remembers your preferences, and adapts to how you work", self.index_html)
        self.assertIn("No credit card required", self.index_html)
        self.assertIn("Personalized AI", self.index_html)
        self.assertIn("Privacy-focused", self.index_html)

    def test_06_features_structure(self):
        """Verify 6 features matching real capabilities are configured."""
        feature_names = [
            "Understand Context",
            "Remember Preferences",
            "Real-time Assistance",
            "Personalized Replies",
            "Multi-session Memory",
            "Private & Secure"
        ]
        for name in feature_names:
            self.assertIn(name, self.landing_js)

    def test_07_how_it_works_steps(self):
        """Verify How AvaAI Works has the 3 exact connected steps."""
        self.assertIn("Create Your Account", self.index_html)
        self.assertIn("Sign up securely in seconds.", self.index_html)
        self.assertIn("Talk Naturally", self.index_html)
        self.assertIn("Use Ava normally. Explicit preferences and useful factual memory can be learned over time.", self.index_html)
        self.assertIn("Ava Adapts", self.index_html)
        self.assertIn("Ava uses persistent memory and feedback-driven behavioral policies to improve how it responds.", self.index_html)

    def test_08_see_in_action_content(self):
        """Verify product demo mockup conversation elements."""
        self.assertIn("Help me plan a productive week.", self.index_html)
        self.assertIn("Focus on deep work during your strongest hours", self.landing_js)
        self.assertIn("Schedule exercise and recovery breaks", self.landing_js)
        self.assertIn("Reserve time for creative projects", self.landing_js)
        self.assertIn("Review the week before planning the next one", self.landing_js)
        self.assertIn("Would you like me to break this into a daily schedule?", self.landing_js)
        self.assertIn("Yes, please", self.index_html)
        self.assertIn("Show me another approach", self.index_html)

    def test_09_truthful_trust_stats(self):
        """Verify stats reflect truthful technical metrics without fake figures."""
        self.assertIn("Behavior Dimensions", self.landing_js)
        self.assertIn("Response Strategies", self.landing_js)
        self.assertIn("Automated Tests", self.landing_js)
        self.assertIn("Vector Databases", self.landing_js)
        self.assertNotIn("100K+ Users", self.landing_js)
        self.assertNotIn("1M+ Conversations", self.landing_js)

    def test_10_faq_questions_and_answers(self):
        """Verify 6 truthful FAQs including production model and no-RAG architecture."""
        required_questions = [
            "Is AvaAI free to use?",
            "Does Ava remember my conversations?",
            "Can Ava write and run code?",
            "What model powers Ava?",
            "Does Ava use RAG?",
            "Can I delete my data?"
        ]
        for q in required_questions:
            self.assertIn(q, self.landing_js)
        self.assertIn("openai/gpt-oss-120b via Groq", self.landing_js)
        self.assertNotIn("llama-3.3-70b-versatile", self.landing_js)
        self.assertIn("does not use vector embeddings or a vector database", self.landing_js)

    def test_11_chat_drawer_integration(self):
        """Verify chat drawer connects to /api/chat/stream and /api/feedback."""
        self.assertIn("/api/chat/stream", self.landing_js)
        self.assertIn("/api/feedback", self.landing_js)
        self.assertIn("/api/sessions/", self.landing_js)
        self.assertIn("credentials: 'same-origin'", self.landing_js)
        self.assertIn("Sign In →", self.index_html)
        self.assertIn("Get Started Free", self.index_html)

    def test_12_css_tokens_and_accessibility(self):
        """Verify CSS tokens and accessibility rules."""
        self.assertIn("--landing-bg", self.landing_css)
        self.assertIn("--landing-surface", self.landing_css)
        self.assertIn("--landing-text", self.landing_css)
        self.assertIn("--landing-muted", self.landing_css)
        self.assertIn("--landing-cyan", self.landing_css)
        self.assertIn("--landing-blue", self.landing_css)
        self.assertIn("--landing-purple", self.landing_css)
        self.assertIn("--landing-border", self.landing_css)
        self.assertIn("--landing-radius", self.landing_css)
        self.assertIn("--landing-shadow", self.landing_css)
        self.assertIn("--landing-container", self.landing_css)
        self.assertIn("prefers-reduced-motion", self.landing_css)


if __name__ == "__main__":
    unittest.main()
