import arcade
from PIL import Image
from pathlib import Path

class MapRenderer:
    """
    Відповідає за відображення мапи провінцій та доступ до даних пікселів.
    Використовує Hybrid Data: Sprite для GPU та PIL Image для CPU.
    """
    def __init__(self, map_path: Path):
        self.sprite_list = arcade.SpriteList()
        self.source_image = None
        self.width = 0
        self.height = 0
        
        if map_path.exists():
            try:
                # 1. GPU: Візуалізація
                sprite = arcade.Sprite(map_path)
                # Центруємо спрайт
                sprite.center_x = sprite.width / 2
                sprite.center_y = sprite.height / 2
                self.sprite_list.append(sprite)
                
                # 2. CPU: Логіка
                self.source_image = Image.open(map_path)
                self.width = self.source_image.width
                self.height = self.source_image.height
                
                print(f"[MapRenderer] Loaded map: {self.width}x{self.height}")
            except Exception as e:
                print(f"[MapRenderer] Error loading map: {e}")
        else:
            print(f"[MapRenderer] Error: Map file not found at {map_path}")

    def draw(self):
        """Малює мапу."""
        self.sprite_list.draw()

    def get_color_at_world_pos(self, world_x: float, world_y: float) -> str:
        """
        Повертає HEX-код кольору за світовими координатами.
        Повертає None, якщо клік поза межами мапи.
        """
        if not self.source_image:
            return None

        # Перевірка меж
        if 0 <= world_x < self.width and 0 <= world_y < self.height:
            # Конвертація Y (Arcade знизу-вгору -> Image зверху-вниз)
            img_x = int(world_x)
            img_y = int(self.height - world_y)
            
            try:
                color = self.source_image.getpixel((img_x, img_y))
                # Формат (R, G, B) або (R, G, B, A)
                return "#{:02x}{:02x}{:02x}".format(color[0], color[1], color[2])
            except Exception:
                return None
        return None

    def get_center(self) -> arcade.math.Vector2:
        """Повертає центр мапи для початкової позиції камери."""
        return arcade.math.Vector2(self.width / 2, self.height / 2)