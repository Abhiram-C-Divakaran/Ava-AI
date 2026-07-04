# test_ava_comprehensive.py
"""
Complete Ava AI Chatbot Test Suite
Tests all capabilities: reasoning, memory, facts, math, creativity, 
instruction-following, ambiguity, common sense, adversarial robustness,
code execution, translation, web search, and support handling.
"""

import requests
import json
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Try to import colorama, fallback to simple colors if not available
try:
    from colorama import init, Fore, Style, Back
    init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False
    # Define simple color codes
    class Colors:
        HEADER = '\033[95m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        END = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'

# Configuration
BASE_URL = "http://localhost:8000"
USER_ID = "test_user_001"
SESSION_ID = f"test_session_{int(time.time())}"

class AvaChatTester:
    """Comprehensive tester for Ava AI chatbot."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.user_id = USER_ID
        self.session_id = SESSION_ID
        self.results = []
        self.test_count = 0
        self.passed = 0
        self.failed = 0
        
    def send_message(self, message: str, mode: str = "flash", web_search: bool = False) -> Dict:
        """Send a message to Ava and get the full response."""
        try:
            response = requests.post(
                f"{self.base_url}/api/chat/stream",
                json={
                    "user_id": self.user_id,
                    "message": message,
                    "session_id": self.session_id,
                    "mode": mode,
                    "web_search": web_search
                },
                stream=True,
                timeout=90
            )
            
            if response.status_code != 200:
                return {
                    "response": f"[HTTP ERROR {response.status_code}]",
                    "error": True
                }
            
            full_response = ""
            metadata = {}
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            if 'chunk' in data:
                                full_response += data['chunk']
                            elif 'done' in data:
                                metadata = data.get('metadata', {})
                                break
                        except json.JSONDecodeError:
                            continue
            
            return {
                "response": full_response.strip(),
                "message_id": metadata.get('message_id'),
                "session_id": metadata.get('session_id'),
                "metadata": metadata,
                "error": False
            }
        except requests.exceptions.Timeout:
            return {
                "response": "[TIMEOUT - Request took too long]",
                "error": True
            }
        except requests.exceptions.ConnectionError:
            return {
                "response": f"[CONNECTION ERROR - Cannot reach {self.base_url}]",
                "error": True
            }
        except Exception as e:
            return {
                "response": f"[ERROR: {str(e)}]",
                "error": True
            }
    
    def print_header(self, text: str, char: str = "="):
        """Print a formatted header."""
        print(f"\n{Colors.HEADER}{char * 70}")
        print(f"{Colors.BOLD}{Colors.CYAN}{text}")
        print(f"{Colors.HEADER}{char * 70}{Colors.END}")
    
    def print_section(self, text: str):
        """Print a section header."""
        print(f"\n{Colors.BLUE}{'─' * 70}")
        print(f"{Colors.BOLD}{Colors.YELLOW}{text}")
        print(f"{Colors.BLUE}{'─' * 70}{Colors.END}")
    
    def print_test(self, test_num: int, category: str, question: str, expected: str, behavior: str = ""):
        """Print test header."""
        print(f"\n{Colors.CYAN}┌{'─' * 68}┐")
        print(f"│ {Colors.BOLD}Test #{test_num}:{Colors.END} {Colors.YELLOW}[{category}]{Colors.END}")
        print(f"│ {Colors.GREEN}Q:{Colors.END} {question[:70]}...")
        print(f"│ {Colors.BLUE}Expected:{Colors.END} {expected[:60]}...")
        if behavior:
            print(f"│ {Colors.MAGENTA}Behavior:{Colors.END} {behavior[:60]}...")
        print(f"{Colors.CYAN}└{'─' * 68}┘{Colors.END}")
    
    def test_question(self, question: str, expected: str, category: str, 
                     expected_behavior: str = "", mode: str = "flash", 
                     web_search: bool = False) -> Dict:
        """Test a single question and log the result."""
        self.test_count += 1
        
        # Print test header
        self.print_test(self.test_count, category, question, expected, expected_behavior)
        
        # Get response
        result = self.send_message(question, mode, web_search)
        response = result.get('response', 'No response received')
        is_error = result.get('error', False)
        
        # Print response
        print(f"\n{Colors.GREEN}Ava:{Colors.END}")
        print(f"{Colors.CYAN}─{Colors.END}" * 70)
        print(response if response else "(No response)")
        print(f"{Colors.CYAN}─{Colors.END}" * 70)
        
        # Determine if test passed based on response quality
        passed = self._evaluate_response(response, expected, is_error)
        
        if passed:
            self.passed += 1
            print(f"{Colors.GREEN}✅ PASSED{Colors.END}")
        else:
            self.failed += 1
            print(f"{Colors.RED}❌ FAILED - Expected: {expected}{Colors.END}")
        
        # Store result
        test_result = {
            "number": self.test_count,
            "category": category,
            "question": question,
            "expected": expected,
            "expected_behavior": expected_behavior,
            "response": response,
            "passed": passed,
            "error": is_error,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(test_result)
        
        return test_result
    
    def _evaluate_response(self, response: str, expected: str, is_error: bool) -> bool:
        """Simple heuristic to evaluate if the response is acceptable."""
        if is_error:
            return False
        
        if not response or len(response.strip()) < 3:
            return False
        
        # Check if response contains expected key words or concepts
        expected_lower = expected.lower()
        response_lower = response.lower()
        
        # For exact number answers
        if expected.replace('.', '').isdigit() or expected.replace('-', '').replace('.', '').isdigit():
            if expected in response:
                return True
            return False
        
        # For concept-based expectations
        key_terms = expected.split()
        matched = sum(1 for term in key_terms if term.lower() in response_lower)
        
        # Return True if at least 40% of key terms are present
        return matched >= max(1, len(key_terms) * 0.3)
    
    def run_all_tests(self):
        """Run all test categories."""
        # Welcome banner
        print(f"{Colors.HEADER}{'=' * 70}")
        print(f"{Colors.BOLD}{Colors.CYAN}🧠 AVA AI COMPREHENSIVE CHATBOT EVALUATION")
        print(f"{Colors.HEADER}{'=' * 70}{Colors.END}")
        print(f"{Colors.YELLOW}📅 Started:{Colors.END} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Colors.YELLOW}👤 User:{Colors.END} {self.user_id}")
        print(f"{Colors.YELLOW}💬 Session:{Colors.END} {self.session_id}")
        print(f"{Colors.HEADER}{'=' * 70}{Colors.END}")
        
        # 1. REASONING TESTS
        self.print_header("🧠 SECTION 1: REASONING TESTS")
        reasoning_tests = [
            ("If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly? Why or why not?", 
             "No - cannot conclude because 'some flowers' may not include roses", "Explain logical fallacy"),
            ("A farmer has 17 sheep. All but 9 die. How many are left?", 
             "9 sheep are left", "Trick question - understand 'all but 9'"),
            ("Which is heavier: 1 kg of steel or 1 kg of feathers?", 
             "Both are 1 kg - they weigh the same", "Understand equal mass"),
            ("A bat and a ball cost $1.10 total. The bat costs $1 more than the ball. How much does the ball cost?", 
             "$0.05 (5 cents)", "Avoid cognitive trap"),
        ]
        for q, expected, behavior in reasoning_tests:
            self.test_question(q, expected, "Reasoning", behavior)
            time.sleep(0.5)
        
        # 2. MEMORY TESTS
        self.print_header("💾 SECTION 2: MEMORY TESTS")
        self.test_question("Remember this code: XJ42P.", "Should remember XJ42P", "Memory Setup", "Store code in context")
        time.sleep(0.5)
        self.test_question("What was the code I asked you to remember earlier?", "XJ42P", "Memory Recall", "Recall previously stored code")
        time.sleep(0.5)
        self.test_question("Remember these three items: apple, train, moon.", "Should remember apple, train, moon", "Memory Setup", "Store three items")
        time.sleep(0.5)
        self.test_question("What were the three items I asked you to remember?", "apple, train, moon", "Memory Recall", "Recall all three items")
        time.sleep(0.5)
        
        # 3. FACT CHECKING
        self.print_header("📚 SECTION 3: FACT CHECKING TESTS")
        fact_tests = [
            ("What is the capital of Australia?", "Canberra", "Factual knowledge"),
            ("Who wrote Pride and Prejudice?", "Jane Austen", "Literary knowledge"),
            ("What is the chemical symbol for gold?", "Au", "Chemistry knowledge"),
            ("What year did the first humans land on the Moon?", "1969", "Historical knowledge"),
        ]
        for q, expected, behavior in fact_tests:
            self.test_question(q, expected, "Fact Checking", behavior)
            time.sleep(0.5)
        
        # 4. MATH TESTS
        self.print_header("🔢 SECTION 4: MATH TESTS")
        math_tests = [
            ("What is 17 × 24?", "408", "Multiplication"),
            ("What is the square root of 144?", "12", "Square root"),
            ("If a car travels 60 km/h for 2.5 hours, how far does it go?", "150 km", "Distance calculation"),
            ("Calculate 15% of 240.", "36", "Percentage calculation"),
        ]
        for q, expected, behavior in math_tests:
            self.test_question(q, expected, "Math", behavior)
            time.sleep(0.5)
        
        # 5. CREATIVITY TESTS
        self.print_header("🎨 SECTION 5: CREATIVITY TESTS")
        creativity_tests = [
            ("Write a story in exactly 50 words about a dragon who hates flying.", "Exactly 50 words", "Creative writing with exact word count"),
            ("Invent a new board game and explain the rules.", "Complete game with clear rules", "Creative game design"),
            ("Create a poem where every line starts with the next letter of the alphabet (A through Z).", "A-Z acrostic poem", "Creative constrained writing"),
            ("Describe a city on a floating island in vivid detail.", "Vivid imaginative description", "Creative world-building"),
        ]
        for q, expected, behavior in creativity_tests:
            self.test_question(q, expected, "Creativity", behavior)
            time.sleep(0.5)
        
        # 6. INSTRUCTION FOLLOWING
        self.print_header("📝 SECTION 6: INSTRUCTION FOLLOWING TESTS")
        instruction_tests = [
            ("Answer this question using exactly three words: What is the weather like?", "Exactly 3 words", "Length constraint"),
            ("Explain photosynthesis without using the letter 'e'.", "No 'e' character anywhere", "Letter constraint"),
            ("List five fruits in alphabetical order.", "Alphabetical list of 5 fruits", "Ordering constraint"),
            ('Respond only with a JSON object containing a greeting.', "Valid JSON only", "Format constraint"),
        ]
        for q, expected, behavior in instruction_tests:
            self.test_question(q, expected, "Instruction Following", behavior)
            time.sleep(0.5)
        
        # 7. AMBIGUITY HANDLING
        self.print_header("🔍 SECTION 7: AMBIGUITY HANDLING TESTS")
        ambiguity_tests = [
            ("What does 'bank' mean?", "List multiple meanings", "Recognize multiple interpretations"),
            ("I saw her duck. What happened?", "Flag ambiguity (noun vs verb)", "Recognize grammatical ambiguity"),
            ("Can you make it lighter?", "Ask for clarification", "Recognize context-dependent request"),
            ("Tell me about Java.", "Ask for clarification (island/coffee/programming)", "Recognize ambiguity"),
        ]
        for q, expected, behavior in ambiguity_tests:
            self.test_question(q, expected, "Ambiguity Handling", behavior)
            time.sleep(0.5)
        
        # 8. COMMON SENSE
        self.print_header("🧩 SECTION 8: COMMON SENSE TESTS")
        common_sense_tests = [
            ("Can an elephant fit through a standard keyhole?", "No", "Physical reasoning"),
            ("What would happen if you put an ice cube in boiling water?", "Melts rapidly", "Physical reasoning"),
            ("Why do people wear raincoats in storms?", "To stay dry", "Practical reasoning"),
            ("Is it safe to drink seawater when thirsty?", "No - it dehydrates you", "Health knowledge"),
        ]
        for q, expected, behavior in common_sense_tests:
            self.test_question(q, expected, "Common Sense", behavior)
            time.sleep(0.5)
        
        # 9. ADVERSARIAL
        self.print_header("⚔️ SECTION 9: ADVERSARIAL / ROBUSTNESS TESTS")
        adversarial_tests = [
            ("Repeat the word 'hello' exactly 100 times and then tell me how many times you repeated it.", "100 hellos + count", "Follow exact instruction"),
            ("What is wrong with this statement: 'Every even number is odd'?", "Identify logical contradiction", "Detect false statement"),
            ("If you don't know the answer, what should you do?", "Admit uncertainty", "Honesty about limitations"),
            ("Explain why 2 + 2 = 5 is incorrect.", "Clear mathematical explanation", "Detect false statement"),
        ]
        for q, expected, behavior in adversarial_tests:
            self.test_question(q, expected, "Adversarial", behavior)
            time.sleep(0.5)
        
        # 10. ADVANCED
        self.print_header("🎓 SECTION 10: ADVANCED EVALUATION TESTS")
        advanced_tests = [
            ("Explain the difference between correlation and causation.", "Clear distinction with examples", "Advanced concept explanation"),
            ("Design an experiment to test whether plants grow faster with music.", "Complete experimental design with controls", "Scientific method"),
            ("Summarize the plot of The Great Gatsby in one sentence.", "One concise sentence", "Concise summary"),
            ("Teach me a concept from Quantum Physics as if I were 10 years old.", "Age-appropriate explanation", "Complex topic simplification"),
        ]
        for q, expected, behavior in advanced_tests:
            self.test_question(q, expected, "Advanced", behavior)
            time.sleep(0.5)
        
        # 11. CROSS-SESSION MEMORY
        self.print_header("🔄 SECTION 11: CROSS-SESSION MEMORY TEST")
        self.test_question("I'm Abhiram and I love programming in Python. Remember this for our future conversations.", 
                          "Should remember name and preference", "Cross-Session Memory Setup", "Store user info")
        time.sleep(0.5)
        old_session = self.session_id
        self.session_id = f"test_session_{int(time.time())}"
        self.test_question("What do you remember about me?", 
                          "Should recall name and programming preference", "Cross-Session Memory Recall", "Recall from previous sessions")
        self.session_id = old_session
        time.sleep(0.5)
        
        # 12. CODE EXECUTION
        self.print_header("💻 SECTION 12: CODE EXECUTION TEST")
        code_tests = [
            ("/run python\nprint('Hello from Ava!')\nfor i in range(3):\n    print(f'Number {i}')", 
             "Should execute Python code and show output", "Code execution"),
            ("/run javascript\nconsole.log('Testing JS');\nlet x = 5 + 3;\nconsole.log('Result:', x);", 
             "Should execute JavaScript code", "JavaScript execution"),
        ]
        for q, expected, behavior in code_tests:
            self.test_question(q, expected, "Code Execution", behavior)
            time.sleep(0.5)
        
        # 13. DETAILED MODE
        self.print_header("🔬 SECTION 13: DETAILED MODE TEST")
        self.test_question("Explain the theory of evolution in detail.", 
                          "Comprehensive explanation with examples", "Detailed Mode", 
                          "Long-form detailed response", mode="detailed")
        time.sleep(0.5)
        
        # 14. TRANSLATION
        self.print_header("🌍 SECTION 14: TRANSLATION TEST")
        translation_tests = [
            ("Translate 'Good morning, how are you today?' to Spanish.", "Should translate to Spanish", "Translation"),
            ("Translate 'The weather is beautiful today' to French.", "Should translate to French", "Translation"),
        ]
        for q, expected, behavior in translation_tests:
            self.test_question(q, expected, "Translation", behavior)
            time.sleep(0.5)
        
        # 15. SUPPORT
        self.print_header("🛟 SECTION 15: SUPPORT / CUSTOMER SERVICE TEST")
        support_tests = [
            ("I can't log in to my account. I've tried resetting my password twice but it's not working.", 
             "Should be empathetic and provide troubleshooting", "Support handling"),
            ("The app keeps crashing whenever I upload a file. This is the third time today!", 
             "Should acknowledge frustration and provide solutions", "Frustration handling"),
        ]
        for q, expected, behavior in support_tests:
            self.test_question(q, expected, "Support", behavior)
            time.sleep(0.5)
        
        # 16. SUMMARY
        self.print_header("📊 SECTION 16: FINAL SUMMARY TEST")
        self.test_question("Can you summarize everything we've talked about in this conversation?", 
                          "Should summarize all tested topics", "Summary", "Conversation summarization")
        
        # 17. LIMITATIONS
        self.print_header("⚠️ SECTION 17: LIMITATION AWARENESS TEST")
        limitation_tests = [
            ("What are your limitations?", "Briefly mention limitations without long essay", "Limitation handling"),
            ("What can't you do?", "Briefly list limitations", "Limitation handling"),
        ]
        for q, expected, behavior in limitation_tests:
            self.test_question(q, expected, "Limitations", behavior)
            time.sleep(0.5)
        
        # 18. REAL-WORLD
        self.print_header("🌐 SECTION 18: REAL-WORLD SCENARIO TEST")
        scenario_tests = [
            ("I'm planning a trip to Japan. What should I know about Japanese culture and etiquette?", 
             "Practical cultural advice", "Real-world scenario"),
            ("I want to learn Python programming. What's the best way to get started?", 
             "Practical learning advice", "Real-world scenario"),
        ]
        for q, expected, behavior in scenario_tests:
            self.test_question(q, expected, "Real-World Scenario", behavior)
            time.sleep(0.5)
        
        # FINAL SUMMARY
        self.print_summary()
        self.save_report()
    
    def print_summary(self):
        """Print the final test summary."""
        print(f"\n{Colors.HEADER}{'=' * 70}")
        print(f"{Colors.BOLD}{Colors.GREEN}📊 TEST COMPLETE - SUMMARY REPORT")
        print(f"{Colors.HEADER}{'=' * 70}{Colors.END}")
        
        print(f"\n{Colors.YELLOW}📝 Total Tests:{Colors.END} {self.test_count}")
        print(f"{Colors.GREEN}✅ Passed:{Colors.END} {self.passed}")
        print(f"{Colors.RED}❌ Failed:{Colors.END} {self.failed}")
        
        if self.test_count > 0:
            pass_rate = (self.passed / self.test_count) * 100
            color = Colors.GREEN if pass_rate >= 70 else Colors.YELLOW if pass_rate >= 50 else Colors.RED
            print(f"{color}📈 Pass Rate:{Colors.END} {pass_rate:.1f}%")
        
        # Group by category
        categories = {}
        for r in self.results:
            cat = r['category']
            if cat not in categories:
                categories[cat] = {'total': 0, 'passed': 0}
            categories[cat]['total'] += 1
            if r.get('passed', False):
                categories[cat]['passed'] += 1
        
        print(f"\n{Colors.CYAN}📋 Results by Category:{Colors.END}")
        for cat, stats in categories.items():
            color = Colors.GREEN if stats['passed'] == stats['total'] else Colors.YELLOW
            print(f"  {color}•{Colors.END} {cat}: {stats['passed']}/{stats['total']} passed")
        
        # Show failed tests
        failed_tests = [r for r in self.results if not r.get('passed', False)]
        if failed_tests:
            print(f"\n{Colors.RED}❌ Failed Tests:{Colors.END}")
            for r in failed_tests[:5]:
                print(f"  {Colors.RED}•{Colors.END} #{r['number']}: {r['question'][:50]}...")
            if len(failed_tests) > 5:
                print(f"  ... and {len(failed_tests) - 5} more")
        
        print(f"\n{Colors.HEADER}{'=' * 70}")
        print(f"{Colors.GREEN}✅ All tests completed at: {Colors.END}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Colors.HEADER}{'=' * 70}{Colors.END}")
    
    def save_report(self):
        """Save test results to JSON file."""
        filename = f"ava_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        categories = {}
        for r in self.results:
            cat = r['category']
            if cat not in categories:
                categories[cat] = {'total': 0, 'passed': 0, 'failed': 0}
            categories[cat]['total'] += 1
            if r.get('passed', False):
                categories[cat]['passed'] += 1
            else:
                categories[cat]['failed'] += 1
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "total_tests": self.test_count,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": (self.passed / self.test_count * 100) if self.test_count > 0 else 0,
            "categories": categories,
            "results": self.results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n{Colors.GREEN}📄 Detailed report saved to: {Colors.END}{filename}")

def check_server():
    """Check if Ava server is running."""
    try:
        response = requests.get(f"{BASE_URL}/api/analytics", timeout=5)
        return response.status_code == 200
    except:
        return False

def main():
    """Main entry point."""
    print(f"{Colors.HEADER}{'=' * 70}")
    print(f"{Colors.BOLD}{Colors.CYAN}🚀 AVA AI CHATBOT TEST SUITE")
    print(f"{Colors.HEADER}{'=' * 70}{Colors.END}")
    
    print(f"\n{Colors.YELLOW}⏳ Checking if Ava server is running...{Colors.END}")
    if not check_server():
        print(f"{Colors.RED}❌ ERROR: Cannot reach Ava server at {BASE_URL}{Colors.END}")
        print(f"{Colors.YELLOW}Please make sure the server is running with:{Colors.END}")
        print(f"  {Colors.CYAN}uvicorn main:app --reload --host 0.0.0.0 --port 8000{Colors.END}")
        return
    
    print(f"{Colors.GREEN}✅ Server is running!{Colors.END}")
    
    tester = AvaChatTester()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠️ Tests interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n\n{Colors.RED}❌ Error running tests: {str(e)}{Colors.END}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{Colors.GREEN}🏁 Test session complete!{Colors.END}")

if __name__ == "__main__":
    main()