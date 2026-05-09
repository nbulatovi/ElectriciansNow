"""
AI Service for ElectriciansNow
Provides AI-based estimates for electrical work using OpenAI or Anthropic Claude.
"""

import os
import json
import re

# Try to import AI libraries - they may not be available in all environments
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class AIEstimator:
    """
    AI-powered estimator for electrical work.
    Supports both OpenAI (ChatGPT) and Anthropic (Claude) APIs.
    """

    # System prompt for electrical estimations
    ESTIMATE_SYSTEM_PROMPT = """You are an expert electrical contractor.
You ALWAYS produce a usable price estimate, even when the description is short.

Rules:
1. NEVER refuse with "we need more details". If details are missing, make
   reasonable assumptions for a typical US residence, state them, and still
   give a price range.
2. Always include a low and high number. The high may be much higher than
   the low when uncertainty is high - that is fine.
3. If clarification would meaningfully narrow the range, write a short
   list of specific clarifying questions in the `clarifying_questions`
   field, but always provide the range too.
4. Use these typical US residential rates as a baseline:
   - Labor $80-150/hour
   - Standard outlet/switch install: $150-250
   - Ceiling fan replacement (existing wiring): $180-450
   - Ceiling fan install (new wiring): $400-900
   - Light fixture replacement: $150-350
   - Recessed lighting per fixture: $150-300
   - GFCI outlet: $150-220
   - Panel upgrade 200A: $1,800-4,000
   - EV charger 240V: $800-2,000
   - Whole-house rewiring: $8,000-20,000
5. Be brief in `explanation` - 3-5 short sentences."""

    CHAT_SYSTEM_PROMPT = """You are a helpful electrical contractor assistant for the ElectriciansNow app.
Answer questions about electrical work, safety, costs, and help users understand their electrical needs.
Be concise and helpful. If something requires professional inspection, always recommend it.
Keep responses brief and mobile-friendly (under 200 words when possible)."""

    def __init__(self):
        """Initialize the AI estimator with available API keys"""
        self.anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        self.openai_key = os.environ.get('OPENAI_API_KEY', '')
        self.provider = self._determine_provider()

    def _determine_provider(self):
        """Determine which AI provider to use based on available keys"""
        if self.anthropic_key and ANTHROPIC_AVAILABLE:
            return 'anthropic'
        elif self.openai_key and OPENAI_AVAILABLE:
            return 'openai'
        else:
            return 'fallback'

    def get_estimate(self, job_description: str) -> dict:
        """
        Get an AI-generated estimate for electrical work.

        Args:
            job_description: Description of the electrical work needed

        Returns:
            dict with 'estimated_cost', 'explanation', 'time_estimate'
        """
        prompt = f"""Estimate the following electrical work. If the
description is incomplete, assume a typical US residential setup and
state your assumptions in `assumptions`. Always return numeric estimates.

Work: {job_description}

Respond in this exact JSON shape (no other text):
{{
    "estimated_cost": <midpoint of range, number, must be > 0>,
    "cost_range_low": <number, must be > 0>,
    "cost_range_high": <number, must be > cost_range_low>,
    "time_estimate": "<estimated time to complete>",
    "explanation": "<3-5 sentence summary>",
    "assumptions": ["<assumption 1>", "<assumption 2>"],
    "clarifying_questions": ["<question 1>", "<question 2>"],
    "considerations": ["<consideration 1>"]
}}"""

        try:
            if self.provider == 'anthropic':
                return self._get_anthropic_estimate(prompt)
            elif self.provider == 'openai':
                return self._get_openai_estimate(prompt)
            else:
                return self._get_fallback_estimate(job_description)
        except Exception as e:
            return {
                'estimated_cost': 0,
                'explanation': f'Error getting estimate: {str(e)}',
                'time_estimate': 'Unknown'
            }

    def _get_anthropic_estimate(self, prompt: str) -> dict:
        """Get estimate using Anthropic Claude API"""
        client = anthropic.Anthropic(api_key=self.anthropic_key)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=self.ESTIMATE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text
        return self._parse_estimate_response(response_text)

    def _get_openai_estimate(self, prompt: str) -> dict:
        """Get estimate using OpenAI ChatGPT API"""
        client = openai.OpenAI(api_key=self.openai_key)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self.ESTIMATE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1024
        )

        response_text = response.choices[0].message.content
        return self._parse_estimate_response(response_text)

    def _parse_estimate_response(self, response_text: str) -> dict:
        """Parse the AI response into a structured estimate.

        Always returns a dict with a positive estimated_cost. If the model
        misbehaves and gives no numbers we fall back to a wide default range
        rather than blocking the user.
        """
        parsed = None
        try:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            parsed = None

        if not parsed or not parsed.get('estimated_cost'):
            # Mine the prose for any dollar amounts so we still return a number
            nums = [int(n.replace(',', '')) for n in re.findall(r'\$([0-9,]+)', response_text)]
            if nums:
                low = min(nums)
                high = max(nums) if max(nums) > low else low * 2
                parsed = parsed or {}
                parsed.setdefault('cost_range_low', low)
                parsed.setdefault('cost_range_high', high)
                parsed['estimated_cost'] = (low + high) // 2
                parsed.setdefault('explanation', response_text.strip())
            else:
                # Last resort: a wide useful range so user can still proceed
                parsed = {
                    'estimated_cost': 300,
                    'cost_range_low': 150,
                    'cost_range_high': 800,
                    'time_estimate': '1-4 hours typical',
                    'explanation': (response_text.strip() or
                                    'Estimate generated from typical residential rates.'),
                    'clarifying_questions': [
                        'How many fixtures or outlets are involved?',
                        'Is existing wiring already in place?',
                        'Any special access requirements (high ceiling, attic, crawlspace)?',
                    ],
                    'considerations': ['Schedule a visit for a precise quote'],
                }
        return parsed

    def _get_fallback_estimate(self, job_description: str) -> dict:
        """
        Provide a basic estimate when AI APIs are not available.
        Uses simple keyword matching for common electrical jobs.
        """
        description_lower = job_description.lower()

        # Basic estimates based on common jobs
        estimates = {
            'outlet': {'cost': 175, 'time': '1-2 hours', 'desc': 'Standard outlet installation'},
            'switch': {'cost': 150, 'time': '1 hour', 'desc': 'Light switch installation/replacement'},
            'panel': {'cost': 2500, 'time': '4-8 hours', 'desc': 'Electrical panel upgrade'},
            'breaker': {'cost': 250, 'time': '1-2 hours', 'desc': 'Circuit breaker replacement'},
            'ceiling fan': {'cost': 250, 'time': '2-3 hours', 'desc': 'Ceiling fan installation'},
            'light fixture': {'cost': 200, 'time': '1-2 hours', 'desc': 'Light fixture installation'},
            'recessed': {'cost': 200, 'time': '1-2 hours per light', 'desc': 'Recessed lighting installation'},
            'gfci': {'cost': 185, 'time': '1 hour', 'desc': 'GFCI outlet installation'},
            'smoke detector': {'cost': 150, 'time': '30 min - 1 hour', 'desc': 'Smoke detector installation'},
            'ev charger': {'cost': 1200, 'time': '4-6 hours', 'desc': 'EV charger installation'},
            'wire': {'cost': 500, 'time': '2-4 hours', 'desc': 'Wiring repair/installation'},
            'inspection': {'cost': 150, 'time': '1 hour', 'desc': 'Electrical inspection'},
        }

        matched_estimate = None
        for keyword, estimate in estimates.items():
            if keyword in description_lower:
                matched_estimate = estimate
                break

        if matched_estimate:
            return {
                'estimated_cost': matched_estimate['cost'],
                'cost_range_low': int(matched_estimate['cost'] * 0.8),
                'cost_range_high': int(matched_estimate['cost'] * 1.5),
                'time_estimate': matched_estimate['time'],
                'explanation': f"{matched_estimate['desc']}\n\n"
                              f"Estimated cost: ${matched_estimate['cost']}\n"
                              f"Range: ${int(matched_estimate['cost'] * 0.8)} - ${int(matched_estimate['cost'] * 1.5)}\n\n"
                              "Note: This is a basic estimate. Actual costs may vary based on:\n"
                              "- Complexity of the job\n"
                              "- Accessibility of the work area\n"
                              "- Local labor rates\n"
                              "- Required permits\n\n"
                              "Schedule an appointment for an accurate quote.",
                'materials_needed': ['Standard electrical supplies'],
                'considerations': ['Professional assessment recommended']
            }
        else:
            return {
                'estimated_cost': 300,
                'cost_range_low': 150,
                'cost_range_high': 800,
                'time_estimate': '1-4 hours typical',
                'explanation': (
                    "Based on typical residential electrical work, this job "
                    "is likely $150–$800. The exact price depends on the "
                    "specifics below. Tap Schedule to lock in a visit; you "
                    "won't be charged until the work is confirmed on-site."
                ),
                'clarifying_questions': [
                    'How many fixtures, outlets, or switches are involved?',
                    'Is existing wiring already in place, or does new wiring need to be run?',
                    'Where in the home is the work (kitchen, bath, attic, exterior, panel)?',
                ],
                'materials_needed': ['Standard electrical supplies'],
                'considerations': ['On-site assessment will give a firm quote']
            }

    def chat(self, message: str) -> str:
        """
        Chat with the AI assistant about electrical questions.

        Args:
            message: User's question or message

        Returns:
            AI response string
        """
        try:
            if self.provider == 'anthropic':
                return self._chat_anthropic(message)
            elif self.provider == 'openai':
                return self._chat_openai(message)
            else:
                return self._chat_fallback(message)
        except Exception as e:
            return f"Sorry, I'm having trouble responding right now. Error: {str(e)}"

    def _chat_anthropic(self, message: str) -> str:
        """Chat using Anthropic Claude API"""
        client = anthropic.Anthropic(api_key=self.anthropic_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=self.CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}]
        )

        return response.content[0].text

    def _chat_openai(self, message: str) -> str:
        """Chat using OpenAI ChatGPT API"""
        client = openai.OpenAI(api_key=self.openai_key)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self.CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ],
            max_tokens=512
        )

        return response.choices[0].message.content

    def _chat_fallback(self, message: str) -> str:
        """Fallback chat responses when AI is not available"""
        message_lower = message.lower()

        # Simple FAQ responses
        if 'cost' in message_lower or 'price' in message_lower or 'how much' in message_lower:
            return ("Electrical work costs vary widely:\n"
                   "- Minor repairs: $100-300\n"
                   "- Outlet/switch work: $150-250\n"
                   "- Fixture installation: $150-400\n"
                   "- Panel upgrades: $1,500-3,500\n\n"
                   "Use our estimate feature for a more specific quote!")

        elif 'emergency' in message_lower or 'urgent' in message_lower:
            return ("For electrical emergencies:\n"
                   "1. Turn off power at the breaker if safe\n"
                   "2. Don't touch exposed wires\n"
                   "3. Call 911 if there's fire or injury\n"
                   "4. Contact us for emergency service\n\n"
                   "We offer 24/7 emergency electrical services.")

        elif 'safe' in message_lower or 'danger' in message_lower:
            return ("Electrical safety tips:\n"
                   "- Never DIY complex electrical work\n"
                   "- Use GFCI outlets near water\n"
                   "- Don't overload circuits\n"
                   "- Replace damaged cords immediately\n"
                   "- Schedule regular inspections\n\n"
                   "When in doubt, call a professional!")

        else:
            return ("Thanks for your question! For the best assistance:\n"
                   "1. Use 'Get Estimate' for pricing\n"
                   "2. Use 'Schedule' to book a visit\n\n"
                   "Our licensed electricians can answer all your questions "
                   "during a scheduled consultation.")
