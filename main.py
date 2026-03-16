from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.core.window import Window
from kivy.properties import StringProperty, NumericProperty, ListProperty
from kivy.clock import Clock
from kivy.metrics import dp
import json
import os

# Import AI service and payment
from ai_service import AIEstimator
import applepay

# Set window size for desktop testing (ignored on iOS)
Window.size = (400, 750)


class HomeScreen(Screen):
    """Main screen with options to get estimate or schedule"""
    pass


class EstimateScreen(Screen):
    """Screen for getting AI-based electrical work estimates"""
    job_description = StringProperty("")
    estimate_result = StringProperty("")
    estimated_cost = NumericProperty(0)

    def get_estimate(self):
        """Get AI-based estimate for the electrical work"""
        if not self.job_description.strip():
            self.estimate_result = "Please describe the electrical work needed."
            return

        self.estimate_result = "Getting estimate..."
        Clock.schedule_once(lambda dt: self._fetch_estimate(), 0.1)

    def _fetch_estimate(self):
        """Fetch estimate from AI service"""
        try:
            estimator = App.get_running_app().ai_estimator
            result = estimator.get_estimate(self.job_description)

            self.estimate_result = result.get('explanation', 'Unable to get estimate')
            self.estimated_cost = result.get('estimated_cost', 0)

            # Store for scheduling
            App.get_running_app().current_estimate = result
        except Exception as e:
            self.estimate_result = f"Error getting estimate: {str(e)}"

    def proceed_to_schedule(self):
        """Move to scheduling screen with current estimate"""
        if self.estimated_cost > 0:
            self.manager.current = 'schedule'


class ScheduleScreen(Screen):
    """Screen for scheduling electrician visit"""
    selected_date = StringProperty("Select Date")
    selected_time = StringProperty("Select Time")
    address = StringProperty("")
    phone = StringProperty("")

    available_dates = ListProperty([])
    available_times = ListProperty([
        "8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM",
        "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM"
    ])

    def on_enter(self):
        """Generate available dates when entering screen"""
        from datetime import datetime, timedelta
        today = datetime.now()
        self.available_dates = [
            (today + timedelta(days=i)).strftime("%A, %b %d")
            for i in range(1, 15)  # Next 14 days
        ]

    def confirm_booking(self):
        """Confirm the booking and process payment"""
        if not self.address.strip():
            self._show_popup("Error", "Please enter your address")
            return
        if not self.phone.strip():
            self._show_popup("Error", "Please enter your phone number")
            return
        if self.selected_date == "Select Date":
            self._show_popup("Error", "Please select a date")
            return
        if self.selected_time == "Select Time":
            self._show_popup("Error", "Please select a time")
            return

        # Get current estimate
        app = App.get_running_app()
        estimate = getattr(app, 'current_estimate', {})
        cost_cents = int(estimate.get('estimated_cost', 0) * 100)

        if cost_cents <= 0:
            self._show_popup("Error", "No valid estimate found")
            return

        # Process payment via Whop checkout (supports Apple Pay, cards, etc.)
        description = f"Electrician Service - {self.selected_date}"
        result = applepay.preauthorize(cost_cents, description)

        if result.get('error'):
            self._show_popup("Payment Error", result['error'])
        else:
            # Store booking details
            booking = {
                'date': self.selected_date,
                'time': self.selected_time,
                'address': self.address,
                'phone': self.phone,
                'estimate': estimate,
                'checkout_id': result.get('checkout_id'),
                'payment_status': 'pending'
            }
            app.bookings.append(booking)

            self._show_popup(
                "Booking Confirmed!",
                f"Your electrician is scheduled for:\n{self.selected_date} at {self.selected_time}\n\n"
                f"Address: {self.address}\n"
                f"Estimated Cost: ${estimate.get('estimated_cost', 0):.2f}\n\n"
                "You will receive a confirmation call shortly."
            )
            self.manager.current = 'home'

    def _show_popup(self, title, message):
        """Show a popup message"""
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text=message, text_size=(dp(250), None)))
        btn = Button(text='OK', size_hint_y=None, height=dp(40))
        content.add_widget(btn)

        popup = Popup(title=title, content=content, size_hint=(0.8, 0.5))
        btn.bind(on_press=popup.dismiss)
        popup.open()


class BookingsScreen(Screen):
    """Screen showing past and upcoming bookings"""
    pass


class ChatScreen(Screen):
    """Chat screen for asking electrical questions"""
    chat_history = StringProperty("")
    user_message = StringProperty("")

    def send_message(self):
        """Send message to AI and get response"""
        if not self.user_message.strip():
            return

        # Add user message to history
        self.chat_history += f"\n[You]: {self.user_message}\n"
        question = self.user_message
        self.user_message = ""

        # Get AI response
        Clock.schedule_once(lambda dt: self._get_ai_response(question), 0.1)

    def _get_ai_response(self, question):
        """Get response from AI"""
        try:
            estimator = App.get_running_app().ai_estimator
            response = estimator.chat(question)
            self.chat_history += f"[Electrician AI]: {response}\n"
        except Exception as e:
            self.chat_history += f"[Error]: {str(e)}\n"


class ElectriciansNowApp(App):
    """Main application class"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ai_estimator = None
        self.current_estimate = {}
        self.bookings = []

    def build(self):
        """Build the application UI"""
        # Initialize AI service
        self.ai_estimator = AIEstimator()

        # Create screen manager
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(EstimateScreen(name='estimate'))
        sm.add_widget(ScheduleScreen(name='schedule'))
        sm.add_widget(BookingsScreen(name='bookings'))
        sm.add_widget(ChatScreen(name='chat'))

        return sm

    def get_estimate_summary(self):
        """Get summary of current estimate for display"""
        if self.current_estimate:
            return f"Estimated Cost: ${self.current_estimate.get('estimated_cost', 0):.2f}"
        return ""


if __name__ == '__main__':
    ElectriciansNowApp().run()
