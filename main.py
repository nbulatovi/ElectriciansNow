from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.core.window import Window
import applepay

# Set a fixed window size for testing on desktop (remove when testing on iOS)
Window.size = (400, 600)

class HelloWorldScreen(BoxLayout):
    pass

class HelloWorldApp(App):
    def build(self):
        return HelloWorldScreen()
    def on_button_press(self):
        print("Button was pressed!")
        applepay.preauthorize(12000, "Electrician Services")

if __name__ == '__main__':
    HelloWorldApp().run()
 