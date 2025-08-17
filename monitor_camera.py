import tkinter as tk
from tkinter import messagebox, ttk
import json
import os
import cv2
import threading
import time
import subprocess
import numpy as np
import shutil
import winsound
from PIL import Image, ImageTk
import queue
import re

# --- Caminho absoluto para o config.json, garantindo que funcione de qualquer lugar ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# --- CLASSE PARA A JANELA DE CONFIGURAÇÃO INICIAL (sem alterações) ---
class SetupWindow:
    def __init__(self, parent):
        self.parent = parent
        self.config = None
        self.top = tk.Toplevel(parent)
        self.top.title("Configuração Inicial da Câmera")
        window_width, window_height = 350, 220
        screen_width, screen_height = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        x_cordinate = int((screen_width/2) - (window_width/2))
        y_cordinate = int((screen_height/2) - (window_height/2))
        self.top.geometry(f"{window_width}x{window_height}+{x_cordinate}+{y_cordinate}")
        self.top.transient(parent)
        self.top.grab_set()
        
        tk.Label(self.top, text="IP da Câmera:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.ip_entry = tk.Entry(self.top, width=30)
        self.ip_entry.grid(row=0, column=1, padx=10, pady=5)
        tk.Label(self.top, text="Usuário:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.user_entry = tk.Entry(self.top, width=30)
        self.user_entry.grid(row=1, column=1, padx=10, pady=5)
        tk.Label(self.top, text="Senha:").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.pass_entry = tk.Entry(self.top, show="*", width=30)
        self.pass_entry.grid(row=2, column=1, padx=10, pady=5)
        tk.Label(self.top, text="Porta (padrão 554):").grid(row=3, column=0, padx=10, pady=5, sticky='w')
        self.port_entry = tk.Entry(self.top, width=30)
        self.port_entry.grid(row=3, column=1, padx=10, pady=5)
        self.port_entry.insert(0, "554")
        tk.Label(self.top, text="Caminho do Stream:").grid(row=4, column=0, padx=10, pady=5, sticky='w')
        self.path_entry = tk.Entry(self.top, width=30)
        self.path_entry.grid(row=4, column=1, padx=10, pady=5)
        self.path_entry.insert(0, "onvif1")
        save_button = tk.Button(self.top, text="Salvar", command=self.save_config)
        save_button.grid(row=5, column=1, padx=10, pady=15, sticky='e')
        
    def save_config(self):
        self.config = {
            "ip": self.ip_entry.get(), "usuario": self.user_entry.get(),
            "senha": self.pass_entry.get(), "porta": self.port_entry.get() or "554",
            "stream_path": self.path_entry.get()
        }
        if not self.config['ip'] or not self.config['usuario']:
            messagebox.showwarning("Atenção", "Os campos 'IP' e 'Usuário' são obrigatórios.", parent=self.top)
            return
        with open(CONFIG_PATH, 'w', encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)
        messagebox.showinfo("Sucesso", "Configuração salva!", parent=self.top)
        self.top.destroy()

# --- FUNÇÃO PARA GERENCIAR A CONFIGURAÇÃO (sem alterações) ---
def load_or_create_config(root):
    if not os.path.exists(CONFIG_PATH):
        messagebox.showinfo("Bem-vindo!", "Arquivo 'config.json' não encontrado. Vamos configurar sua câmera.")
        setup = SetupWindow(root)
        root.wait_window(setup.top)
        return setup.config
    else:
        try:
            with open(CONFIG_PATH, 'r', encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
             messagebox.showerror("Erro", "Erro ao ler 'config.json'. Por favor, apague-o e execute novamente.")
             return None

# --- CLASSE PRINCIPAL DA APLICAÇÃO ---
class App:
    def __init__(self, window, window_title, config):
        self.window = window
        self.window.title(window_title)
        self.config = config
        
        self.monitoring_thread = None
        self.stop_event = threading.Event()
        self.last_alert_time = 0
        self.alert_cooldown = 10 
        self.frame_queue = queue.Queue(maxsize=1)
        self.detected_resolution = None

        # --- Interface Gráfica ---
        top_frame = tk.Frame(window)
        top_frame.pack(pady=10, padx=10, fill="x")

        self.status_label = tk.Label(top_frame, text="Status: Parado", font=("Helvetica", 12))
        self.status_label.pack(side="left", padx=(0, 20))

        # NOVO: Label para o contador de pessoas
        self.person_count_label = tk.Label(top_frame, text="Pessoas Detectadas: 0", font=("Helvetica", 12))
        self.person_count_label.pack(side="left")

        self.btn_start = tk.Button(top_frame, text="▶ Iniciar Monitoramento", command=self.start_monitoring)
        self.btn_start.pack(side="right", padx=5)

        self.btn_stop = tk.Button(top_frame, text="■ Parar Monitoramento", command=self.stop_monitoring, state="disabled")
        self.btn_stop.pack(side="right")

        self.video_canvas = tk.Canvas(window, width=640, height=360, bg="black")
        self.video_canvas.pack(pady=10, padx=10)
        self.video_text = self.video_canvas.create_text(320, 180, text="Vídeo aparecerá aqui", fill="white", font=("Helvetica", 14))

        audio_frame = tk.Frame(window)
        audio_frame.pack(pady=10, padx=10, fill="x")
        
        tk.Label(audio_frame, text="Volume do Alerta:").pack(side="left")
        self.volume_slider = ttk.Scale(audio_frame, from_=0, to=100, orient="horizontal")
        self.volume_slider.set(70)
        self.volume_slider.pack(side="left", fill="x", expand=True, padx=10)
        
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.update_video_canvas()

    def start_monitoring(self):
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_label.config(text="Status: Iniciando conexão...")
        self.video_canvas.delete(self.video_text)

        self.monitoring_thread = threading.Thread(target=self.object_detection_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

    def stop_monitoring(self):
        self.stop_event.set()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_label.config(text="Status: Parado")
        self.person_count_label.config(text="Pessoas Detectadas: 0")
        self.video_text = self.video_canvas.create_text(320, 180, text="Monitoramento parado", fill="white", font=("Helvetica", 14))


    def on_closing(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.stop_monitoring()
        self.window.destroy()

    def trigger_alert(self):
        current_time = time.time()
        if current_time - self.last_alert_time > self.alert_cooldown:
            self.last_alert_time = current_time
            print("ALERTA: Pessoa detectada!")
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)

    def update_video_canvas(self):
        try:
            frame = self.frame_queue.get_nowait()
            frame_resized = cv2.resize(frame, (640, 360))
            self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)))
            self.video_canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        except queue.Empty:
            pass
        
        self.window.after(100, self.update_video_canvas)

    def find_resolution_and_log(self, pipe_stderr):
        for line in iter(pipe_stderr.readline, b''):
            line_str = line.decode('utf-8', errors='ignore').strip()
            print(f"[ffmpeg] {line_str}")
            
            if self.detected_resolution is None:
                if 'Stream' in line_str and 'Video:' in line_str:
                    match = re.search(r'(\d{3,4})x(\d{3,4})', line_str)
                    if match:
                        width, height = map(int, match.groups())
                        print(f"SUCESSO: Resolução detectada automaticamente: {width}x{height}")
                        self.detected_resolution = (width, height)
        pipe_stderr.close()

    def object_detection_loop(self):
        prototxt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MobileNetSSD_deploy.prototxt')
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MobileNetSSD_deploy.caffemodel')

        if not os.path.exists(prototxt_path) or not os.path.exists(model_path):
            self.status_label.config(text="Status: Arquivos do modelo não encontrados!")
            self.stop_monitoring()
            self.window.after(0, lambda: messagebox.showerror("Erro", "Não foi possível encontrar os arquivos do modelo de IA. Baixe 'MobileNetSSD_deploy.prototxt' e 'MobileNetSSD_deploy.caffemodel' e coloque na mesma pasta do script."))
            return

        net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
        
        if shutil.which("ffmpeg") is None:
            self.status_label.config(text="Status: ffmpeg não encontrado!")
            self.stop_monitoring()
            return

        url = f'rtsp://{self.config["usuario"]}:{self.config["senha"]}@{self.config["ip"]}:{self.config["porta"]}/{self.config["stream_path"]}'
        
        # Loop principal para reconexão
        while not self.stop_event.is_set():
            print("Iniciando nova conexão com a câmera...")
            command = [
                'ffmpeg', '-i', url, '-loglevel', 'info', '-f', 'image2pipe',
                '-pix_fmt', 'bgr24', '-vcodec', 'rawvideo', '-'
            ]

            try:
                pipe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
                
                self.detected_resolution = None
                error_thread = threading.Thread(target=self.find_resolution_and_log, args=(pipe.stderr,))
                error_thread.daemon = True
                error_thread.start()

            except FileNotFoundError:
                self.status_label.config(text="Status: ffmpeg não encontrado!")
                self.stop_monitoring()
                return

            wait_start_time = time.time()
            while self.detected_resolution is None:
                time.sleep(0.1)
                if time.time() - wait_start_time > 15:
                    self.status_label.config(text="Status: Timeout ao detectar resolução.")
                    pipe.terminate()
                    time.sleep(5)
                    # continue o loop de reconexão
                    continue
            
            width, height = self.detected_resolution
            self.status_label.config(text="Status: Monitorando...")
            
            last_capture_time = time.time()
            capture_interval = 10 # Segundos

            # NOVO: Timer para reconexão periódica
            reconnect_interval = 120 # 2 minutos
            connection_start_time = time.time()

            # Loop interno para processamento de quadros
            while not self.stop_event.is_set():
                if time.time() - connection_start_time > reconnect_interval:
                    print("Tempo de 2 minutos atingido. Forçando reconexão...")
                    break # Sai do loop de processamento para reconectar

                raw_image = pipe.stdout.read(width * height * 3)
                if len(raw_image) != (width * height * 3):
                    print("Erro no fluxo de dados do ffmpeg. Tentando reconectar...")
                    break

                current_time = time.time()
                if current_time - last_capture_time < capture_interval:
                    continue
                
                last_capture_time = current_time
                print(f"Processando quadro para detecção de pessoas em: {time.strftime('%H:%M:%S')}")

                frame = np.frombuffer(raw_image, dtype='uint8').reshape((height, width, 3))

                (h, w) = frame.shape[:2]
                blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
                
                net.setInput(blob)
                detections = net.forward()

                person_count = 0
                for i in np.arange(0, detections.shape[2]):
                    confidence = detections[0, 0, i, 2]
                    
                    if confidence > 0.5:
                        idx = int(detections[0, 0, i, 1])
                        if idx == 15: # Índice para "pessoa"
                            person_count += 1
                            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                            (startX, startY, endX, endY) = box.astype("int")
                            
                            label = f"Pessoa: {confidence:.2%}"
                            cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)
                            y = startY - 15 if startY - 15 > 15 else startY + 15
                            cv2.putText(frame, label, (startX, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # Atualiza o label do contador na GUI
                self.window.after(0, lambda: self.person_count_label.config(text=f"Pessoas Detectadas: {person_count}"))

                if person_count > 0:
                    self.window.after(0, self.trigger_alert)

                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
            
            # Finaliza o processo ffmpeg antes de reconectar ou parar
            pipe.terminate()
            print("Processo ffmpeg da conexão atual finalizado.")
            if not self.stop_event.is_set():
                self.status_label.config(text="Status: Reconectando...")
                time.sleep(2)

        print("Monitoramento encerrado.")

# --- INICIALIZAÇÃO DA APLICAÇÃO ---
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    configuracao = load_or_create_config(root)
    
    if configuracao:
        root.deiconify()
        root.geometry("680x520")
        root.eval('tk::PlaceWindow . center')
        App(root, "Monitor de Movimento", configuracao)
        root.mainloop()
    else:
        root.destroy()
