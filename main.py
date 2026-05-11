from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.dropdown import DropDown
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.properties import (StringProperty, NumericProperty, ListProperty,
                             BooleanProperty)
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.animation import Animation
from threading import Thread
import os
import time

# Register the Nintendo display font if bundled
try:
    _font_path = os.path.join(os.path.dirname(__file__), "assets", "fonts", "Nunito-Black.ttf")
    if os.path.exists(_font_path):
        LabelBase.register(name="Nintendo", fn_regular=_font_path)
except Exception:
    pass

from ai_service import AIEstimator
import applepay
import user_prefs
import app_logger
import location_service
import telemetry
import address_autocomplete
from nintendo_widgets import (TileButton, HeroCard, PillButton, PriceTicker,
                              StyledTextInput, SWITCH_RED, SWITCH_BLUE,
                              MARIO_YELLOW, LUIGI_GREEN, STAR_PURPLE, CREAM,
                              NAVY)

# Cream background
Window.clearcolor = CREAM
Window.size = (400, 800)


class HomeScreen(Screen):
    address = StringProperty("")
    locating = StringProperty("")
    suggestions = ListProperty([])
    task_description = StringProperty("")

    _last_typed = ""
    _autocomplete_event = None
    _dropdown = None

    def on_pre_enter(self):
        prefs = user_prefs.load()
        if prefs.get("address") and not self.address:
            self.address = prefs["address"]
        telemetry.track("screen_changed", to="home")

    def start_estimate(self):
        """User typed a task and tapped Get Estimate -> jump to estimate flow."""
        if not self.task_description.strip():
            telemetry.track("estimate_blocked", reason="empty_task")
            return
        telemetry.track("home_start_estimate", chars=len(self.task_description))
        # Pass description to the estimate screen
        if self.manager:
            est = self.manager.get_screen("estimate")
            est.job_description = self.task_description
            self.manager.current = "estimate"
            # Auto-fire the estimate
            Clock.schedule_once(lambda dt: est.get_estimate(), 0.15)

    def address_text_changed(self, text):
        # Mirror to property
        self.address = text
        # Debounce autocomplete
        if self._autocomplete_event:
            self._autocomplete_event.cancel()
        self._autocomplete_event = Clock.schedule_once(
            lambda dt: self._fetch_suggestions(text), 0.35)

    def _fetch_suggestions(self, text):
        text = (text or "").strip()
        if len(text) < 3:
            self._close_dropdown()
            return
        if text == self._last_typed:
            return
        self._last_typed = text
        telemetry.track("address_typed", prefix_len=len(text))
        Thread(target=self._do_suggest, args=(text,), daemon=True).start()

    def _do_suggest(self, text):
        results = address_autocomplete.suggest(text, limit=5)
        Clock.schedule_once(lambda dt: self._show_suggestions(results), 0)

    def _show_suggestions(self, results):
        self.suggestions = results
        if not results:
            self._close_dropdown()
            return
        # Build / refresh dropdown
        if self._dropdown is None:
            self._dropdown = DropDown(auto_width=False, width=Window.width - dp(36))
        self._dropdown.clear_widgets()
        for r in results:
            btn = PillButton(text=r["label"], bg_color=SWITCH_BLUE,
                             size_hint_y=None, height=dp(56))
            btn.bind(on_release=lambda b, label=r["label"]: self.choose_suggestion(label))
            self._dropdown.add_widget(btn)
        try:
            anchor = self.ids.address_card
            self._dropdown.open(anchor)
        except Exception as e:
            app_logger.log_exception("home", "dropdown open failed", e)

    def _close_dropdown(self):
        if self._dropdown:
            try:
                self._dropdown.dismiss()
            except Exception:
                pass

    def choose_suggestion(self, label):
        telemetry.track("address_suggestion_picked", provider="photon")
        self.address = label
        user_prefs.update(address=label)
        self._close_dropdown()
        self._mirror_to_schedule()

    def _mirror_to_schedule(self):
        sched = self.manager.get_screen("schedule") if self.manager else None
        if sched:
            sched.address = self.address

    def save_address(self, text):
        if text and text != self.address:
            self.address = text
        user_prefs.update(address=self.address)
        self._mirror_to_schedule()

    def use_current_location(self):
        telemetry.track("location_requested")
        self.locating = "Locating..."
        Thread(target=self._do_locate, daemon=True).start()

    def _on_location_status(self, state, ms, **extra):
        ui_text = {
            "waiting_permission": "Waiting for permission...",
            "locating": "Getting your location...",
            "geocoding": "Looking up address...",
            "denied": "Location denied. Type your address below.",
            "restricted": "Location restricted. Type your address below.",
            "timeout": "Location timed out. Type your address below.",
            "unsupported": "Location only works on iPhone.",
            "error": "Could not determine location.",
            "done": "",
        }.get(state, state)
        Clock.schedule_once(lambda dt: setattr(self, "locating", ui_text), 0)
        telemetry.track("location_status", state=state, ms=ms, **extra)

    def _do_locate(self):
        try:
            addr = location_service.get_current_address(status_cb=self._on_location_status)
        except Exception as e:
            app_logger.log_exception("home", "location lookup failed", e)
            addr = None
        Clock.schedule_once(lambda dt: self._apply_address(addr), 0)

    def _apply_address(self, addr):
        if addr:
            self.address = addr
            user_prefs.update(address=addr)
            self.locating = ""
            self._mirror_to_schedule()
            telemetry.track("location_result", status="ok", address=addr)
        else:
            telemetry.track("location_result", status="failed")

    def go_to(self, screen_name):
        telemetry.track("tile_tapped", id=screen_name)
        self.manager.current = screen_name


class EstimateScreen(Screen):
    job_description = StringProperty("")
    explanation = StringProperty("")
    confidence = StringProperty("")
    cost_low = NumericProperty(0)
    cost_high = NumericProperty(0)
    refined_context = StringProperty("")
    refinement_round = NumericProperty(0)
    questions = ListProperty([])

    def on_pre_enter(self):
        telemetry.track("screen_changed", to="estimate")

    def get_estimate(self):
        if not self.job_description.strip():
            self.explanation = "Please describe the electrical work needed."
            return
        self.explanation = "Getting estimate..."
        self.refined_context = ""
        self.refinement_round = 0
        Clock.schedule_once(lambda dt: self._fetch_estimate(), 0.05)

    def _fetch_estimate(self):
        full_desc = self.job_description
        if self.refined_context:
            full_desc += "\n\nAdditional context:\n" + self.refined_context
        try:
            telemetry.track("estimate_requested",
                            description_len=len(full_desc),
                            round=self.refinement_round)
            estimator = App.get_running_app().ai_estimator
            result = estimator.get_estimate(full_desc)
            self._apply_result(result)
        except Exception as e:
            app_logger.log_exception("estimate", "fetch failed", e)
            self.explanation = f"Error: {e}"

    def _apply_result(self, result):
        cost = result.get("estimated_cost") or 0
        low = result.get("cost_range_low") or int(cost * 0.7) or 150
        high = result.get("cost_range_high") or int(cost * 1.5) or 800
        if cost <= 0:
            cost = (low + high) // 2

        self.cost_low = low
        self.cost_high = high
        self.confidence = (result.get("confidence") or "medium").upper()
        self.explanation = result.get("explanation") or ""
        self.questions = result.get("clarifying_questions") or []

        App.get_running_app().current_estimate = {
            "estimated_cost": cost,
            "cost_range_low": low,
            "cost_range_high": high,
            "confidence": self.confidence,
            "description": self.job_description + (
                "\n" + self.refined_context if self.refined_context else ""),
        }
        telemetry.track("estimate_returned", cost=cost, low=low, high=high,
                        confidence=self.confidence,
                        question_count=len(self.questions),
                        provider=App.get_running_app().ai_estimator.provider)
        self._render_questions()

    def _render_questions(self):
        container = self.ids.get("questions_box") if hasattr(self, "ids") else None
        if container is None:
            return
        container.clear_widgets()
        if not self.questions:
            return
        from kivy.uix.label import Label as KLabel
        for q in self.questions[:3]:
            qlabel = KLabel(
                text=q.get("question", ""), color=NAVY, font_size=dp(18),
                bold=True, size_hint_y=None, halign="left", valign="middle",
                text_size=(Window.width - dp(40), None))
            qlabel.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1] + dp(6)))
            container.add_widget(qlabel)

            for opt in q.get("options", [])[:4]:
                colors = [SWITCH_BLUE, MARIO_YELLOW, LUIGI_GREEN, STAR_PURPLE]
                color = colors[len(container.children) % len(colors)]
                btn = PillButton(text=opt["label"], bg_color=color,
                                 size_hint_y=None, height=dp(54), font_size=dp(17))
                btn.bind(on_release=lambda b, ctx=opt["context"], qst=q["question"], lbl=opt["label"]:
                         self.refine(qst, lbl, ctx))
                container.add_widget(btn)

    def refine(self, question, answer_label, context):
        if self.refinement_round >= 3:
            self.explanation = "Range tightened. Tap Schedule to proceed."
            return
        self.refinement_round += 1
        self.refined_context += f"\n- {question} -> {context}"
        telemetry.track("estimate_refined",
                        round=self.refinement_round,
                        question=question[:120], answer=answer_label[:60])
        self.explanation = "Updating estimate..."
        Clock.schedule_once(lambda dt: self._fetch_estimate(), 0.05)

    def proceed_to_schedule(self):
        if self.cost_low > 0:
            telemetry.track("schedule_from_estimate")
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
        # Today plus next 14 days
        self.available_dates = [
            (today + timedelta(days=i)).strftime("%A, %b %d")
            for i in range(0, 15)
        ]
        # Default to today if not already chosen
        if self.selected_date == "Select Date":
            self.selected_date = self.available_dates[0]
        # Default time to next hour within service window (8 AM - 5 PM)
        if self.selected_time == "Select Time":
            next_hour = today.hour + 1
            if next_hour < 8:
                next_hour = 8
            if next_hour > 17:
                # Past end of service hours -> first slot tomorrow
                self.selected_date = self.available_dates[1] if len(self.available_dates) > 1 else self.available_dates[0]
                next_hour = 8
            # Format same way as values list ("8:00 AM", "1:00 PM" etc.)
            suffix = "AM" if next_hour < 12 else "PM"
            display = next_hour if next_hour <= 12 else next_hour - 12
            self.selected_time = f"{display}:00 {suffix}"
        prefs = user_prefs.load()
        if not self.address and prefs.get("address"):
            self.address = prefs["address"]
        if not self.phone and prefs.get("phone"):
            self.phone = prefs["phone"]
        telemetry.track("screen_changed", to="schedule",
                        default_date=self.selected_date,
                        default_time=self.selected_time)

    payment_status = StringProperty("")
    payment_polling = BooleanProperty(False)

    def confirm_booking(self):
        if not self.address.strip():
            self._popup("Hold up", "Please enter your address.")
            return
        if not self.phone.strip():
            self._popup("Hold up", "Please enter your phone number.")
            return
        if self.selected_date == "Select Date":
            self._popup("Hold up", "Please pick a date.")
            return
        if self.selected_time == "Select Time":
            self._popup("Hold up", "Please pick a time.")
            return

        user_prefs.update(address=self.address, phone=self.phone)
        app = App.get_running_app()
        estimate = getattr(app, "current_estimate", {})
        cost_cents = int((estimate.get("estimated_cost") or 0) * 100)
        if cost_cents <= 0:
            self._popup("No estimate", "Get an estimate first, then come back.")
            return

        description = f"Electrician Service - {self.selected_date}"
        telemetry.track("payment_started", cost_cents=cost_cents,
                        date=self.selected_date, time=self.selected_time)
        self.payment_status = "Opening Whop checkout..."
        result = applepay.preauthorize(cost_cents, description)

        if result.get("error") or result.get("status") == "failed":
            err = result.get("error") or "Payment failed"
            telemetry.track("payment_error", message=err)
            self.payment_status = ""
            self._popup("Payment Error", err)
            return

        # The webview is now open. We DON'T treat this as success - we wait
        # for Whop to report a real completed payment. Poll their API in a
        # background thread.
        plan_id = result.get("plan_id")
        checkout_id = result.get("checkout_id")
        telemetry.track("payment_webview_opened",
                        plan_id=plan_id, checkout_id=checkout_id)

        if not plan_id:
            self.payment_status = ""
            self._popup("Cannot verify payment",
                        "We couldn't identify the checkout. If you completed payment, contact support with your bank receipt.")
            return

        booking = {
            "date": self.selected_date, "time": self.selected_time,
            "address": self.address, "phone": self.phone,
            "estimate": estimate, "checkout_id": checkout_id,
            "plan_id": plan_id, "payment_status": "awaiting_completion",
            "started_at": int(time.time()),
        }
        app.bookings.append(booking)
        self.payment_polling = True
        self.payment_status = "Complete payment in the Whop window, then return here."
        Thread(target=self._poll_payment, args=(booking,), daemon=True).start()

    def _poll_payment(self, booking):
        """Poll Whop API for up to 90s looking for a completed payment."""
        import whop_payment
        deadline = time.time() + 90
        attempts = 0
        while time.time() < deadline and self.payment_polling:
            attempts += 1
            try:
                paid = whop_payment.find_completed_payment(
                    booking["plan_id"], booking["started_at"])
            except Exception as e:
                app_logger.log_exception("schedule", "poll raised", e)
                paid = None
            if paid:
                booking["payment_status"] = "paid"
                booking["payment_id"] = paid.get("id")
                telemetry.track("payment_succeeded",
                                payment_id=paid.get("id"),
                                attempts=attempts)
                Clock.schedule_once(lambda dt: self._on_paid(), 0)
                return
            telemetry.track("payment_poll_pending", attempts=attempts)
            time.sleep(5)

        # Either user cancelled or we timed out without finding a payment
        if not self.payment_polling:
            # cancelled
            telemetry.track("payment_polling_cancelled", attempts=attempts)
            return
        booking["payment_status"] = "not_completed"
        telemetry.track("payment_not_completed", attempts=attempts)
        Clock.schedule_once(lambda dt: self._on_not_paid(), 0)

    def _on_paid(self):
        self.payment_polling = False
        self.payment_status = ""
        self._popup("Booked!",
                    f"Payment received. You're scheduled for {self.selected_date} at {self.selected_time}.")
        self.manager.current = "home"

    def _on_not_paid(self):
        self.payment_polling = False
        self.payment_status = ""
        self._popup("Payment not received",
                    "We didn't see a completed payment from Whop. If you tapped Pay "
                    "and it succeeded, tap 'I Paid Anyway' below and we'll verify. "
                    "Otherwise, try again.")

    def _popup(self, title, msg):
        content = BoxLayout(orientation="vertical", padding=dp(15), spacing=dp(15))
        content.add_widget(Label(text=msg, font_size=dp(19), color=NAVY,
                                 text_size=(dp(280), None), halign="center"))
        btn = PillButton(text="OK", bg_color=SWITCH_BLUE,
                         size_hint_y=None, height=dp(54), font_size=dp(20))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.9, 0.5),
                      title_size=dp(20))
        btn.bind(on_release=popup.dismiss)
        popup.open()


class BookingsScreen(Screen):
    def on_pre_enter(self):
        telemetry.track("screen_changed", to="bookings")


class ChatScreen(Screen):
    chat_history = StringProperty("")
    user_message = StringProperty("")

    def on_pre_enter(self):
        telemetry.track("screen_changed", to="chat")

    def send_message(self):
        if not self.user_message.strip():
            return
        self.chat_history += f"\n[You]: {self.user_message}\n"
        question = self.user_message
        self.user_message = ""
        Clock.schedule_once(lambda dt: self._get_response(question), 0.05)

    def _get_response(self, question):
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
        # Start telemetry pipeline early
        telemetry.start()
        telemetry.install_excepthook()
        telemetry.track("app_started", app_version=telemetry.APP_VERSION)

        self.ai_estimator = AIEstimator()
        app_logger.log("app", "started", provider=self.ai_estimator.provider)

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
            low = self.current_estimate.get("cost_range_low", 0)
            high = self.current_estimate.get("cost_range_high", 0)
            if low and high:
                return f"Estimate: ${low:,} - ${high:,}"
        return ""


if __name__ == "__main__":
    ElectriciansNowApp().run()
