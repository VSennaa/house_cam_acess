import tkinter as tk
from tkinter import messagebox
import json
import os
import subprocess
import shutil

# --- Caminho absoluto para o config.json, garantindo que funcione de qualquer lugar ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# --- CLASSE PARA A JANELA DE CONFIGURAÇÃO INICIAL ---
class SetupWindow:
    def __init__(self, parent):
        self.parent = parent
        self.config = None
        self.top = tk.Toplevel(parent)
        self.top.title("Configuração Inicial da Câmera")
        
        # --- CORREÇÃO: Centraliza a janela Toplevel manualmente ---
        window_width = 350
        window_height = 220
        screen_width = self.top.winfo_screenwidth()
        screen_height = self.top.winfo_screenheight()
        x_cordinate = int((screen_width/2) - (window_width/2))
        y_cordinate = int((screen_height/2) - (window_height/2))
        self.top.geometry(f"{window_width}x{window_height}+{x_cordinate}+{y_cordinate}")
        # --- FIM DA CORREÇÃO ---

        self.top.transient(parent)
        self.top.grab_set()
        
        # --- Widgets da Janela de Setup ---
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
        
        print("-> Janela de Setup inicializada e visível.")
        
    def save_config(self):
        """Salva a configuração no arquivo JSON usando o caminho absoluto."""
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
            
        messagebox.showinfo("Sucesso", "Configuração salva em 'config.json'!", parent=self.top)
        self.top.destroy()

# --- FUNÇÃO PARA GERENCIAR A CONFIGURAÇÃO ---
def load_or_create_config(root):
    """Carrega a configuração do JSON ou chama a janela de setup se ele não existir."""
    print("Verificando a existência do config.json...")
    if not os.path.exists(CONFIG_PATH):
        print("config.json não encontrado. Exibindo messagebox de boas-vindas.")
        messagebox.showinfo("Bem-vindo!", "Arquivo 'config.json' não encontrado. Vamos configurar sua câmera.")
        
        print("Messagebox fechado. Criando a janela de setup.")
        setup = SetupWindow(root)
        
        print("Aguardando o fechamento da janela de setup...")
        root.wait_window(setup.top)
        
        print("Janela de setup fechada.")
        config = setup.config
    else:
        print("config.json encontrado. Carregando configurações.")
        try:
            with open(CONFIG_PATH, 'r', encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, KeyError):
             messagebox.showerror("Erro", "Erro ao ler 'config.json'. Por favor, apague-o e execute novamente.")
             return None
             
    if config is None:
        print("Configuração não foi definida pelo usuário. Encerrando.")
        return None
    
    print("Configuração carregada com sucesso.")
    return config

# --- CLASSE PRINCIPAL DA APLICAÇÃO ---
class App:
    def __init__(self, window, window_title, config):
        self.window = window
        self.window.title(window_title)
        self.config = config
        self.ffplay_process = None

        label = tk.Label(window, text="Clique no botão para iniciar a câmera.", pady=10)
        label.pack()

        self.btn_start = tk.Button(window, text="▶ Iniciar Câmera", command=self.start_camera_ffplay, height=2, width=20)
        self.btn_start.pack(pady=10)

        self.btn_quit = tk.Button(window, text="Fechar Launcher", command=window.destroy)
        self.btn_quit.pack(pady=5)

    def start_camera_ffplay(self):
        """Monta a URL e executa o ffplay em um novo processo."""
        print("Iniciando a câmera com ffplay...")

        # Verifica proativamente se ffplay está disponível no PATH do sistema
        if shutil.which("ffplay") is None:
            messagebox.showerror("Erro", "Comando 'ffplay' não encontrado. Verifique se o FFmpeg está instalado e no PATH do sistema.")
            return

        url = f'rtsp://{self.config["usuario"]}:{self.config["senha"]}@{self.config["ip"]}:{self.config["porta"]}/{self.config["stream_path"]}'
        cmd = f'ffplay -noborder -autoexit "{url}"'

        self.btn_start.config(state="disabled", text="Câmera em execução...")

        try:
            # Redireciona a saída do subprocesso para DEVNULL para evitar que o buffer encha e congele a GUI.
            self.ffplay_process = subprocess.Popen(
                cmd, 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"Processo ffplay iniciado com PID: {self.ffplay_process.pid}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao iniciar ffplay: {e}")
            self.btn_start.config(state="normal", text="▶ Iniciar Câmera")
        
        self.window.after(1000, self.check_if_ffplay_closed)

    def check_if_ffplay_closed(self):
        """Verifica periodicamente se o processo ffplay ainda está em execução."""
        if self.ffplay_process and self.ffplay_process.poll() is not None:
            print("Processo ffplay foi fechado.")
            self.btn_start.config(state="normal", text="▶ Iniciar Câmera")
        else:
            self.window.after(1000, self.check_if_ffplay_closed)

# --- INICIALIZAÇÃO DA APLICAÇÃO ---
if __name__ == "__main__":
    # Cria a janela raiz, mas a mantém escondida movendo-a para fora da tela.
    root = tk.Tk()
    root.geometry('+9999+9999')

    configuracao = load_or_create_config(root)
    
    if configuracao:
        # Traz a janela de volta, define o tamanho e a centraliza.
        root.geometry("300x150")
        root.eval('tk::PlaceWindow . center')
        App(root, "Camera Launcher", configuracao)
        root.mainloop()
    else:
        # Se a configuração falhou, simplesmente destrói a janela raiz.
        root.destroy()
