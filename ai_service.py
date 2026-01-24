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
    ESTIMATE_SYSTEM_PROMPT = """You are an expert electrical contractor assistant. Your job is to provide accurate cost estimates for electrical work based on the description provided.

When giving estimates, consider:
- Labor costs (typically $50-150/hour depending on complexity)
- Material costs (wiring, outlets, panels, fixtures, etc.)
- Permit requirements for major work
- Regional pricing variations
- Complexity and time required

Always provide:
1. A cost range (low to high estimate)
2. Breakdown of major cost components
3. Factors that could affect the final price
4. Time estimate for completion
5. Any safety considerations or code requirements

Be helpful but always recommend getting an in-person assessment for accurate quotes."""

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
        prompt = f"""Please provide an estimate for the following electrical work:

{job_description}

Respond in the following JSON format:
{{
    "estimated_cost": <average estimated cost as a number>,
    "cost_range_low": <low estimate as a number>,
    "cost_range_high": <high estimate as a number>,
    "time_estimate": "<estimated time to complete>",
    "explanation": "<detailed explanation of the estimate>",
    "materials_needed": ["<list of main materials>"],
    "considerations": ["<list of important considerations>"]
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
        """Parse the AI response into a structured estimate"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # Fallback: return raw response
        return {
            'estimated_cost': 0,
            'explanation': response_text,
            'time_estimate': 'Contact for assessment'
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
                'estimated_cost': 200,
                'cost_range_low': 100,
                'cost_range_high': 500,
                'time_estimate': 'Varies',
                'explanation': "We need more details to provide an accurate estimate.\n\n"
                              "Common electrical service costs:\n"
                              "- Outlet installation: $150-250\n"
                              "- Light fixture: $150-300\n"
                              "- Panel upgrade: $1,500-3,500\n"
                              "- Whole house rewiring: $8,000-15,000\n\n"
                              "Schedule a visit for a detailed assessment and accurate quote.",
                'materials_needed': ['To be determined'],
                'considerations': ['On-site assessment needed']
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
