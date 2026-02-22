import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import re
import struct
import datetime
import difflib

# --- DEFINICJA ARCHITEKTURY (ISA v1.5) ---

OPCODES = {
    "ADD":   0x0, # Ra, Rb
    "SUB":   0x1, # Ra, Rb
    "AND":   0x2, # Ra, Rb
    "OR":    0x3, # Ra, Rb
    "XOR":   0x4, # Ra, Rb
    "NOT":   0x5, # Ra
    "MOV":   0x6, # Ra, Rb
    "CMP":   0x7, # Ra, Rb
    "LOAD":  0x8, # Ra, [Imm]
    "STORE": 0x9, # [Imm] (Deprecated/Trap)
    "LDI":   0xA, # Ra, #Imm
    "JMP":   0xB, # Addr
    "BEQ":   0xC, # Addr
    "STR":   0xD, # Ra, [Rb]
    "LDR":   0xE, # Ra, [Rb]
    "HALT":  0xF  # -
}

# Typy instrukcji do parsowania
# R - Rejestr, I - Immediate (stała), A - Adres, P - Pointer [Reg]
INSTRUCTION_FORMATS = {
    "ADD":   ["R", "R"],
    "SUB":   ["R", "R"],
    "AND":   ["R", "R"],
    "OR":    ["R", "R"],
    "XOR":   ["R", "R"],
    "NOT":   ["R"],
    "MOV":   ["R", "R"],
    "CMP":   ["R", "R"],
    "LOAD":  ["R", "A"], # [Imm]
    "STORE": ["A"],      # [Imm]
    "LDI":   ["R", "I"], # #Imm
    "JMP":   ["L"],      # Label/Addr
    "BEQ":   ["L"],      # Label/Addr
    "STR":   ["R", "P"], # [Rb]
    "LDR":   ["R", "P"], # [Rb]
    "HALT":  []
}

class LineNumbers(tk.Canvas):
    def __init__(self, *args, **kwargs):
        tk.Canvas.__init__(self, *args, **kwargs)
        self.text_widget = None

    def attach(self, text_widget):
        self.text_widget = text_widget

    def redraw(self, *args):
        self.delete("all")
        i = self.text_widget.index("@0,0")
        while True :
            dline = self.text_widget.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.create_text(28, y, anchor="ne", text=linenum, fill="#555555", font=("Consolas", 11))
            i = self.text_widget.index("%s+1line" % i)

class AssemblerCompiler:
    def __init__(self):
        self.labels = {}
        self.binary_data = bytearray()
        self.source_map = [] # Mapuje adres binarny na linię kodu

    def parse_register(self, token):
        token = token.upper().strip(',')
        if not token.startswith('R'):
            raise ValueError(f"Nieprawidłowy rejestr: {token}")
        try:
            reg_num = int(token[1:])
            if 0 <= reg_num <= 15:
                return reg_num
            raise ValueError
        except:
            raise ValueError(f"Rejestr poza zakresem (R0-R15): {token}")

    def parse_number(self, token):
        token = token.strip(',').strip('[').strip(']').strip('#')
        # Obsługa literałów znakowych np. 'A'
        if token.startswith("'") and token.endswith("'") and len(token) == 3:
            return ord(token[1])
        try:
            if token.startswith('0x'):
                return int(token, 16)
            elif token.startswith('0b'):
                return int(token, 2)
            else:
                return int(token)
        except:
            raise ValueError(f"Nieprawidłowa liczba: {token}")

    def first_pass(self, lines):
        """Znajduje etykiety i przypisuje im adresy."""
        self.labels = {}
        address = 0
        clean_lines = []
        errors = []

        for line_idx, line in enumerate(lines):
            # Usuń komentarze
            line = line.split(';')[0].strip()
            if not line:
                continue

            # Sprawdź czy linia to etykieta (kończy się :)
            if line.endswith(':'):
                # Fix: Etykieta nie może zawierać cudzysłowów (np. .STRING "Text:")
                if '"' not in line:
                    label_name = line[:-1].upper()
                    self.labels[label_name] = address
                    continue
            
            # Jeśli linia zawiera etykietę i instrukcję (np. "LOOP: ADD R0, R1")
            if ':' in line:
                # Fix: Sprawdź czy dwukropek nie jest wewnątrz stringa (np. .STRING "Pwd: ")
                col_index = line.find(':')
                quote_count = line[:col_index].count('"')
                
                if quote_count % 2 == 0:
                    parts = line.split(':', 1)
                    label_name = parts[0].strip().upper()
                    self.labels[label_name] = address
                    line = parts[1].strip()
            
            # Obsługa dyrektywy .STRING "Tekst"
            # Rozwija napis na sekwencję instrukcji LDI R0, char + STR R0, [R15]
            if line.upper().startswith('.STRING') or line.upper().startswith('STRING'):
                start_quote = line.find('"')
                end_quote = line.rfind('"')
                
                if start_quote != -1 and end_quote > start_quote:
                    content = line[start_quote+1:end_quote]
                    for char in content:
                        # Generujemy kod dla każdego znaku
                        # Zakładamy: R0 = Dane, R15 = Adres Docelowy (np. Terminal)
                        clean_lines.append((line_idx + 1, f"LDI R0, {ord(char)}"))
                        clean_lines.append((line_idx + 1, f"STR R0, [R15]"))
                        address += 2 # 2 instrukcje na znak
                    continue
                else:
                    errors.append(f"Linia {line_idx + 1}: Błędna składnia .STRING (oczekiwano \"tekst\")")
                    continue
            
            # Wykrywanie linii zaczynających się od " (częsty błąd przy kopiowaniu)
            if line.startswith('"'):
                errors.append(f"Linia {line_idx + 1}: Nieznana instrukcja (czy chciałeś użyć .STRING?)")
                continue
            
            if not line:
                continue

            clean_lines.append((line_idx + 1, line))
            address += 1 # Adresowanie słowami (1 słowo = 1 instrukcja)
        
        return clean_lines, errors

    def compile(self, source_code):
        lines = source_code.split('\n')
        self.binary_data = bytearray()
        logs = []
        
        try:
            instructions, pass1_errors = self.first_pass(lines)
            logs.extend(pass1_errors)
        except Exception as e:
            return None, [f"Błąd krytyczny w Pass 1: {str(e)}"]

        address = 0
        
        for line_num, line in instructions:
            parts = re.split(r'[,\s]+', line)
            parts = [p for p in parts if p] # Usuń puste
            
            mnemonic = parts[0].upper()
            
            if mnemonic.startswith('"') or mnemonic.startswith("'"):
                logs.append(f"Linia {line_num}: Nieznana instrukcja (wygląda jak tekst, sprawdź składnię .STRING)")
                continue
            
            if mnemonic not in OPCODES:
                msg = f"Linia {line_num}: Nieznana instrukcja '{mnemonic}'"
                # Sugestie (Did you mean?)
                matches = difflib.get_close_matches(mnemonic, OPCODES.keys(), n=1, cutoff=0.6)
                if matches:
                    msg += f" (Czy chodziło o '{matches[0]}' ?)"
                logs.append(msg)
                continue

            opcode = OPCODES[mnemonic]
            req_args = INSTRUCTION_FORMATS[mnemonic]
            
            # Weryfikacja liczby argumentów
            if len(parts) - 1 != len(req_args):
                logs.append(f"Linia {line_num}: '{mnemonic}' wymaga {len(req_args)} argumentów, podano {len(parts)-1}")
                continue

            # Kodowanie (Format: 2 bajty)
            # Byte 1: [Opcode 4bit] [Reg A 4bit]
            # Byte 2: [Reg B 4bit / Padding] [Imm/Addr 8bit - nadpisuje Reg B jeśli trzeba]
            
            byte1 = (opcode << 4) & 0xF0
            byte2 = 0x00
            
            try:
                # Parsowanie argumentów
                if mnemonic in ["ADD", "SUB", "AND", "OR", "XOR", "MOV", "CMP"]:
                    ra = self.parse_register(parts[1])
                    rb = self.parse_register(parts[2])
                    byte1 |= (ra & 0x0F)
                    byte2 = rb & 0x0F
                    
                elif mnemonic == "NOT":
                    ra = self.parse_register(parts[1])
                    byte1 |= (ra & 0x0F)
                    
                elif mnemonic == "LDI":
                    ra = self.parse_register(parts[1])
                    imm = self.parse_number(parts[2])
                    if imm > 255: raise ValueError("Stała > 255")
                    byte1 |= (ra & 0x0F)
                    byte2 = imm & 0xFF
                    
                elif mnemonic == "LOAD": # LOAD Ra, [Imm]
                    ra = self.parse_register(parts[1])
                    addr = self.parse_number(parts[2])
                    if addr > 255: raise ValueError("Adres > 255")
                    byte1 |= (ra & 0x0F)
                    byte2 = addr & 0xFF
                    
                elif mnemonic == "STORE": # STORE [Imm]
                    addr = self.parse_number(parts[1])
                    if addr > 255: raise ValueError("Adres > 255")
                    byte2 = addr & 0xFF
                    
                elif mnemonic in ["JMP", "BEQ"]:
                    target = parts[1].upper()
                    if target in self.labels:
                        addr = self.labels[target]
                    else:
                        try:
                            addr = self.parse_number(target)
                        except:
                            raise ValueError(f"Nieznana etykieta: {target}")
                    
                    if addr > 255: 
                        # Ostrzeżenie: w architekturze 8-bit PC, skok powyżej 255 jest niemożliwy 
                        # chyba że PC jest szerszy. Zakładamy PC 8-bit dla prostoty lub 
                        # że skok jest relatywny (tu implementujemy absolutny).
                        # W specyfikacji "Szyna Adresowa CPU: 8-bit", więc skok max do 255.
                        logs.append(f"Linia {line_num}: Ostrzeżenie - Adres skoku {addr} poza stroną (0-255).")
                    
                    byte2 = addr & 0xFF
                    
                elif mnemonic in ["STR", "LDR"]: # STR Ra, [Rb]
                    ra = self.parse_register(parts[1])
                    # parts[2] powinno być [Rb]
                    rb_str = parts[2].strip('[').strip(']')
                    rb = self.parse_register(rb_str)
                    
                    byte1 |= (ra & 0x0F)
                    byte2 = rb & 0x0F

                elif mnemonic == "HALT":
                    pass # 0xF0 0x00

                self.binary_data.append(byte1)
                self.binary_data.append(byte2)
                address += 2

            except ValueError as e:
                logs.append(f"Linia {line_num}: Błąd argumentu - {str(e)}")
            except Exception as e:
                logs.append(f"Linia {line_num}: Nieoczekiwany błąd - {str(e)}")

        if not logs:
            logs.append("Kompilacja zakończona sukcesem.")
            logs.append(f"Rozmiar kodu: {len(self.binary_data)} bajtów.")
        
        return self.binary_data, logs

# --- GUI ---

class AssemblerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("8-bit CPU Assembler (v1.5 ISA)")
        self.root.geometry("1000x700")
        self.compiler = AssemblerCompiler()
        
        # Konfiguracja stylów dla edytora (podświetlanie błędów)
        self.code_editor_tags_configured = False
        
        # Definicja przykładów
        self.examples = {
            "1. Test GPU (Minimal)": """; PROSTY TEST GPU
; Zapala wszystkie diody w pierwszym wierszu (0xF0)
; -------------------------------------------------

START:
    LDI R0, 252     ; Adres Rejestru Banku (0xFC)
    LDI R1, 3       ; ID Banku GPU (Bank 3)
    
    ; 1. Przełącz na Bank 3
    STR R1, [R0]    ; Zapisz 3 pod adres 252 -> RAM to teraz VRAM
    
    ; 2. Przygotuj dane
    LDI R2, 240     ; Adres wiersza 0 w VRAM (0xF0)
    LDI R3, 255     ; Wartość 0xFF (wszystkie diody ON)
    
    ; 3. Rysuj
    STR R3, [R2]    ; Zapisz 0xFF pod adres 0xF0
    
    ; 4. Zatrzymaj (aby diody nie zgasły)
    HALT
""",
            "2. Klawiatura -> Terminal": """; ECHO KLAWIATURY
; Odczytuje znak z klawiatury (0xFD) i wysyła na terminal (0xFE)
; --------------------------------------------------------------

START:
    ; 1. Inicjalizacja Banku 0 (Bezpieczeństwo)
    LDI R0, 0
    LDI R15, 252    ; Adres Rejestru Banku
    STR R0, [R15]   ; Ustaw Bank 0

    ; 2. Konfiguracja adresów
    LDI R1, 253     ; Adres Klawiatury (0xFD)
    LDI R2, 254     ; Adres Terminala (0xFE)
    LDI R4, 255     ; Wartość ACK (0xFF)

WAIT_KEY:
    LDR R3, [R1]    ; Odczytaj klawisz do R3
    CMP R3, R0      ; Sprawdź czy 0 (brak klawisza)
    BEQ WAIT_KEY    ; Jeśli 0, czekaj dalej

    STR R3, [R2]    ; Wyślij znak na Terminal
    STR R4, [R1]    ; Wyślij ACK (0xFF) do klawiatury

    JMP WAIT_KEY
""",
            "3. Ciąg Fibonacciego": """; CIĄG FIBONACCIEGO (0-255)
; Oblicza kolejne liczby i wyświetla na HEX Display (0xFF)
; --------------------------------------------------------

INIT:
    LDI R0, 0       ; Liczba A
    LDI R1, 1       ; Liczba B
    LDI R15, 255    ; Adres HEX Display

LOOP:
    STR R0, [R15]   ; Wyświetl aktualną liczbę (A)
    
    MOV R2, R0      ; Temp = A
    ADD R2, R1      ; Temp = A + B (Nowa liczba)
    
    ; Przesunięcie: A = B, B = Temp
    MOV R0, R1
    MOV R1, R2
    
    JMP LOOP
""",
            "4. Kopiowanie Pamięci": """; KOPIOWANIE BLOKU PAMIĘCI
; 1. Wpisuje 0xAA pod adres 10 (Dane testowe)
; 2. Kopiuje 5 bajtów z adresu 10 do 20
; -------------------------------------------

INIT_DATA:
    LDI R0, 10      ; Adres 10
    LDI R1, 0xAA    ; Wartość 0xAA
    STR R1, [R0]    ; RAM[10] = 0xAA

PREPARE:
    LDI R0, 10      ; Adres Źródłowy (Source)
    LDI R1, 20      ; Adres Docelowy (Dest)
    LDI R2, 5       ; Licznik (Count)
    LDI R3, 1       ; Krok (Step)
    LDI R4, 0       ; Zero do porównania

COPY_LOOP:
    CMP R2, R4      ; Czy licznik == 0?
    BEQ STOP        ; Jeśli tak, koniec

    LDR R5, [R0]    ; Pobierz bajt ze źródła
    STR R5, [R1]    ; Zapisz bajt do celu

    ADD R0, R3      ; Source++
    ADD R1, R3      ; Dest++
    SUB R2, R3      ; Count--

    JMP COPY_LOOP

STOP:
    HALT
""",
            "5. Mnożenie (Programowe)": """; MNOŻENIE (R0 = R1 * R2)
; Programowe mnożenie przez dodawanie
; -----------------------------------

START:
    LDI R1, 5       ; Mnożna
    LDI R2, 4       ; Mnożnik
    LDI R0, 0       ; Wynik
    LDI R3, 0       ; Zero
    LDI R4, 1       ; Krok

LOOP:
    CMP R2, R3      ; Czy mnożnik == 0?
    BEQ STOP        ; Koniec
    
    ADD R0, R1      ; Wynik += Mnożna
    SUB R2, R4      ; Mnożnik--
    JMP LOOP

STOP:
    HALT
""",
            "6. Licznik Binarny (GPU)": """; LICZNIK BINARNY (GPU)
; Wyświetla liczby 0-255 na diodach
; ---------------------------------

INIT:
    LDI R0, 252     ; Adres Banku
    LDI R1, 3       ; Bank GPU
    STR R1, [R0]    ; Włącz GPU
    
    LDI R2, 240     ; Adres wiersza 0
    LDI R3, 0       ; Licznik
    LDI R4, 1       ; Krok

LOOP:
    STR R3, [R2]    ; Wyświetl
    ADD R3, R4      ; Licznik++
    JMP LOOP
""",
            "7. Operacje Logiczne": """; TEST LOGICZNY (AND, OR, XOR)
; Wyniki na wyświetlaczu HEX (0xFF)
; ---------------------------------

START:
    LDI R15, 255    ; Adres HEX Disp
    LDI R0, 0xAA    ; Wzór A (10101010)
    LDI R1, 0x0F    ; Wzór B (00001111)

    ; Test AND (Wynik: 0x0A)
    MOV R2, R0
    AND R2, R1
    STR R2, [R15]

    ; Test OR (Wynik: 0xAF)
    MOV R2, R0
    OR R2, R1
    STR R2, [R15]

    ; Test XOR (Wynik: 0xA5)
    MOV R2, R0
    XOR R2, R1
    STR R2, [R15]

    HALT
""",
            "8. Echo + GPU (Full)": """; ECHO + GPU DISPLAY
; 1. Czeka na znak z klawiatury
; 2. Wyświetla znak na Terminalu
; 3. Wyświetla kod binarny znaku na GPU (Wiersz 7)
; ------------------------------------------------

START:
    LDI R0, 0       ; Stała 0
    LDI R1, 253     ; Adres Klawiatury
    LDI R2, 254     ; Adres Terminala
    LDI R3, 252     ; Adres Banku
    LDI R4, 247     ; Adres VRAM (0xF7 - dół)
    LDI R14, 255    ; ACK (0xFF)

LOOP:
    ; Upewnij się, że Bank 0
    STR R0, [R3]
    
    ; Czytaj klawisz
    LDR R5, [R1]
    CMP R5, R0
    BEQ LOOP        ; Jeśli 0, czekaj

    ; 1. Terminal
    STR R5, [R2]

    ; 2. GPU (Bank 3)
    LDI R6, 3
    STR R6, [R3]    ; Przełącz na Bank 3
    STR R5, [R4]    ; Wyświetl na diodach
    
    ; Powrót do Bank 0
    STR R0, [R3]

    ; 3. ACK Klawiatury
    STR R14, [R1]   ; Skasuj bufor

    JMP LOOP
""",
            "9. Hello World": """; HELLO WORLD
; Wypisuje tekst na terminalu (0xFE)
; ----------------------------------

START:
    LDI R15, 254      ; Adres Terminala (0xFE)

    .STRING "Hello World!"
    ; .STRING automatycznie generuje kod wysyłający znaki do [R15]

    HALT
""",
            "10. Password Check": """; PASSWORD CHECK (PASS)
; Wpisz "PASS" (DUŻE LITERY) aby zapalić diody
; -------------------------------------

START:
    LDI R15, 252    ; Bank Reg
    LDI R0, 0
    STR R0, [R15]   ; Bank 0
    LDI R14, 254    ; Terminal
    LDI R13, 253    ; Keyboard
    LDI R12, 255    ; ACK

    .STRING "Pwd: "

    ; --- Check 'P' ---
WAIT_1:
    LDR R5, [R13]   ; Czytaj
    LDI R0, 0
    CMP R5, R0
    BEQ WAIT_1      ; Czekaj na znak
    STR R5, [R14]   ; Echo
    STR R12, [R13]  ; ACK
    
    LDI R1, 'P'
    CMP R5, R1
    BEQ OK_1
    JMP FAIL
OK_1:

    ; --- Check 'A' ---
WAIT_2:
    LDR R5, [R13]
    LDI R0, 0
    CMP R5, R0
    BEQ WAIT_2
    STR R5, [R14]
    STR R12, [R13]
    
    LDI R1, 'A'
    CMP R5, R1
    BEQ OK_2
    JMP FAIL
OK_2:

    ; --- Check 'S' ---
WAIT_3:
    LDR R5, [R13]
    LDI R0, 0
    CMP R5, R0
    BEQ WAIT_3
    STR R5, [R14]
    STR R12, [R13]
    
    LDI R1, 'S'
    CMP R5, R1
    BEQ OK_3
    JMP FAIL
OK_3:

    ; --- Check 'S' ---
WAIT_4:
    LDR R5, [R13]
    LDI R0, 0
    CMP R5, R0
    BEQ WAIT_4
    STR R5, [R14]
    STR R12, [R13]
    
    LDI R1, 'S'
    CMP R5, R1
    BEQ SUCCESS
    JMP FAIL

SUCCESS:
    .STRING " OK!"
    
    ; Włącz GPU (Bank 3)
    LDI R0, 3
    STR R0, [R15]
    
    ; Zapal diody (Wiersz 0)
    LDI R1, 240     ; 0xF0
    LDI R2, 0xFF    ; ON
    STR R2, [R1]
    HALT

FAIL:
    .STRING " NO!"
    HALT
"""
        }

        # Layout
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Lewa strona - Edytor
        left_frame = tk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(left_frame, text="Kod Źródłowy (Assembler)", font=("Arial", 10, "bold")).pack(anchor="w")
        
        # Kontener na edytor i numery linii
        editor_container = tk.Frame(left_frame)
        editor_container.pack(fill=tk.BOTH, expand=True)
        
        self.line_numbers = LineNumbers(editor_container, width=35, bg="#f0f0f0", highlightthickness=0)
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        self.code_editor = tk.Text(editor_container, width=50, height=30, font=("Consolas", 11), wrap=tk.NONE, undo=True)
        self.code_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar = tk.Scrollbar(editor_container, command=self.on_scroll)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.code_editor.config(yscrollcommand=self.on_text_scroll)
        
        self.line_numbers.attach(self.code_editor)
        
        # Eventy do odświeżania numerów linii
        self.code_editor.bind("<KeyRelease>", self.on_content_changed)
        self.code_editor.bind("<Button-1>", self.on_content_changed)
        self.code_editor.bind("<MouseWheel>", self.on_mouse_scroll)
        
        # Tag dla błędów
        self.code_editor.tag_config("error", background="#ffcccc")
        
        # Wstawienie szablonu
        self.insert_example_key("1. Test GPU (Minimal)")

        # Prawa strona - Hex Dump i Logi
        right_frame = tk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        tk.Label(right_frame, text="Wyjście Binarne (Hex)", font=("Arial", 10, "bold")).pack(anchor="w")
        self.hex_view = scrolledtext.ScrolledText(right_frame, width=40, height=20, font=("Consolas", 11), state='disabled')
        self.hex_view.pack(fill=tk.BOTH, expand=True)

        tk.Label(right_frame, text="Logi Kompilacji", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10,0))
        self.log_view = scrolledtext.ScrolledText(right_frame, width=40, height=10, font=("Consolas", 10), fg="red")
        self.log_view.pack(fill=tk.BOTH, expand=True)

        # Pasek narzędzi
        toolbar = tk.Frame(root, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Button(toolbar, text="KOMPILUJ", command=self.compile_code, bg="#ddffdd", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(toolbar, text="Zapisz .BIN", command=self.save_binary, font=("Arial", 10)).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(toolbar, text="Eksport Logisim (.txt)", command=self.save_logisim, bg="#ffeebb", font=("Arial", 10)).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(toolbar, text="Wyczyść", command=lambda: self.code_editor.delete('1.0', tk.END)).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Wybór przykładu
        tk.Label(toolbar, text="Przykład:").pack(side=tk.LEFT, padx=(10, 2))
        self.selected_example = tk.StringVar()
        self.example_combo = ttk.Combobox(toolbar, textvariable=self.selected_example, values=list(self.examples.keys()), state="readonly", width=25)
        self.example_combo.current(0)
        self.example_combo.pack(side=tk.LEFT, padx=2, pady=5)
        
        tk.Button(toolbar, text="Wstaw", command=self.insert_selected_example).pack(side=tk.LEFT, padx=2, pady=5)

    def on_scroll(self, *args):
        self.code_editor.yview(*args)
        self.line_numbers.redraw()

    def on_text_scroll(self, *args):
        self.scrollbar.set(*args)
        self.line_numbers.redraw()

    def on_mouse_scroll(self, event):
        self.code_editor.yview_scroll(int(-1*(event.delta/120)), "units")
        self.line_numbers.redraw()
        return "break"

    def on_content_changed(self, event=None):
        self.line_numbers.redraw()

    def insert_selected_example(self):
        key = self.selected_example.get()
        self.insert_example_key(key)

    def insert_example_key(self, key):
        if key in self.examples:
            self.code_editor.delete('1.0', tk.END)
            self.code_editor.insert('1.0', self.examples[key])
            self.line_numbers.redraw()

    def compile_code(self):
        source = self.code_editor.get('1.0', tk.END)
        binary, logs = self.compiler.compile(source)
        
        # Wyczyść poprzednie podświetlenia błędów
        self.code_editor.tag_remove("error", "1.0", tk.END)
        
        # Wyświetl logi
        self.log_view.delete('1.0', tk.END)
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_view.insert(tk.END, f"[{timestamp}] Rozpoczęto kompilację...\n")
        
        for log in logs:
            self.log_view.insert(tk.END, log + "\n")
            
            # Podświetlanie linii z błędem w edytorze
            match = re.search(r"Linia (\d+):", log)
            if match:
                line_num = match.group(1)
                self.code_editor.tag_add("error", f"{line_num}.0", f"{line_num}.end")
            
            if "Błąd" in log:
                self.log_view.config(fg="red")
            else:
                self.log_view.config(fg="green")

        # Wyświetl Hex Dump
        self.hex_view.config(state='normal')
        self.hex_view.delete('1.0', tk.END)
        
        if binary:
            data = bytearray(binary)
            if len(data) % 2 != 0:
                data.append(0)
            
            words = []
            for i in range(0, len(data), 2):
                word = (data[i] << 8) | data[i+1]
                words.append(word)
            
            while len(words) < 256:
                words.append(0)

            hex_output = "v3.0 hex words addressed\n"
            for i in range(0, len(words), 16):
                chunk = words[i:i+16]
                line_hex = " ".join(f"{w:04X}" for w in chunk)
                hex_output += f"{i:02x}: {line_hex}\n"
            
            self.hex_view.insert(tk.END, hex_output)
        
        self.hex_view.config(state='disabled')

    def save_binary(self):
        if not self.compiler.binary_data:
            messagebox.showwarning("Błąd", "Najpierw skompiluj kod!")
            return
            
        file_path = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("Binary Files", "*.bin")])
        if file_path:
            with open(file_path, "wb") as f:
                f.write(self.compiler.binary_data)
            messagebox.showinfo("Sukces", f"Zapisano plik: {file_path}")

    def save_logisim(self):
        if not self.compiler.binary_data:
            messagebox.showwarning("Błąd", "Najpierw skompiluj kod!")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Logisim Hex", "*.txt")])
        if file_path:
            try:
                with open(file_path, "w") as f:
                    f.write("v3.0 hex words addressed\n")
                    
                    data = bytearray(self.compiler.binary_data)
                    # Wyrównaj do parzystej liczby bajtów (słowa 16-bit)
                    if len(data) % 2 != 0:
                        data.append(0)
                    
                    words = []
                    for i in range(0, len(data), 2):
                        word = (data[i] << 8) | data[i+1]
                        words.append(word)
                    
                    # Wypełnij zerami do 256 słów (adresy 00-FF), aby pasowało do formatu z przykładu
                    while len(words) < 256:
                        words.append(0)

                    for i in range(0, len(words), 16):
                        chunk = words[i:i+16]
                        line_hex = " ".join(f"{w:04X}" for w in chunk)
                        f.write(f"{i:02x}: {line_hex}\n")
                
                messagebox.showinfo("Sukces", f"Zapisano plik Logisim: {file_path}")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zapisać pliku: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AssemblerApp(root)
    root.mainloop()
