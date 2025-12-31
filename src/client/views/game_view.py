import arcade

class GameView(arcade.View):
    """
    Режим Гри (Gameplay Mode).
    Тут буде відбуватися основний геймплей.
    """
    def on_show_view(self):
        self.window.background_color = arcade.color.BLACK
        print("[GameView] Switched to Game Mode.")

    def on_draw(self):
        self.clear()
        arcade.draw_text("GAMEPLAY MODE (Placeholder)", 
                         self.window.width / 2, self.window.height / 2,
                         arcade.color.WHITE, 30, anchor_x="center")