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
    ESTIMATE_SYSTEM_PROMPT = """You are an expert residential electrical contractor.
You produce a price RANGE for every job, plus interactive multiple-choice
follow-up questions that let the customer narrow the range with a single tap.

Always reply with ONE JSON object, no surrounding prose. Schema:

{
  "estimated_cost": <int midpoint of low/high>,
  "cost_range_low": <int>,
  "cost_range_high": <int>,
  "confidence": "low" | "medium" | "high",
  "explanation": "<2-3 short sentences explaining the estimate>",
  "clarifying_questions": [
    {
      "question": "<short single-sentence question>",
      "options": [
        {"label": "<short tap-friendly answer, max 6 words>",
         "context": "<one-line clarifying fact this answer adds>"}
      ]
    }
  ]
}

Rules:
1. ALWAYS give a numeric range. Never refuse with "need more details".
2. If the high/low ratio > 2.5x, output 1-3 clarifying_questions, each with
   2-4 options. Each option must be a complete answer the user can tap
   without typing. Include "I don't know" / "Not sure" as one option when
   the answer is technical.
3. If confidence is "high" (high/low ratio < 1.4x), output zero
   clarifying_questions - the user can proceed to schedule.
4. The questions should target the largest sources of cost variance:
   existing wiring vs new, ceiling height / accessibility, fixture quality,
   number of units, location indoor/outdoor, permit needs, age of building.
5. Baseline US residential rates:
   - Labor $80-150/hour
   - Outlet/switch: $150-250 each
   - Ceiling fan replacement (existing wiring): $180-300
   - Ceiling fan install (new wiring required): $400-900
   - Light fixture replacement: $150-350
   - Recessed lighting per can: $150-300
   - GFCI outlet: $150-220
   - Panel upgrade 200A: $1,800-4,000
   - EV charger 240V: $800-2,000
   - Whole-house rewiring: $8,000-20,000
6. `explanation`: 2-3 SHORT sentences, plain language, no bullet points."""

    CHAT_SYSTEM_PROMPT = """You are a helpful electrical contractor assistant for the ElectriciansNow app.
Answer questions about electrical work, safety, costs, and help users understand their electrical needs.
Be concise and helpful. If something requires professional inspection, always recommend it.
Keep responses brief and mobile-friendly (under 200 words when possible)."""

    def __init__(self):
        """Initialize the AI estimator with available API keys"""
        try:
            import secrets_baked as _baked
        except ImportError:
            _baked = None
        def _secret(name):
            if _baked is not None and getattr(_baked, name, None):
                return getattr(_baked, name)
            return os.environ.get(name, '')
        self.anthropic_key = _secret('ANTHROPIC_API_KEY')
        self.openai_key = _secret('OPENAI_API_KEY')
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
        prompt = f"Estimate this electrical work:\n\n{job_description}"

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
        """Parse the AI response into the v2 structured estimate.

        Always returns a dict with a positive estimated_cost and a
        clarifying_questions list (possibly empty). If the model misbehaves
        and gives no numbers we fall back to a wide default range with
        generic narrowing questions.
        """
        parsed = None
        try:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                parsed = json.loads(json_match.group())
        except (json.JSONDecodeError, ValueError):
            parsed = None

        if not parsed or not parsed.get('estimated_cost'):
            nums = [int(n.replace(',', '')) for n in re.findall(r'\$([0-9,]+)', response_text)]
            if nums:
                low = min(nums)
                high = max(nums) if max(nums) > low else low * 2
                parsed = parsed or {}
                parsed.setdefault('cost_range_low', low)
                parsed.setdefault('cost_range_high', high)
                parsed['estimated_cost'] = (low + high) // 2
                parsed.setdefault('explanation', response_text.strip()[:300])
            else:
                parsed = self._generic_estimate(response_text.strip())

        # Normalize question shape - ensure each has options[]
        questions = parsed.get('clarifying_questions') or []
        normalized = []
        for q in questions:
            if isinstance(q, str):
                # Old-format string question - skip, schema requires options
                continue
            if not isinstance(q, dict):
                continue
            opts = q.get('options') or []
            valid = []
            for o in opts:
                if isinstance(o, dict) and o.get('label'):
                    valid.append({
                        'label': str(o['label'])[:60],
                        'context': str(o.get('context') or o['label'])[:200],
                    })
            if q.get('question') and valid:
                normalized.append({
                    'question': str(q['question'])[:200],
                    'options': valid[:4],
                })
        parsed['clarifying_questions'] = normalized[:3]
        parsed.setdefault('confidence', 'medium')
        return parsed

    def _generic_estimate(self, raw_text=''):
        return {
            'estimated_cost': 350,
            'cost_range_low': 150,
            'cost_range_high': 800,
            'confidence': 'low',
            'explanation': (raw_text[:200] if raw_text else
                            "Typical residential electrical job. Tap an answer below to narrow this down."),
            'clarifying_questions': [
                {
                    'question': 'What kind of work is this?',
                    'options': [
                        {'label': 'Light fixture or fan', 'context': 'fixture install or replacement'},
                        {'label': 'Outlet or switch', 'context': 'outlet/switch work'},
                        {'label': 'Panel or breaker', 'context': 'panel or breaker work'},
                        {'label': 'Something else', 'context': 'other electrical work'},
                    ],
                },
            ],
        }

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
            cost = matched_estimate['cost']
            return {
                'estimated_cost': cost,
                'cost_range_low': int(cost * 0.8),
                'cost_range_high': int(cost * 1.5),
                'confidence': 'medium',
                'explanation': f"{matched_estimate['desc']}. Typical time: {matched_estimate['time']}. Tap an answer below to narrow this down.",
                'clarifying_questions': [
                    {
                        'question': 'How many of these are needed?',
                        'options': [
                            {'label': 'Just one', 'context': 'single unit'},
                            {'label': '2-3', 'context': '2-3 units'},
                            {'label': '4 or more', 'context': '4+ units'},
                        ],
                    },
                ],
            }
        else:
            return self._generic_estimate()

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
