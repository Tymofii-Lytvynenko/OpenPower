import arcade
from src.client.window import MainWindow

def main():
    print("OpenPower starting...")
    
    # Створюємо вікно
    window = MainWindow()
    
    # Виконуємо початкове налаштування (яке запустить EditorView)
    window.setup()
    
    # Запускаємо цикл Arcade
    arcade.run()

if __name__ == "__main__":
    main()