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
from threading import Thread

from ai_service import AIEstimator
import applepay
import user_prefs
import app_logger
import location_service

# Window size only used for desktop; ignored on iOS
Window.size = (400, 800)


class HomeScreen(Screen):
    """Main screen with address bar + service options."""
    address = StringProperty("")
    locating = StringProperty("")

    def on_pre_enter(self):
        prefs = user_prefs.load()
        if prefs.get("address") and not self.address:
            self.address = prefs["address"]

    def save_address(self, text):
        self.address = text
        user_prefs.update(address=text)
        # Mirror to schedule screen so user doesn't re-type
        sched = self.manager.get_screen("schedule") if self.manager else None
        if sched:
            sched.address = text

    def use_current_location(self):
        """Resolve current location to an address (iOS Core Location)."""
        self.locating = "Locating..."
        Thread(target=self._do_locate, daemon=True).start()

    def _do_locate(self):
        try:
            addr = location_service.get_current_address()
        except Exception as e:
            app_logger.log_exception("home", "location lookup failed", e)
            addr = None
        Clock.schedule_once(lambda dt: self._apply_address(addr), 0)

    def _apply_address(self, addr):
        if addr:
            self.save_address(addr)
            self.locating = ""
        else:
            self.locating = "Could not determine location. Please type address."


class EstimateScreen(Screen):
    job_description = StringProperty("")
    estimate_result = StringProperty("")
    estimated_cost = NumericProperty(0)
    cost_range = StringProperty("")

    def get_estimate(self):
        if not self.job_description.strip():
            self.estimate_result = "Please describe the electrical work needed."
            return
        self.estimate_result = "Getting estimate..."
        Clock.schedule_once(lambda dt: self._fetch_estimate(), 0.1)

    def _fetch_estimate(self):
        try:
            estimator = App.get_running_app().ai_estimator
            result = estimator.get_estimate(self.job_description)
            app_logger.log("estimate", "got result",
                           cost=result.get("estimated_cost"),
                           low=result.get("cost_range_low"),
                           high=result.get("cost_range_high"))

            cost = result.get("estimated_cost", 0) or 0
            low = result.get("cost_range_low") or int(cost * 0.7) or 150
            high = result.get("cost_range_high") or int(cost * 1.5) or 800
            if cost <= 0:
                cost = (low + high) // 2

            parts = []
            parts.append(f"Estimate: ${low:,} - ${high:,}")
            if result.get("time_estimate"):
                parts.append(f"Time: {result['time_estimate']}")
            if result.get("explanation"):
                parts.append("")
                parts.append(result["explanation"])
            assumptions = result.get("assumptions") or []
            if assumptions:
                parts.append("")
                parts.append("Assumptions:")
                for a in assumptions:
                    parts.append(f"  - {a}")
            questions = result.get("clarifying_questions") or []
            if questions:
                parts.append("")
                parts.append("To narrow this down, please answer:")
                for q in questions:
                    parts.append(f"  - {q}")
                parts.append("")
                parts.append("Add details above and tap Get Estimate again, or proceed to schedule with the range above.")

            self.estimate_result = "\n".join(parts)
            self.estimated_cost = cost
            self.cost_range = f"${low:,} - ${high:,}"
            App.get_running_app().current_estimate = result
        except Exception as e:
            app_logger.log_exception("estimate", "fetch failed", e)
            self.estimate_result = f"Error getting estimate: {e}"

    def proceed_to_schedule(self):
        if self.estimated_cost > 0:
            self.manager.current = "schedule"


class ScheduleScreen(Screen):
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
        from datetime import datetime, timedelta
        today = datetime.now()
        self.available_dates = [
            (today + timedelta(days=i)).strftime("%A, %b %d")
            for i in range(1, 15)
        ]
        prefs = user_prefs.load()
        if not self.address and prefs.get("address"):
            self.address = prefs["address"]
        if not self.phone and prefs.get("phone"):
            self.phone = prefs["phone"]

    def confirm_booking(self):
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

        user_prefs.update(address=self.address, phone=self.phone)

        app = App.get_running_app()
        estimate = getattr(app, "current_estimate", {})
        cost_cents = int((estimate.get("estimated_cost") or 0) * 100)

        if cost_cents <= 0:
            self._show_popup("Error", "No valid estimate found")
            return

        description = f"Electrician Service - {self.selected_date}"
        app_logger.log("schedule", "confirming booking",
                       date=self.selected_date, time=self.selected_time,
                       cost_cents=cost_cents)
        result = applepay.preauthorize(cost_cents, description)

        if result.get("error") or result.get("status") == "failed":
            err = result.get("error") or "Payment failed"
            self._show_popup("Payment Error",
                             f"{err}\n\nTap 'Diagnostic Logs' on the home "
                             f"screen for details we can share with support.")
        else:
            booking = {
                "date": self.selected_date,
                "time": self.selected_time,
                "address": self.address,
                "phone": self.phone,
                "estimate": estimate,
                "checkout_id": result.get("checkout_id"),
                "payment_status": "pending",
            }
            app.bookings.append(booking)
            self._show_popup(
                "Booking Confirmed!",
                f"Your electrician is scheduled for:\n{self.selected_date} at {self.selected_time}\n\n"
                f"Address: {self.address}\n"
                f"Estimated Cost: ${estimate.get('estimated_cost', 0):.2f}\n\n"
                "You will receive a confirmation call shortly.",
            )
            self.manager.current = "home"

    def _show_popup(self, title, message):
        content = BoxLayout(orientation="vertical", padding=dp(15), spacing=dp(15))
        content.add_widget(Label(text=message, font_size=dp(18),
                                 text_size=(dp(280), None), halign="center"))
        btn = Button(text="OK", size_hint_y=None, height=dp(55), font_size=dp(20))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.9, 0.5),
                      title_size=dp(20))
        btn.bind(on_press=popup.dismiss)
        popup.open()


class BookingsScreen(Screen):
    pass


class ChatScreen(Screen):
    chat_history = StringProperty("")
    user_message = StringProperty("")

    def send_message(self):
        if not self.user_message.strip():
            return
        self.chat_history += f"\n[You]: {self.user_message}\n"
        question = self.user_message
        self.user_message = ""
        Clock.schedule_once(lambda dt: self._get_ai_response(question), 0.1)

    def _get_ai_response(self, question):
        try:
            estimator = App.get_running_app().ai_estimator
            response = estimator.chat(question)
            self.chat_history += f"[Electrician AI]: {response}\n"
        except Exception as e:
            self.chat_history += f"[Error]: {e}\n"


class LogsScreen(Screen):
    log_text = StringProperty("")

    def on_pre_enter(self):
        self.refresh()

    def refresh(self):
        lines = app_logger.read_recent(300)
        self.log_text = "".join(lines) if lines else "(no entries)"

    def clear_logs(self):
        app_logger.clear()
        self.refresh()


class ElectriciansNowApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ai_estimator = None
        self.current_estimate = {}
        self.bookings = []

    def build(self):
        self.ai_estimator = AIEstimator()
        app_logger.log("app", "started",
                       provider=self.ai_estimator.provider)

        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(EstimateScreen(name="estimate"))
        sm.add_widget(ScheduleScreen(name="schedule"))
        sm.add_widget(BookingsScreen(name="bookings"))
        sm.add_widget(ChatScreen(name="chat"))
        sm.add_widget(LogsScreen(name="logs"))
        return sm

    def get_estimate_summary(self):
        if self.current_estimate:
            return f"Estimated Cost: ${self.current_estimate.get('estimated_cost', 0):.2f}"
        return ""


if __name__ == "__main__":
    ElectriciansNowApp().run()
