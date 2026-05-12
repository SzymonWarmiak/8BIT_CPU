# 8-bit CPU Studio (ISA v1.5)

Kompletne środowisko IDE oraz kompilator Assemblera dla autorskiej architektury 8-bitowego procesora.

Aplikacja umożliwia pisanie kodu, kompilację do formatu binarnego oraz eksport wsadów pamięci kompatybilnych z symulatorem Logisim.

---

## Szybki Start

### Wymagania
* Python 3.x
* Biblioteka tkinter (standardowo w pakiecie Python)

### Uruchomienie
python Examples/asm_to_bin.py

### Obsługa Interfejsu
1. Edytor: Pisz kod po lewej stronie. Linie z błędami zostaną podświetlone na czerwono.
2. Kompilacja: Kliknij KOMPILUJ. Wynik pojawi się w oknie "Wyjście Binarne".
3. Eksport:
    * Zapisz .BIN: Czysty plik binarny (do EEPROM/Emulatorów).
    * Eksport Logisim: Plik tekstowy gotowy do wczytania w Logisim (Prawy klik na RAM -> Load Image).

---

## Architektura Systemu

* Typ: 8-bit RISC, Architektura Harvard.
* Rejestry: 16 rejestrów ogólnego przeznaczenia (R0 - R15).
* Szyna Danych: 8-bit (Wartości 0-255).
* Szyna Adresowa: 8-bit (Okno 256 bajtów). Dostęp do pełnych 4KB RAM poprzez Bank Switching.

### Mapa Pamięci (Memory Map)

Procesor widzi adresy 0x00 - 0xFF. Ich znaczenie zależy od wybranego Banku.

| Zakres Adresów | Opis |
| :--- | :--- |
| 0x00 - 0xFB | Pamięć RAM. Zawartość zależy od aktywnego Banku (0-15). |
|             | • Bank 0: Systemowy / Zmienne. |
|             | • Bank 3: VRAM (GPU). |
| 0xFC - 0xFF | MMIO (Memory Mapped I/O). Stałe adresy sprzętowe. |

### Urządzenia Wejścia/Wyjścia (MMIO)

Te adresy są dostępne zawsze, niezależnie od wybranego banku.

| Adres (Hex) | Adres (Dec) | Nazwa      | Opis |
| :---        | :---        | :---       | :--- |
| 0xFC        | 252         | BANK_REG   | Zapisz tu ID banku (0-15), aby podmienić pamięć RAM. |
| 0xFD        | 253         | KEYBOARD   | Odczyt: Kod wciśniętego klawisza. Zapis: Wartość 0xFF czyści bufor (ACK). |
| 0xFE        | 254         | TERMINAL   | Zapis: Wyświetla znak ASCII na ekranie tekstowym. |
| 0xFF        | 255         | HEX_DISP   | Zapis: Wyświetla liczbę na wyświetlaczu 7-segmentowym. |

---

## Lista Instrukcji (Instruction Set)

Każda instrukcja zajmuje 1 słowo (16 bitów).

### Arytmetyka i Logika
* ADD Ra, Rb   -> Ra = Ra + Rb
* SUB Ra, Rb   -> Ra = Ra - Rb
* AND Ra, Rb   -> Ra = Ra & Rb (Bitowe AND)
* OR  Ra, Rb   -> Ra = Ra | Rb (Bitowe OR)
* XOR Ra, Rb   -> Ra = Ra ^ Rb (Bitowe XOR)
* NOT Ra       -> Ra = ~Ra (Negacja bitowa)
* CMP Ra, Rb   -> Porównaj Ra i Rb (Ustawia flagi Z, N)

### Przesyłanie Danych
* MOV Ra, Rb    -> Kopiuj wartość z rejestru Rb do Ra.
* LDI Ra, Imm   -> Załaduj stałą (0-255) do Ra. Np. LDI R0, 10.
* LOAD Ra, [Imm]-> Załaduj z pamięci (adres stały). Np. LOAD R0, [100].
* LDR Ra, [Rb]  -> Odczyt wskaźnikowy. Adres jest w Rb.
* STR Ra, [Rb]  -> Zapis wskaźnikowy. Zapisz Ra pod adres w Rb.

### Sterowanie Przepływem
* JMP Label     -> Skok bezwarunkowy do etykiety.
* BEQ Label     -> Skok jeśli równe (Flaga Z=1). Użyj po CMP.
* HALT          -> Zatrzymaj procesor.

---

## Składnia Assemblera

### Podstawy
* Komentarze: Znak średnika (;).
* Etykiety: Nazwa zakończona dwukropkiem, np. START:, LOOP:.
* Liczby:
    * Dziesiętne: 10, 255
    * Szesnastkowe: 0xFF, 0xA0
    * Binarne: 0b1010
    * Znaki: 'A', 'Z' (zamieniane na kod ASCII).

### Dyrektywa .STRING
Ułatwia wypisywanie tekstu. Automatycznie generuje serię instrukcji LDI + STR.
Wymaganie: Rejestr R15 musi wskazywać na urządzenie wyjściowe (np. Terminal).

Przykład:
LDI R15, 254        ; Adres Terminala
.STRING "Hello!"    ; Wypisze "Hello!" na terminalu

---

## Przykłady Kodu

### 1. Migająca Dioda (GPU)
START:
    LDI R0, 252     ; Adres Banku
    LDI R1, 3       ; Bank 3 (GPU)
    STR R1, [R0]    ; Włącz GPU

    LDI R2, 240     ; Adres wiersza 0 (0xF0)
    LDI R3, 0xFF    ; Wszystkie diody ON
    STR R3, [R2]    ; Zapal
    HALT

---

## Ważne Uwagi (Gotchas)

1. Brak SHL/SHR: Procesor nie posiada instrukcji przesunięć bitowych.
   Mnożenie x2: ADD R0, R0.
2. Pułapka Banków: Zmieniając bank (STR do adresu 252), podmieniasz całą pamięć RAM (0-251). Rejestry procesora pozostają bez zmian.
   Dobra praktyka: Trzymaj wskaźniki i liczniki w rejestrach (R0-R15), a nie w pamięci RAM, jeśli planujesz często zmieniać banki.
3. Adresowanie: Skoki (JMP, BEQ) używają adresów absolutnych (0-255).
