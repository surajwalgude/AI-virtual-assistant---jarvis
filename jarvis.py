import os
import sys
import time
import json
import threading
import webbrowser
import subprocess
import cv2
import urllib.parse
import requests
import pyttsx3
import speech_recognition as sr
import pywhatkit as kit
import customtkinter as ctk
from datetime import datetime, timedelta

# Advanced automation utilities
import pyautogui  
try:
    import psutil  
except ImportError:
    psutil = None

try:
    from AppOpener import open as launch_app
except ImportError:
    launch_app = None

# Free translation module addition
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

# ==========================================
# CONFIGURATION & INITIALIZATION
# ==========================================
WEATHER_API_KEY = "d9270230628440ee5978ba2eebf59f46" 
NEWS_API_KEY = "44161ada51d3484597256ea1f466b17f"    
DEFAULT_CITY = "Delhi"  # Fallback home city if no city is specified in the command
STORAGE_FILE = "history_storage.json" 
SNAPSHOT_DIR = "jarvis_snapshots"      

if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ChatGPTJarvisGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Jarvis AI Chat")
        self.geometry("950x670")
        self.resizable(True, True)
        self.configure(fg_color="#202123") 

        # --- CONTROLLER FLAGS ---
        self.is_speaking = False 
        self.wake_word_active = True 

        # --- LOAD DATA HISTORY ---
        self.chat_sessions = {}
        self.session_titles = {} 
        self.session_timestamps = {} 
        self.load_history_from_file()
        
        if not self.chat_sessions:
            self.current_session_id = "sess_init"
            self.chat_sessions[self.current_session_id] = "🤖 SYSTEM ENGINE\nSystems successfully initiated. Hello, how can I help you today?\n"
            self.session_titles[self.current_session_id] = "System Start"
            self.session_timestamps[self.current_session_id] = time.time()
        else:
            self.current_session_id = list(self.chat_sessions.keys())[-1]

        # --- GRID SYSTEM ARRANGEMENT ---
        self.grid_columnconfigure(0, weight=1) 
        self.grid_columnconfigure(1, weight=3) 
        self.grid_rowconfigure(0, weight=1)

        # 📂 SIDEBAR CONTAINER
        self.sidebar = ctk.CTkFrame(self, fg_color="#202123", width=260, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        self.new_chat_btn = ctk.CTkButton(self.sidebar, text="➕ New Chat Engine", font=ctk.CTkFont(size=13, weight="bold"), height=40, fg_color="transparent", border_color="#4d4d4f", border_width=1, hover_color="#2A2B32", anchor="w", command=self.create_new_session)
        self.new_chat_btn.pack(fill="x", padx=15, pady=(20, 15))
        
        ctk.CTkLabel(self.sidebar, text="📌 SHORT DATA LOGS (30 DAYS)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9A9DB0").pack(padx=20, pady=(10, 5), anchor="w")
        
        self.history_scroll_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", height=300, width=230)
        self.history_scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 📊 TELEMETRY DASHBOARD PANEL
        self.telemetry_frame = ctk.CTkFrame(self.sidebar, fg_color="#1E1F22", height=90, corner_radius=8)
        self.telemetry_frame.pack(fill="x", padx=15, pady=(5, 5))
        
        self.cpu_label = ctk.CTkLabel(self.telemetry_frame, text="CPU Usage: --%", font=ctk.CTkFont(size=11, weight="bold"), text_color="#10A37F")
        self.cpu_label.pack(anchor="w", padx=12, pady=(6, 2))
        self.ram_label = ctk.CTkLabel(self.telemetry_frame, text="RAM Usage: --%", font=ctk.CTkFont(size=11, weight="bold"), text_color="#10A37F")
        self.ram_label.pack(anchor="w", padx=12, pady=2)
        self.battery_label = ctk.CTkLabel(self.telemetry_frame, text="Battery: --%", font=ctk.CTkFont(size=11, weight="bold"), text_color="#10A37F")
        self.battery_label.pack(anchor="w", padx=12, pady=(2, 6))
        
        self.action_btn = ctk.CTkButton(self.sidebar, text="🎙️ Tap to Speak", font=ctk.CTkFont(size=13, weight="bold"), height=40, fg_color="#10A37F", hover_color="#1A7F64", command=self.trigger_manual_listen)
        self.action_btn.pack(side="bottom", fill="x", padx=15, pady=20)

        # 💬 MAIN CHAT CANVAS AREA
        self.chat_area = ctk.CTkFrame(self, fg_color="#343541", corner_radius=0) 
        self.chat_area.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.chat_area.grid_rowconfigure(0, weight=1)
        self.chat_area.grid_columnconfigure(0, weight=1)

        self.console = ctk.CTkTextbox(self.chat_area, font=ctk.CTkFont(size=14, family="Segoe UI"), fg_color="#343541", text_color="#ECECF1", border_width=0, wrap="word")
        self.console.grid(row=0, column=0, sticky="nsew", padx=30, pady=(20, 10))
        
        self.refresh_chat_display()

        # Bottom Input Area
        self.input_container = ctk.CTkFrame(self.chat_area, fg_color="transparent")
        self.input_container.grid(row=1, column=0, sticky="ew", padx=30, pady=(10, 25))
        
        self.entry_box = ctk.CTkEntry(self.input_container, placeholder_text="Send a message or type a command... (Press Enter)", font=ctk.CTkFont(size=14), fg_color="#40414F", border_color="#565869", text_color="#FFFFFF", height=48, corner_radius=8, border_width=1)
        self.entry_box.pack(fill="x", side="left", expand=True)
        self.entry_box.bind("<Return>", self.process_typed_command)

        self.rebuild_history_sidebar()

        # Threads
        threading.Thread(target=self.start_jarvis_sequence, daemon=True).start()
        threading.Thread(target=self.update_telemetry_loop, daemon=True).start()
        threading.Thread(target=self.background_wake_word_loop, daemon=True).start()

    def background_wake_word_loop(self):
        r = sr.Recognizer()
        while self.wake_word_active:
            if not self.is_speaking:
                with sr.Microphone() as source:
                    r.pause_threshold = 0.6
                    r.adjust_for_ambient_noise(source, duration=0.3)
                    try:
                        audio = r.listen(source, timeout=3, phrase_time_limit=4)
                        phrase = r.recognize_google(audio, language='en-in').lower()
                        if "hey jarvis" in phrase or "jarvis" in phrase:
                            self.trigger_manual_listen()
                    except Exception:
                        pass
            time.sleep(0.5)

    def update_telemetry_loop(self):
        while True:
            if psutil:
                try:
                    cpu = psutil.cpu_percent(interval=None)
                    ram = psutil.virtual_memory().percent
                    battery_info = psutil.sensors_battery()
                    
                    if battery_info:
                        bat_str = f"{battery_info.percent}% {'(Charging)' if battery_info.power_plugged else '(Discharging)'}"
                    else:
                        bat_str = "N/A"
                        
                    self.cpu_label.configure(text=f"CPU Usage: {cpu}%")
                    self.ram_label.configure(text=f"RAM Usage: {ram}%")
                    self.battery_label.configure(text=f"Battery: {bat_str}")
                except Exception:
                    pass
            time.sleep(2.5)

    def save_history_to_file(self):
        try:
            payload = {
                "chat_sessions": self.chat_sessions,
                "session_titles": self.session_titles,
                "session_timestamps": self.session_timestamps
            }
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Failed to record data index to disk: {e}")

    def load_history_from_file(self):
        if not os.path.exists(STORAGE_FILE):
            return
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            raw_sessions = payload.get("chat_sessions", {})
            raw_titles = payload.get("session_titles", {})
            raw_timestamps = payload.get("session_timestamps", {})
            one_month_ago = (datetime.now() - timedelta(days=30)).timestamp()
            
            for sess_id, ts in raw_timestamps.items():
                if ts >= one_month_ago:  
                    self.chat_sessions[sess_id] = raw_sessions[sess_id]
                    self.session_titles[sess_id] = raw_titles[sess_id]
                    self.session_timestamps[sess_id] = ts
            if len(raw_sessions) != len(self.chat_sessions):
                self.save_history_to_file()
        except Exception as e:
            print(f"Data conversion array corrupted: {e}")

    def write_message(self, sender, text):
        formatted_chunk = f"\n🤖 {sender.upper()}\n{text}\n"
        self.chat_sessions[self.current_session_id] += formatted_chunk
        self.session_timestamps[self.current_session_id] = time.time()
        
        if self.session_titles[self.current_session_id].startswith("Session") and sender.lower().startswith("you"):
            short_title = text[:18] + "..." if len(text) > 18 else text
            self.session_titles[self.current_session_id] = short_title.capitalize()
            self.rebuild_history_sidebar()

        self.refresh_chat_display()
        self.save_history_to_file()  

    def refresh_chat_display(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.insert("end", self.chat_sessions[self.current_session_id])
        self.console.configure(state="disabled")
        self.console.see("end")

    def rebuild_history_sidebar(self):
        for widget in self.history_scroll_frame.winfo_children():
            widget.destroy()
        for sess_id in reversed(list(self.chat_sessions.keys())):
            is_active = (sess_id == self.current_session_id)
            display_name = self.session_titles[sess_id]
            btn = ctk.CTkButton(
                self.history_scroll_frame, 
                text=f"💬 {display_name}", 
                font=ctk.CTkFont(size=12),
                height=35,
                anchor="w",
                fg_color="#2A2B32" if is_active else "transparent",
                text_color="#FFFFFF" if is_active else "#C5C5D2",
                hover_color="#2A2B32",
                command=lambda s=sess_id: self.switch_active_session(s)
            )
            btn.pack(fill="x", pady=2, padx=5)

    def create_new_session(self):
        new_id = f"sess_{int(time.time())}"
        self.current_session_id = new_id
        self.chat_sessions[new_id] = "🤖 SYSTEM ENGINE\nNew clean chat session open. Ready for inputs.\n"
        self.session_titles[new_id] = f"Session {len(self.chat_sessions) + 1}"
        self.session_timestamps[new_id] = time.time()
        self.refresh_chat_display()
        self.rebuild_history_sidebar()
        self.save_history_to_file()

    def switch_active_session(self, target_session_id):
        self.current_session_id = target_session_id
        self.refresh_chat_display()
        self.rebuild_history_sidebar()

    def set_gui_state(self, state_mode):
        if state_mode == "speaking":
            self.action_btn.configure(text="🔊 Jarvis Speaking...", fg_color="#10A37F")
            self.console.configure(text_color="#A9F5D0")  
        elif state_mode == "listening":
            self.action_btn.configure(text="🎙️ Listening...", fg_color="#D1A119")
            self.console.configure(text_color="#FCE4A6")  
        elif state_mode == "processing":
            self.action_btn.configure(text="⚙️ Processing...", fg_color="#2A2B32")
            self.console.configure(text_color="#ECECF1")  
        else:
            self.action_btn.configure(text="🎙️ Tap to Speak", fg_color="#10A37F")
            self.console.configure(text_color="#ECECF1")

    def speak(self, text):
        self.is_speaking = True 
        self.set_gui_state("speaking")
        self.write_message("Jarvis", text)
        
        try:
            threading_engine = pyttsx3.init('sapi5' if sys.platform == "win32" else None)
            voices = threading_engine.getProperty('voices')
            if voices:
                threading_engine.setProperty('voice', voices[0].id)
            threading_engine.setProperty('rate', 185)
            threading_engine.say(text)
            threading_engine.runAndWait()
        except Exception as e:
            print(f"TTS Thread Exception caught: {e}")
            
        self.is_speaking = False
        self.set_gui_state("idle")

    def listen(self):
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.pause_threshold = 0.8
            r.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = r.listen(source, timeout=4, phrase_time_limit=7)
            except Exception:
                return "none"
        try:
            query = r.recognize_google(audio, language='en-in')
            self.write_message("You (Voice)", query)
            return query.lower()
        except Exception:
            return "none"

    def trigger_manual_listen(self):
        def voice_worker():
            self.set_gui_state("listening")
            query = self.listen()
            self.set_gui_state("processing")
            if query != "none" and query:
                self.execute_action(query)
            self.set_gui_state("idle")
        threading.Thread(target=voice_worker, daemon=True).start()

    def process_typed_command(self, event=None):
        query = self.entry_box.get().strip().lower()
        if query:
            self.entry_box.delete(0, "end")
            self.write_message("You", query)
            def manual_worker():
                self.set_gui_state("processing")
                self.execute_action(query)
                self.set_gui_state("idle")
            threading.Thread(target=manual_worker, daemon=True).start()

    def perform_deep_search(self, topic):
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(topic)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(res.text, 'html.parser')
                snippets = [a.text.strip() for a in soup.find_all('a', class_='result__snippet')[:3]]
                if snippets:
                    return f"Deep Analytics Report for '{topic}':\n\n" + "\n\n".join(snippets)
            return "Unable to securely parse structural snippet components from web indices."
        except Exception:
            return "Deep Search interface connection structural timeout."

    def create_local_file(self, content_intent):
        try:
            filename = f"jarvis_output_{int(time.time())}.txt"
            if "python" in content_intent or "script" in content_intent:
                filename = filename.replace(".txt", ".py")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content_intent)
            self.speak(f"Operational data matrix committed to local workspace file named: {filename}")
        except Exception as e:
            self.speak(f"File system operational creation array exception: {str(e)}")

    def face_unlock(self):
        try:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            cap = cv2.VideoCapture(0)
            if not cap.isOpened(): cap = cv2.VideoCapture(1)
            if not cap.isOpened(): return False
            time.sleep(0.5)
            start_time = time.time()
            authenticated = False
            while time.time() - start_time < 5:
                ret, frame = cap.read()
                if not ret: break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                if len(faces) > 0:
                    authenticated = True
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    cv2.imwrite(f"{SNAPSHOT_DIR}/login_{timestamp}.jpg", frame)
                    break
            cap.release()
            cv2.destroyAllWindows()
            return authenticated
        except Exception:
            return False

    def take_manual_photo(self):
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened(): cap = cv2.VideoCapture(1)
            if not cap.isOpened():
                self.speak("Webcam peripheral arrays are inaccessible.")
                return
            time.sleep(0.4)
            ret, frame = cap.read()
            cap.release()
            if ret:
                filename = f"{SNAPSHOT_DIR}/snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(filename, frame)
                self.speak(f"Photo captured successfully at {filename}.")
            else:
                self.speak("Failed to process imaging buffer pipeline.")
        except Exception as e:
            self.speak(f"Imaging pipeline error: {str(e)}")

    def get_news(self, zone="world"):
        if zone == "india":
            url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={NEWS_API_KEY}"
            prefix = "Here are the latest live headlines from India:\n\n• "
        else:
            url = f"https://newsapi.org/v2/top-headlines?language=en&apiKey={NEWS_API_KEY}"
            prefix = "Here are the top global updates from around the world:\n\n• "
            
        try:
            res = requests.get(url, timeout=5).json()
            articles = res.get("articles", [])
            if not articles:
                return f"No live news updates discovered for your {zone} tracking arrays."
            
            headlines = [art['title'] for art in articles[:4] if art.get('title')]
            return prefix + "\n• ".join(headlines)
        except Exception:
            return f"Failed to contact live {zone} news broadcasting registries."

    def get_weather(self, city):
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        try:
            res = requests.get(url).json()
            if res.get("cod") != "404" and res.get("cod") != 404:
                return f"The current weather in {city.capitalize()} is {res['main']['temp']}°C with {res['weather'][0]['description']}."
            return f"Location '{city}' could not be matched in meteorological databases."
        except Exception:
            return "Weather telemetry networks offline."

    # ==========================================================
    # ⚡ UPDATED FEATURE: DYNAMIC CITY DAILY BRIEFING ENGINE
    # ==========================================================
    def get_daily_update(self, city=None):
        # Fallback to standard tracking default if no specific city argument passed
        target_city = city if city else DEFAULT_CITY
        
        self.speak(f"Compiling comprehensive matrix briefing arrays for {target_city.capitalize()}...")
        
        # 1. Date-Time Vector
        time_now = datetime.now().strftime('%I:%M %p')
        date_today = datetime.now().strftime('%A, %B %d, %Y')
        
        # 2. Extract Weather Telemetry
        weather_report = self.get_weather(target_city)
        
        # 3. Extract Global Headlines Array
        news_report = self.get_news(zone="world")
        
        # 4. Construct Canvas Manifest
        briefing_data = (
            f"📋 --- DAILY SYSTEM BRIEFING MANIFEST ---\n\n"
            f"📅 Temporal Date: {date_today}\n"
            f"⏰ Current System Time: {time_now}\n\n"
            f"🌤️ Target Weather Vector ({target_city.capitalize()}):\n   -> {weather_report}\n\n"
            f"{news_report}\n"
            f"----------------------------------------"
        )
        
        # Update Chat Display & Announce Highlight Summary
        self.write_message("Jarvis", briefing_data)
        self.speak(f"Briefing complete. Today is {date_today}. The weather outlook in {target_city.capitalize()} has been processed. Reading news headlines now.")

    def file_search(self, filename):
        self.speak(f"Searching storage arrays for: {filename}...")
        search_path = os.path.expanduser("~") 
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if filename in file.lower():
                    full_path = os.path.join(root, file)
                    self.speak(f"File located. Opening {file} now.")
                    if sys.platform == "win32": os.startfile(full_path)
                    else: subprocess.call(["open", full_path])
                    return
        self.speak("No matching files discovered.")

    def execute_action(self, query):
        if "translate " in query or "translation " in query:
            if not GoogleTranslator:
                self.speak("Translation engine library component is missing. Please run pip install deep-translator.")
                return
            
            target_phrase = query.replace("translate", "").replace("translation", "").strip()
            if not target_phrase:
                self.speak("Data input buffer empty. State a phrase to translate.")
                return
                
            try:
                translated_text = GoogleTranslator(source='auto', target='en').translate(target_phrase)
                self.speak(f"Translation complete: {translated_text.capitalize()}")
            except Exception:
                self.speak("Translation execution failed.")
            return

        if "time" in query and "what" in query:
            self.speak(f"The local system time is currently {datetime.now().strftime('%I:%M %p')}.")
            return
        elif "date" in query and "what" in query:
            self.speak(f"Today's date is {datetime.now().strftime('%A, %B %d, %Y')}.")
            return

        # ==========================================================
        # ⚡ UPDATED ENGINE TRIGGER: SEARCH CITY NAME FROM BRIEFING
        # ==========================================================
        elif "daily update" in query or "morning briefing" in query or "status update" in query:
            extracted_city = None
            # Scan structural command phrases for string segmentation hooks
            for separator in ["for ", "in ", "about "]:
                if separator in query:
                    parts = query.split(separator)
                    if len(parts) > 1:
                        potential_city = parts[-1].strip()
                        if potential_city:
                            extracted_city = potential_city
                            break
            
            # Pass targeted city directly into update compiler
            self.get_daily_update(city=extracted_city)
            return

        elif "shutdown computer" in query or "shutdown the pc" in query or "power off computer" in query:
            self.speak("Initiating system shutdown sequence. Finalizing background operational arrays.")
            if sys.platform == "win32": os.system("shutdown /s /t 10")  
            elif sys.platform == "darwin": os.system("sudo shutdown -h now")
            else: os.system("shutdown -h now")
            return

        elif "restart computer" in query or "reboot the pc" in query or "restart the system" in query:
            self.speak("Initiating system restart core directive. Rebooting mainframe arrays.")
            if sys.platform == "win32": os.system("shutdown /r /t 10")
            elif sys.platform == "darwin": os.system("sudo shutdown -r now")
            else: os.system("shutdown -h now")
            return

        elif "volume up" in query or "increase volume" in query or "raise volume" in query:
            self.speak("Increasing master system audio output registry.")
            pyautogui.press("volumeup", presses=5)
            return
        elif "volume down" in query or "decrease volume" in query or "lower volume" in query:
            self.speak("Lowering system master speaker volume output metrics.")
            pyautogui.press("volumedown", presses=5)
            return
        elif "mute volume" in query or "mute audio" in query or "unmute" in query:
            self.speak("Toggling hardware mute configuration.")
            pyautogui.press("volumemute")
            return

        elif "create a file" in query or "write a script" in query or "create script" in query:
            target_content = query.replace("create a file", "").replace("write a script", "").strip()
            self.create_local_file(target_content if target_content else "Jarvis System Output Content Matrix.")
            return

        elif "deep search for" in query or "deep research" in query:
            search_target = query.replace("deep search for", "").replace("deep research", "").strip()
            self.speak("Invoking structural query scraper. Compiling results...")
            report = self.perform_deep_search(search_target)
            self.speak("Analytics compilation active. Rendering data block.")
            self.write_message("Jarvis", report)
            return

        elif "minimize all windows" in query or "minimize windows" in query:
            self.speak("Minimizing active workspace displays.")
            pyautogui.hotkey('win', 'd')
            return
        elif "take a screenshot" in query or "capture screen" in query:
            self.speak("Capturing screenshot.")
            screenshot_file = f"{SNAPSHOT_DIR}/screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot(screenshot_file)
            self.speak(f"Screenshot written to {screenshot_file}.")
            return
        elif "lock my pc" in query or "lock the computer" in query:
            self.speak("Securing workstation endpoint structure now.")
            if sys.platform == "win32":
                import ctypes; ctypes.windll.user32.LockWorkStation()
            else:
                os.system('xdg-screensaver lock' if sys.platform != "darwin" else 'pmset displaysleepnow')
            return

        elif "pause music" in query or "pause video" in query or "pause" in query and ("song" in query or "music" in query):
            self.speak("Pausing playback.")
            pyautogui.press('playpause')
            return
        elif "next song" in query or "skip music" in query or "next track" in query:
            self.speak("Skipping to next media track item.")
            pyautogui.press('nexttrack')
            return

        elif "open google" in query:
            self.speak("Opening Google.")
            webbrowser.open("https://google.com")
        elif "search web for" in query:
            search_query = query.replace("search web for", "").strip()
            self.speak(f"Searching web indexes for: {search_query}")
            webbrowser.open(f"https://www.google.com/search?q={search_query}")
        elif "take a photo" in query or "capture snapshot" in query or "take photo" in query:
            self.speak("Activating operational camera grid. Stand still.")
            self.take_manual_photo()
        elif "play music" in query or "play on youtube" in query:
            song = query.replace("play music", "").replace("play on youtube", "").strip()
            if "0.25" in query or "timestamp" in query:
                self.speak(f"Playing {song} on YouTube from designated timestamp.")
                webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}&t=15s")
            else:
                self.speak(f"Playing {song} on YouTube.")
                kit.playonyt(song)
        elif "weather in" in query:
            city = query.split("weather in")[-1].strip()
            self.speak(self.get_weather(city))
        elif "find file" in query:
            file_name = query.replace("find file", "").strip()
            self.file_search(file_name)
        elif "navigate from" in query or "directions from" in query:
            try:
                clean_query = query.replace("navigate from", "").replace("directions from", "").strip()
                parts = clean_query.split(" to ")
                webbrowser.open(f"https://www.google.com/maps/dir/{urllib.parse.quote(parts[0].strip())}/{urllib.parse.quote(parts[1].strip())}")
                self.speak(f"Calculating route map from {parts[0]} to {parts[1]}.")
            except Exception: self.speak("Could not parse map coordinates cleanly.")
        elif "navigate to" in query or "directions to" in query:
            destination = query.replace("navigate to", "").replace("directions to", "").strip()
            webbrowser.open(f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(destination)}")
            self.speak(f"Opening navigation systems routing toward {destination}.")
        elif "show map of" in query or "map of" in query:
            location = query.replace("show map of", "").replace("map of", "").strip()
            webbrowser.open(f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(location)}")
            self.speak(f"Pulling map layouts for {location}.")
        elif "open application" in query or "open" in query:
            app_target = query.replace("open application", "").replace("open", "").strip().lower()
            if app_target == "notepad":
                self.speak("Opening Notepad."); subprocess.Popen(["notepad.exe"])
            elif app_target in ["calc", "calculator"]:
                self.speak("Opening Calculator."); subprocess.Popen(["calc.exe"])
            elif app_target in ["cmd", "command prompt"]:
                self.speak("Opening Command Prompt."); subprocess.Popen(["cmd.exe"])
            elif launch_app:
                self.speak(f"Invoking application handler for {app_target}.")
                try: launch_app(app_target, match_closest=True)
                except Exception: self.speak(f"Could not open {app_target}. Try using its precise system name.")
            else: self.speak("AppOpener engine is missing.")
        elif "go to sleep" in query or "exit" in query:
            self.speak("Powering down system. Goodbye.")
            self.quit()

        elif "indian news" in query or "india news" in query or "news from india" in query:
            self.speak(self.get_news(zone="india"))
        elif "world news" in query or "global news" in query or "latest news" in query:
            self.speak(self.get_news(zone="world"))

        elif "wikipedia" in query or "wiki" in query:
            search_query = query.replace("search wikipedia for", "").replace("wikipedia summary", "").replace("wikipedia search", "").replace("wikipedia", "").replace("wiki", "").strip()
            if not search_query:
                self.speak("Wikipedia search mode active. What topic should I access summaries for?")
                return
            
            self.speak(f"Querying Wikipedia real-time summaries for {search_query}...")
            headers = {"User-Agent": "JarvisAI/1.0 (Desktop Assistant)"}
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(search_query)}"
            
            try:
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    summary = response.json().get("extract", "")
                    if len(summary) > 450:
                        summary = summary[:450] + "..."
                    self.write_message("Jarvis", f"📚 WIKIPEDIA CORE LOG ({search_query.upper()}):\n\n{summary}")
                    self.speak(summary)
                else:
                    search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(search_query)}&limit=1&namespace=0&format=json"
                    search_response = requests.get(search_url, headers=headers, timeout=5)
                    if search_response.status_code == 200:
                        search_results = search_response.json()
                        if search_results[1]:  
                            closest_match = search_results[1][0]
                            self.speak(f"Exact registry empty. Parsing variation database for: {closest_match}...")
                            retry_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(closest_match)}"
                            retry_res = requests.get(retry_url, headers=headers, timeout=5)
                            if retry_res.status_code == 200:
                                summary = retry_res.json().get("extract", "")
                                if len(summary) > 450:
                                    summary = summary[:450] + "..."
                                self.write_message("Jarvis", f"📚 WIKIPEDIA MATCH LOG ({closest_match.upper()}):\n\n{summary}")
                                self.speak(summary)
                                return
                    self.speak(f"No database information matches your parameter query: '{search_query}'.")
            except Exception:
                self.speak("Wikipedia communication link network timeout.")
            return

        else:
            if any(x in query for x in ["hello", "hi", "hey"]): 
                self.speak("Hello! How can I help you today?")
            elif "who are you" in query: 
                self.speak("I am Jarvis, your virtual desktop assistant.")
            else:
                try:
                    search_query = query.replace("what is", "").replace("who is", "").strip()
                    if not search_query: search_query = query
                    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(search_query)}"
                    headers = {"User-Agent": "JarvisAI/1.0 (Desktop Assistant)"}
                    response = requests.get(url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        summary = response.json().get("extract", "")
                        if len(summary) > 400: summary = summary[:400] + "..."
                        self.speak(summary)
                    else:
                        self.speak(f"I could not locate any records matching '{search_query}'.")
                except Exception:
                    self.speak("An exception occurred while attempting to contact Wikipedia networks.")

    def start_jarvis_sequence(self):
        if not self.face_unlock():
            self.speak("Bio signature authentication timed out. Bypassing lock manually.")
        else:
            self.speak("Authentication complete. Systems active.")
        self.speak("Hello! How can I help you today?")

if __name__ == "__main__":
    app = ChatGPTJarvisGUI()
    app.mainloop()