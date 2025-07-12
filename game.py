import pgzrun, pygame, pytmx
import pgzero.music as music
from pgzero.loaders import sounds
import os, time, sys
from functools import lru_cache


# === KONSTANSOK ===
WIDTH = 320
HEIGHT = 240
TILE_SIZE = 16
MOVEMENT_COOLDOWN = 0.15
DEBUG_MODE_ON = False

SCORE = 0           # Aktuális játék pontszáma
HAS_KEY = False     # Kulcs van-e a játékosnál?

# Játék állapotok
STATE_LOGO = 0
STATE_TITLE = 1
STATE_GAME = 2
STATE_GAME_OVER = 3
STATE_END = 4
STATE_CREDITS = 5

# Játékszintek sorrendje
LEVEL_SEQUENCE = [
    "level-1",
    "level-last",
]

# Színek
RETRO_BROWN = (88, 68, 34)
RETRO_GREEN = (120, 164, 106)
RETRO_CREAM = (212, 210, 155)

# OPTIMIZATION: Pre-allocate commonly used rectangles
_temp_rect = pygame.Rect(0, 0, TILE_SIZE, TILE_SIZE)
_camera_rect = pygame.Rect(0, 0, WIDTH, HEIGHT)


# === HIGH SCORE ===
@lru_cache(maxsize=1)
def load_high_score():
    """Legmagasabb játékpontszám betöltése külső fájlból"""
    try:
        with open("data/highscore.txt", "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0

def save_high_score(score):
    """Legmagasabb játékpontszám kiírása külső fájlba"""
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/highscore.txt", "w") as f:
            f.write(str(score))
        print(f"Pontszám elmentve: {score}")
        load_high_score.cache_clear()           # Cache törlése
    except Exception as e:
        print(f"HIBA! Pontszám nem került elmentésre: {e}")

HIGH_SCORE = load_high_score()

# === JÁTÉK ÁLLAPOTOK ===
class GameStateManager:
    """
    Kezeli a játék különböző állapotait.

    Állapotok: LOGO -> TITLE -> GAME -> GAME_OVER -> TITLE
                             └-> CREDITS -> TITLE

    Felelős a státuszváltásokért, input kezelésért és renderelésért.
    """


    def __init__(self):
        pygame.mouse.set_visible(False)     # Cursor elrejtése
        self.current_state = STATE_LOGO     # Jelenlegi állapot
        self.game_paused = False            # Pause állapot tracking
        self.level_loader = None            # LevelLoader (pálya betöltő osztály) referencia

        # Logo állapot változói
        self.logo_timer = 0                 # Megjelenítés időzítő
        self.logo_duration = 3.0            # Megjelenítés hossza
        self.logo_sound_delay = 0.3         # Hang lejátszásának késleltetése
        self.logo_sound_played = False      # Hang lejátszásra került-e?
        self.logo_image = None              # Kép

        # Title állapot változói
        self.title_image = None
        self.title_font_small = None
        self.title_font_large = None
        self.game_over_font = None

        # Screen transition
        self.transitioning = False
        self.transition_timer = 0
        self.transition_duration = 0.5
        self.transition_surface = pygame.Surface((WIDTH, HEIGHT)).convert_alpha()
        self.next_state = None

        # Victory system
        self.victory_freeze = False
        self.victory_freeze_timer = 0
        self.victory_freeze_duration = 3.0

        # Credits system
        self.credits_images = []
        self.credits_index = 0
        self.credits_timer = 0
        self.credits_duration = 3.0
        self.credits_total = 0

        # OPTIMIZATION: Cache time to reduce system calls
        self._last_time = time.time()

        self._load_logo_assets()
        self._load_title_assets()

    def _load_logo_assets(self):
        """Load and convert logo assets"""
        try:
            self.logo_image = pygame.image.load("images/state_logo.png").convert_alpha()
        except Exception as e:
            print(f"Warning: Could not load logo image: {e}")
            # Create a simple fallback logo
            self.logo_image = pygame.Surface((WIDTH, HEIGHT)).convert_alpha()
            self.logo_image.fill((64, 64, 64))

            # Simple text fallback
            font = pygame.font.Font(None, 36)
            text = font.render("GAME", True, (120, 164, 106))
            text_rect = text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            self.logo_image.blit(text, text_rect)

    def _load_title_assets(self):
        """Load and convert title screen assets"""
        try:
            self.title_image = pygame.image.load("images/state_title.png").convert_alpha()
        except Exception as e:
            print(f"Warning: Could not load title image: {e}")
            # Create a simple fallback title screen
            self.title_image = pygame.Surface((WIDTH, HEIGHT)).convert_alpha()
            self.title_image.fill((32, 32, 64))

        # Load fonts
        try:
            self.title_font_small = pygame.font.Font("fonts/early-gameboy.ttf", 16)
            self.title_font_large = pygame.font.Font("fonts/early-gameboy.ttf", 24)
            self.game_over_font = pygame.font.Font("fonts/early-gameboy.ttf", 24)
        except Exception as e:
            print(f"Warning: Could not load early-gameboy font: {e}")
            # Fallback to default fonts
            self.title_font_small = pygame.font.Font(None, 16)
            self.title_font_large = pygame.font.Font(None, 24)
            self.game_over_font = pygame.font.Font(None, 24)

    def _load_credits(self):
        """Load credits images on-demand with better error handling"""
        self.credits_images.clear()
        self.credits_index = 0
        self.credits_timer = time.time()

        # Try to load credits images starting from credits_0.png
        credits_count = 0
        for i in range(0, 10):  # Check from 0 to 9
            try:
                image_path = f"images/credits_{i}.png"
                print(f"Checking for: {image_path}")
                if os.path.exists(image_path):
                    credits_count += 1
                    print(f"Found: {image_path}")
                else:
                    print(f"Not found: {image_path}")
                    break
            except Exception as e:
                print(f"Error checking {image_path}: {e}")
                break

        self.credits_total = credits_count
        print(f"Found {credits_count} credits screens (starting from credits_0.png)")

        # If no credits found, go back to title immediately
        if credits_count == 0:
            print("No credits images found, returning to title")
            self._start_state_transition(STATE_TITLE)
            return

        try:
            music.play("village")
        except:
            pass

    def _get_current_credits_image(self):
        """Load current credits image on demand with conversion"""
        if self.credits_index >= self.credits_total:
            return None

        try:
            image_path = f"images/credits_{self.credits_index}.png"
            image = pygame.image.load(image_path).convert_alpha()
            return image
        except Exception as e:
            print(f"Warning: Could not load {image_path}: {e}")
            return None

    def _start_state_transition(self, next_state):
        """Start transition to next state"""
        if self.transitioning:
            return False

        self.transitioning = True
        self.transition_timer = time.time()
        self.next_state = next_state
        return True

    def update(self):
        """Update current state with cached time"""
        current_time = time.time()

        # Handle transitions
        if self.transitioning:
            elapsed = current_time - self.transition_timer
            if elapsed >= self.transition_duration:
                self.transitioning = False
                self._change_state(self.next_state)
                self.next_state = None
            return

        # Update current state
        if self.current_state == STATE_LOGO:
            self._update_logo(current_time)
        elif self.current_state == STATE_TITLE:
            self._update_title(current_time)
        elif self.current_state == STATE_GAME:
            self._update_game(current_time)
        elif self.current_state == STATE_GAME_OVER:
            self._update_game_over(current_time)
        elif self.current_state == STATE_CREDITS:
            self._update_credits(current_time)

        self._last_time = current_time

    def _update_logo(self, current_time):
        """Update logo state with time parameter"""
        # Initialize timer on first update
        if self.logo_timer == 0:
            self.logo_timer = current_time

        elapsed = current_time - self.logo_timer

        # Play sound effect after delay
        if not self.logo_sound_played and elapsed >= self.logo_sound_delay:
            try:
                sounds.gold_2.play()
            except:
                print("Warning: Could not play logo sound")
            self.logo_sound_played = True

        # Check if logo duration is complete
        if elapsed >= self.logo_duration:
            self._start_state_transition(STATE_TITLE)

    def _update_title(self, current_time):
        """Update title state"""
        # Title screen is static, just wait for input
        pass

    def _update_credits(self, current_time):
        """Update credits state with variable timing"""
        # Different durations for different screens
        if self.credits_index == 0:
            duration = 7.0  # First screen displays for 7 seconds
        else:
            duration = 3.0  # All other screens display for 3 seconds

        # Check if it's time to advance to next screen
        if current_time - self.credits_timer >= duration:
            self.credits_index += 1
            self.credits_timer = current_time

            print(f"Moving to credits screen {self.credits_index}")

            # If we've shown all credits, return to title
            if self.credits_index >= self.credits_total:
                print("Credits finished, transitioning to title")
                self._start_state_transition(STATE_TITLE)

    def _handle_credits_input(self):
        """Handle credits screen input"""
        # Skip to next screen or exit credits
        if keyboard.space or keyboard.RETURN:
            self.credits_index += 1
            self.credits_timer = time.time()

            if self.credits_index >= self.credits_total:
                self._start_state_transition(STATE_TITLE)

            time.sleep(0.2)  # Prevent rapid input

        # Exit credits immediately
        if keyboard.ESCAPE:
            self._start_state_transition(STATE_TITLE)

    def _update_game(self, current_time):
        """Update game state"""
        # Check for victory freeze first
        if self.victory_freeze:
            if current_time - self.victory_freeze_timer >= self.victory_freeze_duration:
                self.victory_freeze = False
                print("Victory freeze ended - transitioning to credits")
                self._start_state_transition(STATE_CREDITS)
            return

        # Normal game update
        if not self.game_paused and self.level_loader:
            self.level_loader.update()

            # Check if player is dead and transition to game over
            if self.level_loader.player and self.level_loader.player.is_dead():
                if (self.level_loader.player.state == "dying" and
                    self.level_loader.player.anim.finished):
                    print("Player died - transitioning to game over")
                    self._start_state_transition(STATE_GAME_OVER)

    def _update_game_over(self, current_time):
        """Update game over state"""
        # Game over screen is static, just wait for input
        pass

    def _change_state(self, new_state):
        """Change to new state with optimizations"""
        old_state = self.current_state
        self.current_state = new_state

        # State-specific initialization
        if new_state == STATE_GAME and old_state != STATE_GAME:
            # Initialize game for the first time OR reset after game over
            if (not self.level_loader or
                old_state == STATE_GAME_OVER or
                (self.level_loader and self.level_loader.player and self.level_loader.player.is_dead())):

                print("Creating new game (fresh start or player was dead)")
                self.level_loader = LevelLoader(LEVEL_SEQUENCE)
                # Reset score when starting new game
                global SCORE, HAS_KEY
                SCORE = 0
                HAS_KEY = False
            print("Entered game state")

        elif new_state == STATE_LOGO:
            # Reset logo state
            self.logo_sound_played = False
            self.logo_timer = 0

        elif new_state == STATE_TITLE:
            try:
                music.play("village")
            except:
                pass
            print("Entered title state")

        elif new_state == STATE_GAME_OVER:
            print("Entered game over state")

        elif new_state == STATE_CREDITS:
            self._load_credits()
            print("Entered credits state")

    def handle_input(self):
        """Handle input for current state"""
        # Check for ESC key to quit (works in any state)
        if keyboard.ESCAPE:
            print("ESC pressed - quitting game")
            pygame.quit()
            sys.exit(0)

        if self.transitioning:
            return  # No input during transitions

        if self.current_state == STATE_TITLE:
            self._handle_title_input()
        elif self.current_state == STATE_GAME:
            self._handle_game_input()
        elif self.current_state == STATE_GAME_OVER:
            self._handle_game_over_input()
        elif self.current_state == STATE_CREDITS:
            self._handle_credits_input()

    def _handle_title_input(self):
        """Handle title screen input"""
        # Start game when P (START), SPACE (A), or ENTER (B) is pressed
        if keyboard.p or keyboard.space or keyboard.RETURN:
            print("Starting game from title screen")

            # Play accept sound
            try:
                sounds.accept_2.play()
            except Exception as e:
                print(f"Warning: Could not play accept sound: {e}")

            self._start_state_transition(STATE_GAME)
            time.sleep(0.2)  # Prevent rapid input

    def _start_victory_freeze(self):
        """Start victory freeze after boss defeat"""
        if not self.victory_freeze:
            self.victory_freeze = True
            self.victory_freeze_timer = time.time()
            print("Victory freeze started!")

    def _set_paused(self, paused):
        """Set pause state for all entities including victory freeze"""
        # Pause player animations
        if self.level_loader and self.level_loader.player:
            self.level_loader.player.set_paused(paused or self.victory_freeze)

        # Set pause state for level entities
        if self.level_loader:
            self.level_loader.set_paused(paused or self.victory_freeze)

    def _handle_game_input(self):
        """Handle game state input"""
        # Don't process any input during victory freeze
        if self.victory_freeze:
            return

        # Quit game
        if keyboard.ESCAPE:
            print("ESC pressed - quitting game")
            pygame.quit()
            sys.exit(0)

        # Pause toggle
        if keyboard.p:
            self.toggle_pause()
            time.sleep(0.2)  # Prevent rapid toggling

        # Debug toggle
        if keyboard.d:
            self.toggle_debug_mode()
            time.sleep(0.2)

        # Only process game input if not paused
        if (not self.game_paused and self.level_loader and self.level_loader.player):
            # Attack
            if keyboard.space:
                self.level_loader.player.start_attack()
                time.sleep(0.1)

            # Door interaction
            if keyboard.RETURN:
                self.level_loader.try_enter_door()
                time.sleep(0.2)  # Prevent rapid input

            # Movement (only if not attacking and not transitioning)
            player = self.level_loader.player
            if (player.state != "attacking" and not self.level_loader.transitioning):

                if keyboard.left and not any([keyboard.right, keyboard.up, keyboard.down]):
                    self.level_loader.move_player(-1, 0)
                elif keyboard.right and not any([keyboard.left, keyboard.up, keyboard.down]):
                    self.level_loader.move_player(1, 0)
                elif keyboard.up and not any([keyboard.left, keyboard.right, keyboard.down]):
                    self.level_loader.move_player(0, -1)
                elif keyboard.down and not any([keyboard.left, keyboard.right, keyboard.up]):
                    self.level_loader.move_player(0, 1)

    def _handle_game_over_input(self):
        """Handle game over screen input"""
        # Quit game
        if keyboard.ESCAPE:
            print("ESC pressed - quitting game")
            pygame.quit()
            sys.exit(0)

        # Return to title when space or enter is pressed
        if keyboard.space or keyboard.RETURN:
            print("Returning to title screen from game over")
            self._start_state_transition(STATE_TITLE)
            time.sleep(0.2)  # Prevent rapid input

    def toggle_pause(self):
        """Toggle game pause"""
        if self.current_state == STATE_GAME:
            self.game_paused = not self.game_paused
            print(f"Game {'paused' if self.game_paused else 'unpaused'}")

    def toggle_debug_mode(self):
        """Toggle debug mode"""
        global DEBUG_MODE_ON
        DEBUG_MODE_ON = not DEBUG_MODE_ON
        print(f"Debug mode: {'ON' if DEBUG_MODE_ON else 'OFF'}")

    def draw(self, screen):
        """Draw current state with optimizations"""
        if self.current_state == STATE_LOGO:
            self._draw_logo(screen)
        elif self.current_state == STATE_TITLE:
            self._draw_title(screen)
        elif self.current_state == STATE_GAME:
            self._draw_game(screen)
        elif self.current_state == STATE_GAME_OVER:
            self._draw_game_over(screen)
        elif self.current_state == STATE_CREDITS:
            self._draw_credits(screen)

        # Draw transition overlay (always last)
        if self.transitioning:
            self._draw_transition(screen)

    def _draw_logo(self, screen):
        """Draw logo state"""
        screen.fill((0, 0, 0))  # Black background
        if self.logo_image:
            # Center the logo
            logo_rect = self.logo_image.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(self.logo_image, logo_rect)

    def _draw_title(self, screen):
        """Draw title state with cached surfaces"""
        global HIGH_SCORE

        screen.fill((0, 0, 0))  # Black background

        # Draw title background image
        if self.title_image:
            title_rect = self.title_image.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(self.title_image, title_rect)

        # OPTIMIZATION: Cache rendered text surfaces
        if not hasattr(self, '_cached_high_score') or self._cached_high_score != HIGH_SCORE:
            self._cached_high_score = HIGH_SCORE
            high_score_text = f"High Score: {HIGH_SCORE}"
            if self.title_font_small:
                self._cached_high_score_surface = self.title_font_small.render(
                    high_score_text, True, RETRO_GREEN
                )
                self._cached_high_score_rect = self._cached_high_score_surface.get_rect(
                    center=(WIDTH // 2, 160)
                )

        # Draw cached high score
        if hasattr(self, '_cached_high_score_surface'):
            screen.blit(self._cached_high_score_surface, self._cached_high_score_rect)

        # OPTIMIZATION: Cache "PRESS START" text (only render once)
        if not hasattr(self, '_cached_press_start_surface'):
            press_start_text = "PRESS START"
            if self.title_font_large:
                self._cached_press_start_surface = self.title_font_large.render(
                    press_start_text, True, RETRO_CREAM
                )
                self._cached_press_start_rect = self._cached_press_start_surface.get_rect(
                    center=(WIDTH // 2, 160 + 32)
                )

        # Draw cached "PRESS START"
        if hasattr(self, '_cached_press_start_surface'):
            screen.blit(self._cached_press_start_surface, self._cached_press_start_rect)

    def _draw_game(self, screen):
        """Draw game state"""
        if self.level_loader:
            self.level_loader.draw(screen)

            # Draw pause darkening overlay (but NOT during victory freeze)
            if self.game_paused and not self.victory_freeze:
                # OPTIMIZATION: Cache pause overlay
                if not hasattr(self, '_pause_overlay'):
                    self._pause_overlay = pygame.Surface((WIDTH, HEIGHT)).convert_alpha()
                    self._pause_overlay.fill((0, 0, 0))
                    self._pause_overlay.set_alpha(96)
                screen.blit(self._pause_overlay, (0, 0))

            # Optional: Draw pause indicator (minimal)
            if self.game_paused and DEBUG_MODE_ON and not self.victory_freeze:
                # OPTIMIZATION: Cache debug pause surface
                if not hasattr(self, '_debug_pause_surf'):
                    self._debug_pause_surf = pygame.Surface((4, 4)).convert_alpha()
                    self._debug_pause_surf.fill((255, 255, 0))
                screen.blit(self._debug_pause_surf, (WIDTH - 8, 4))

    def _draw_game_over(self, screen):
        """Draw game over state with cached surfaces"""
        global SCORE, HIGH_SCORE

        screen.fill((0, 0, 0))  # Black background

        # OPTIMIZATION: Cache "GAME OVER" text (render once)
        if not hasattr(self, '_cached_game_over_surface'):
            game_over_text = "GAME OVER"
            if self.game_over_font:
                self._cached_game_over_surface = self.game_over_font.render(
                    game_over_text, True, RETRO_CREAM
                )
                self._cached_game_over_rect = self._cached_game_over_surface.get_rect(
                    center=(WIDTH // 2, HEIGHT // 2 - 30)
                )

        # Draw cached "GAME OVER"
        if hasattr(self, '_cached_game_over_surface'):
            screen.blit(self._cached_game_over_surface, self._cached_game_over_rect)

        # OPTIMIZATION: Cache score text if it hasn't changed
        if not hasattr(self, '_cached_final_score') or self._cached_final_score != SCORE:
            self._cached_final_score = SCORE
            score_text = f"Score: {SCORE}"
            if self.title_font_large:
                self._cached_final_score_surface = self.title_font_large.render(
                    score_text, True, RETRO_CREAM
                )
                self._cached_final_score_rect = self._cached_final_score_surface.get_rect(
                    center=(WIDTH // 2, HEIGHT // 2 + 10)
                )

        # Draw cached final score
        if hasattr(self, '_cached_final_score_surface'):
            screen.blit(self._cached_final_score_surface, self._cached_final_score_rect)

        # OPTIMIZATION: Cache high score text for game over screen
        if not hasattr(self, '_cached_go_high_score') or self._cached_go_high_score != HIGH_SCORE:
            self._cached_go_high_score = HIGH_SCORE
            high_score_text = f"High Score: {HIGH_SCORE}"
            if self.title_font_small:
                self._cached_go_high_score_surface = self.title_font_small.render(
                    high_score_text, True, RETRO_CREAM
                )
                self._cached_go_high_score_rect = self._cached_go_high_score_surface.get_rect(
                    center=(WIDTH // 2, HEIGHT // 2 + 30)
                )

        # Draw cached high score
        if hasattr(self, '_cached_go_high_score_surface'):
            screen.blit(self._cached_go_high_score_surface, self._cached_go_high_score_rect)

    def _draw_credits(self, screen):
        """Draw credits screen with on-demand loading"""
        screen.fill(RETRO_BROWN)  # Brown background

        # If we're past the last credit, don't draw anything
        if self.credits_index >= self.credits_total:
            return

        # Load and draw current credits image
        credits_image = self._get_current_credits_image()
        if credits_image:
            # Center the image
            image_rect = credits_image.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(credits_image, image_rect)
        else:
            print(f"Warning: Could not load credits_{self.credits_index}.png")

    def _draw_transition(self, screen):
        """Draw transition overlay"""
        elapsed = time.time() - self.transition_timer
        progress = elapsed / self.transition_duration

        # Fade to brown instead of black
        alpha = int(255 * progress)
        self.transition_surface.fill(RETRO_BROWN)
        self.transition_surface.set_alpha(alpha)
        screen.blit(self.transition_surface, (0, 0))


class ObjectPool:
    """Simple object pool for reducing allocations"""

    def __init__(self, factory_func, initial_size=10):
        self.factory_func = factory_func
        self.available = []
        self.in_use = []

        # Pre-allocate objects
        for _ in range(initial_size):
            self.available.append(factory_func())

    def get(self, *args, **kwargs):
        """Get object from pool"""
        if self.available:
            obj = self.available.pop()
            # Reset/initialize object with new parameters
            if hasattr(obj, 'reset'):
                obj.reset(*args, **kwargs)
            self.in_use.append(obj)
            return obj
        else:
            # Pool exhausted, create new object
            obj = self.factory_func(*args, **kwargs)
            self.in_use.append(obj)
            return obj

    def return_object(self, obj):
        """Return object to pool"""
        if obj in self.in_use:
            self.in_use.remove(obj)
            self.available.append(obj)


# Create global pools for frequently created objects
_rect_pool = ObjectPool(lambda: pygame.Rect(0, 0, 0, 0), 20)


# === ANIMÁCIÓ KEZELŐ ===

class AnimationManager:
    """Lightweight animation manager optimized for Pi Zero"""

    _sprite_cache = {}  # Global cache for all spritesheets
    _frame_cache = {}   # Cache for cut frames

    # OPTIMIZATION: Pre-allocated surface for frame cutting
    _temp_surface = None

    def __init__(self, spritesheet_path, tile_size=16, animations=None):
        self.tile_size = tile_size
        self.animations = animations or {}

        # Simple animation state
        self.current_anim = None
        self.frame_idx = 0
        self.last_update = 0
        self.finished = False
        self.paused = False

        # Use cached spritesheet or load new one
        if spritesheet_path not in AnimationManager._sprite_cache:
            try:
                AnimationManager._sprite_cache[spritesheet_path] = pygame.image.load(spritesheet_path).convert_alpha()
            except pygame.error as e:
                print(f"Failed to load spritesheet {spritesheet_path}: {e}")
                # Create fallback surface
                fallback = pygame.Surface((tile_size * 4, tile_size * 4))
                fallback.fill((255, 0, 255))  # Magenta for missing sprites
                AnimationManager._sprite_cache[spritesheet_path] = fallback

        self.spritesheet = AnimationManager._sprite_cache[spritesheet_path]

    def _get_frame(self, anim_name, frame_idx):
        """Get frame surface with improved caching"""
        cache_key = f"{id(self.spritesheet)}_{anim_name}_{frame_idx}"

        if cache_key not in AnimationManager._frame_cache:
            try:
                row, col = self.animations[anim_name]["frames"][frame_idx]
                x, y = col * self.tile_size, row * self.tile_size

                # OPTIMIZATION: Use subsurface with convert() for better blitting performance
                frame = self.spritesheet.subsurface(x, y, self.tile_size, self.tile_size)
                AnimationManager._frame_cache[cache_key] = frame.convert_alpha()
            except (KeyError, IndexError, ValueError) as e:
                print(f"Animation frame error: {e}")
                # Create error frame
                error_frame = pygame.Surface((self.tile_size, self.tile_size))
                error_frame.fill((255, 0, 0))  # Red for errors
                AnimationManager._frame_cache[cache_key] = error_frame.convert_alpha()

        return AnimationManager._frame_cache[cache_key]

    def play(self, anim_name, reset=True):
        """Start animation with validation"""
        if anim_name not in self.animations:
            print(f"Warning: Animation '{anim_name}' not found")
            return

        if self.current_anim != anim_name or reset:
            self.current_anim = anim_name
            self.frame_idx = 0
            self.last_update = time.time()
            self.finished = False

    def set_paused(self, paused):
        """Set animation pause state"""
        self.paused = paused

    def update(self):
        """Update animation with reduced time.time() calls"""
        if not self.current_anim or self.finished or self.paused:
            return

        anim = self.animations[self.current_anim]
        now = time.time()

        if now - self.last_update >= anim["duration"]:
            self.frame_idx += 1
            self.last_update = now

            frame_count = len(anim["frames"])
            if self.frame_idx >= frame_count:
                if anim.get("loop", True):
                    self.frame_idx = 0
                else:
                    self.frame_idx = frame_count - 1
                    self.finished = True

    def get_frame(self):
        """Get current frame surface"""
        if not self.current_anim:
            return None

        frame_count = len(self.animations[self.current_anim]["frames"])
        safe_frame_idx = min(self.frame_idx, frame_count - 1)
        return self._get_frame(self.current_anim, safe_frame_idx)

    @classmethod
    def clear_caches(cls):
        """Clear all caches to free memory"""
        cls._sprite_cache.clear()
        cls._frame_cache.clear()

# === JÁTÉKOS ===

class Player:
    """Optimized player class with reduced allocations"""

    # Class-level constants to reduce memory
    ANIMATIONS = {
        "idle_right": {"frames": [(0, 0), (0, 1), (0, 2)], "duration": 0.6, "loop": True},
        "idle_left": {"frames": [(1, 0), (1, 1), (1, 2)], "duration": 0.6, "loop": True},
        "walk_right": {"frames": [(2, 0), (2, 1), (2, 2), (2, 3)], "duration": 0.6, "loop": True},
        "walk_left": {"frames": [(3, 0), (3, 1), (3, 2), (3, 3)], "duration": 0.6, "loop": True},
        "hurt_right": {"frames": [(4, 1), (4, 2), (4, 3), (4, 4), (4, 5)], "duration": 0.6, "loop": False},
        "hurt_left": {"frames": [(5, 1), (5, 2), (5, 3), (5, 4), (5, 5)], "duration": 0.6, "loop": False},
        "die_right": {"frames": [(6, 1), (6, 2), (6, 3)], "duration": 0.6, "loop": False},
        "die_left": {"frames": [(7, 1), (7, 2), (7, 3)], "duration": 0.6, "loop": False},
    }

    SWORD_ANIMATIONS = {
        "attack_left": {"frames": [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)], "duration": 0.1, "loop": False},
        "attack_right": {"frames": [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)], "duration": 0.1, "loop": False},
    }

    def __init__(self, x, y):
        # Grid-snap position
        self.x = (x // TILE_SIZE) * TILE_SIZE
        self.y = (y // TILE_SIZE) * TILE_SIZE

        # Basic state
        self.facing = "right"
        self.last_move = 0

        # Combat state
        self.health = 3
        self.max_health = 3

        # State management
        self.state = "idle"
        self.state_timer = 0
        self.invincible_timer = 0

        # OPTIMIZATION: Cache the rectangle to avoid creating new ones
        self._rect = pygame.Rect(self.x, self.y, TILE_SIZE, TILE_SIZE)

        # Animation managers
        self.anim = AnimationManager("images/player.png", TILE_SIZE, self.ANIMATIONS)
        self.sword_anim = AnimationManager("images/weapons_animated.png", 48, self.SWORD_ANIMATIONS)
        self.anim.play("idle_right")

        # OPTIMIZATION: Cache time for reduced system calls
        self._last_update = time.time()

    def set_paused(self, paused):
        """Set pause state for animations"""
        self.anim.set_paused(paused)
        self.sword_anim.set_paused(paused)

    def update(self):
        """Optimized update with reduced time calls"""
        now = time.time()
        dt = now - self._last_update

        # Update timers
        if self.invincible_timer > 0:
            self.invincible_timer = max(0, self.invincible_timer - dt)

        # State machine with optimized animation updates
        if self.state == "dying":
            if not self.anim.finished:
                self.anim.update()
        elif self.state == "hurt":
            if now - self.state_timer >= 1.0:
                self.state = "idle"
            self.anim.update()
        elif self.state == "attacking":
            if now - self.state_timer >= 0.5:
                self.state = "idle"
            self.sword_anim.update()
            self.anim.update()
        else:
            # Idle/moving state
            if self.state in ["idle", "moving"]:
                anim_name = f"{'walk' if self.state == 'moving' else 'idle'}_{self.facing}"
                self.anim.play(anim_name, False)
            self.anim.update()

        self._last_update = now

    def move(self, dx, dy, level_width, level_height, current_time):
        """Optimized movement with cached rectangle updates"""
        if self.state in ["attacking", "hurt", "dying"] or not self._can_move(current_time):
            return False

        # Update facing
        if dx > 0:
            self.facing = "right"
        elif dx < 0:
            self.facing = "left"

        # Calculate new position
        new_x = self.x + (dx * TILE_SIZE)
        new_y = self.y + (dy * TILE_SIZE)

        # Boundary check
        if 0 <= new_x <= level_width - TILE_SIZE and 0 <= new_y <= level_height - TILE_SIZE:
            self.x, self.y = new_x, new_y
            # OPTIMIZATION: Update cached rectangle
            self._rect.x, self._rect.y = self.x, self.y
            self.last_move = current_time
            self.state = "moving"
            return True
        return False

    def _can_move(self, current_time):
        """Movement cooldown check"""
        return current_time - self.last_move >= MOVEMENT_COOLDOWN

    def start_attack(self):
        """Start attack with sound optimization"""
        if self.state in ["attacking", "hurt", "dying"]:
            return False

        self.state = "attacking"
        self.state_timer = time.time()
        try:
            sounds.sword_2.play()
        except:
            pass  # Silent fail for missing sounds
        self.sword_anim.play(f"attack_{self.facing}", True)
        return True

    def take_damage(self, damage=1):
        """Take damage with invincibility check"""
        if self.invincible_timer > 0 or self.state in ["hurt", "dying"]:
            return False

        self.health -= damage
        if self.health <= 0:
            self._start_death()
        else:
            self._start_hurt()
        return True

    def _start_hurt(self):
        """Start hurt state"""
        self.state = "hurt"
        self.state_timer = time.time()
        self.invincible_timer = 1.8
        try:
            sounds.hit_7.play()
        except:
            pass
        self.anim.play(f"hurt_{self.facing}", True)

    def _start_death(self):
        """Start death sequence"""
        self.state = "dying"
        self.state_timer = time.time()
        music.stop()
        try:
            sounds.game_over.play()
        except:
            pass
        self.anim.play(f"die_{self.facing}", True)

    def get_rect(self):
        """Return cached rectangle"""
        return self._rect

    def is_dead(self):
        """Check if player is dead"""
        return self.health <= 0

    def draw(self, screen, camera_x, camera_y):
        """Optimized drawing with reduced calculations"""
        screen_x = self.x - camera_x
        screen_y = self.y - camera_y

        # Early exit if off-screen
        if screen_x < -TILE_SIZE or screen_x > WIDTH or screen_y < -TILE_SIZE or screen_y > HEIGHT:
            return

        # Flashing effect during invincibility (not when dying)
        if self.invincible_timer > 0 and self.state not in ["hurt", "dying"]:
            # OPTIMIZATION: Use integer time for flashing to reduce time.time() calls
            if int(self._last_update * 10) % 2:
                return

        # Draw player
        frame = self.anim.get_frame()
        if frame:
            screen.blit(frame, (screen_x, screen_y))

        # Draw sword during attack (but not when dying)
        if self.state == "attacking" and self.state != "dying":
            sword_frame = self.sword_anim.get_frame()
            if sword_frame:
                screen.blit(sword_frame, (screen_x - 16, screen_y - 16))


##############################################################
# OPTIMIZED ENEMY CLASS


class Enemy:
    # Shared animation definitions
    ANIMATIONS = {
        "idle_right": {
            "frames": [(0, 0), (0, 1)],
            "duration": 0.6,
            "loop": True,
        },
        "idle_left": {
            "frames": [(1, 0), (1, 1)],
            "duration": 0.6,
            "loop": True,
        },
        "walk_right": {
            "frames": [(2, 0), (2, 1), (2, 2)],
            "duration": 0.4,
            "loop": True,
        },
        "walk_left": {
            "frames": [(3, 0), (3, 1), (3, 2)],
            "duration": 0.4,
            "loop": True,
        },
        "hurt_right": {
            "frames": [(4, 0), (4, 1), (4, 2), (4, 3)],
            "duration": 0.2,
            "loop": False,
        },
        "hurt_left": {
            "frames": [(5, 0), (5, 1), (5, 2), (5, 3)],
            "duration": 0.2,
            "loop": False,
        },
    }

    def __init__(
        self, x, y, enemy_type="rat", movement="horizontal", blocks=2
    ):
        # Grid-snap position
        self.x = (x // TILE_SIZE) * TILE_SIZE
        self.y = (y // TILE_SIZE) * TILE_SIZE
        self.start_x, self.start_y = self.x, self.y

        # Movement
        self.facing = "right"
        self.movement_type = movement
        self.blocks = blocks
        self.blocks_moved = 0
        self.last_move = 0
        self.move_cooldown = 0.3

        # State machine
        self.state = "moving"  # moving, idle, hurt, dying
        self.state_timer = 0

        # Animation
        spritesheet_path = f"images/enemy_{enemy_type}.png"
        self.anim = AnimationManager(
            spritesheet_path, TILE_SIZE, self.ANIMATIONS
        )
        self.anim.play("walk_right")

    def set_paused(self, paused):
        """Set pause state for animations"""
        self.anim.set_paused(paused)

    def update(self, level_loader=None):
        """Simplified enemy AI"""
        now = time.time()

        if self.state == "dying":
            if now - self.state_timer >= 1.0:
                return  # Mark for removal
        elif self.state == "hurt":
            if now - self.state_timer >= 0.8:
                self.state = "moving"
                self.anim.play(f"walk_{self.facing}")
        elif self.state == "moving":
            self._update_movement(now, level_loader)
        elif self.state == "idle":
            if now - self.state_timer >= 3.0:
                self.facing = "left" if self.facing == "right" else "right"
                self.state = "moving"
                self.blocks_moved = 0
                self.anim.play(f"walk_{self.facing}")

        self.anim.update()

    def _update_movement(self, now, level_loader):
        """Handle movement logic"""
        if now - self.last_move < self.move_cooldown:
            return

        # Calculate movement direction
        dx = dy = 0
        if self.movement_type == "horizontal":
            dx = 1 if self.facing == "right" else -1
        else:  # vertical
            dy = 1 if self.facing == "right" else -1

        # Try to move
        new_x = self.x + (dx * TILE_SIZE)
        new_y = self.y + (dy * TILE_SIZE)

        can_move = True
        if level_loader:
            can_move = not level_loader.is_position_blocked(new_x, new_y)

        if can_move:
            self.x, self.y = new_x, new_y
            self.blocks_moved += 1
            self.last_move = now

            if self.blocks_moved >= self.blocks:
                self.state = "idle"
                self.state_timer = now
                self.anim.play(f"idle_{self.facing}")
        else:
            # Hit wall, go idle and turn around
            self.state = "idle"
            self.state_timer = now
            self.anim.play(f"idle_{self.facing}")

    def take_damage(self):
        """Take damage"""
        if self.state in ["hurt", "dying"]:
            return False

        self.state = "hurt"
        self.state_timer = time.time()
        self.anim.play(f"hurt_{self.facing}", True)
        return True

    def start_death(self):
        """Start death"""
        self.state = "dying"
        self.state_timer = time.time()
        sounds.hit_7.play()

    def should_be_removed(self):
        """Check if should be removed"""
        return self.state == "dying" and time.time() - self.state_timer >= 1.0

    def get_rect(self):
        return pygame.Rect(self.x, self.y, TILE_SIZE, TILE_SIZE)

    def draw(self, screen, camera_x, camera_y):
        """Draw enemy with death flashing"""
        screen_x, screen_y = self.x - camera_x, self.y - camera_y

        # Flash during death
        if self.state == "dying":
            if int(time.time() * 10) % 2:
                return

        frame = self.anim.get_frame()
        if frame:
            screen.blit(frame, (screen_x, screen_y))


class Boss(Enemy):
    """
    Boss enemy class with T-motion pattern and multiple health points.
    Inherits from Enemy but overrides most behavior for boss-specific mechanics.
    """

    # Boss-specific animation definitions
    BOSS_ANIMATIONS = {
        "idle_right": {
            "frames": [(0, 0), (0, 1)],
            "duration": 0.6,
            "loop": True,
        },
        "idle_left": {
            "frames": [(1, 0), (1, 1)],
            "duration": 0.6,
            "loop": True,
        },
        "walk_right": {
            "frames": [(2, 0), (2, 1), (2, 2), (2, 3)],
            "duration": 0.4,
            "loop": True,
        },
        "walk_left": {
            "frames": [(3, 0), (3, 1), (3, 2), (3, 3)],
            "duration": 0.4,
            "loop": True,
        },
        "hurt_right": {
            "frames": [(4, 0), (4, 1), (4, 2), (4, 3)],
            "duration": 0.2,
            "loop": False,
        },
        "hurt_left": {
            "frames": [(5, 0), (5, 1), (5, 2), (5, 3)],
            "duration": 0.2,
            "loop": False,
        },
    }

    def __init__(self, x, y):
        # Don't call super().__init__() to avoid Enemy's sprite loading
        # Instead, manually initialize the basic properties we need

        # Grid-snap position (from Enemy.__init__)
        self.x = (x // TILE_SIZE) * TILE_SIZE
        self.y = (y // TILE_SIZE) * TILE_SIZE
        self.start_x, self.start_y = self.x, self.y

        # Basic Enemy properties we need
        self.facing = "right"
        self.movement_type = "boss_ai"
        self.state = "moving"
        self.state_timer = 0

        # Boss-specific properties
        self.max_health = 3  # Boss takes 3 hits to defeat
        self.current_health = self.max_health
        self.size = 32  # Boss is 32x32 pixels (2x2 tiles)

        # Create boss-specific animation manager
        self.anim = AnimationManager(
            "images/boss_slime.png", 32, self.BOSS_ANIMATIONS
        )

        # T-Motion Pattern System
        self.move_cooldown = 0.3  # Speed of movement
        self.last_move = 0
        self.blocks_moved = 0
        self.target_blocks = 3  # Always move 3 blocks in each direction

        # T-Motion sequence: right, left, left, right, down, up
        self.t_sequence = ["right", "left", "left", "right", "down", "up"]
        self.current_sequence_index = 0
        self.current_direction = self.t_sequence[0]

        # Victory/defeat states
        self.defeated = False
        self.victory_timer = 0

        # Start with walking right animation
        self.anim.play("walk_right")

        print(f"Boss created at ({x}, {y}) with {self.max_health} health")
        print(f"Boss starting T-motion pattern: {' -> '.join(self.t_sequence)}")

    def get_rect(self):
        """Boss uses a 32x32 rectangle instead of 16x16"""
        return pygame.Rect(self.x, self.y, self.size, self.size)

    def take_damage(self):
        """Override damage system for boss"""
        if self.state in ["hurt", "dying"]:
            print(f"Boss damage blocked - state: {self.state}")
            return False

        # Take damage
        self.current_health -= 1

        # Check if boss is defeated
        if self.current_health <= 0:
            self._start_defeat()
            return True

        # Start hurt state
        self.state = "hurt"
        self.state_timer = time.time()

        # Play hurt animation and sound
        hurt_anim = f"hurt_{self.facing}"
        print(f"Boss entering hurt state, playing animation: {hurt_anim}")
        self.anim.play(hurt_anim, True)
        sounds.hit_7.play()

        # Add score for hitting boss
        global SCORE
        SCORE += 25  # More points for hitting boss

        print(f"Boss took damage! Health: {self.current_health}/{self.max_health}, State: {self.state}")
        return True

    def _start_defeat(self):
        """Handle boss defeat"""
        self.defeated = True
        self.state = "dying"
        self.state_timer = time.time()
        self.victory_timer = time.time()

        # Stop music and play victory sound
        music.stop()
        sounds.winneris.play()

        # Big score bonus for defeating boss
        global SCORE, HIGH_SCORE
        SCORE += 500

        # Update high score if current score is higher
        if SCORE > HIGH_SCORE:
            HIGH_SCORE = SCORE
            save_high_score(HIGH_SCORE)
            print(f"NEW HIGH SCORE! {HIGH_SCORE}")
        else:
            print(f"Boss defeated! Final Score: {SCORE} (High Score: {HIGH_SCORE})")

        # NEW: Start victory freeze instead of immediate transition
        # Access the global game state manager to trigger victory freeze
        global game_state_manager
        game_state_manager._start_victory_freeze()

        print("Boss defeated! Victory freeze activated!")

    def update(self, level_loader=None):
        """Update boss with T-motion pattern"""
        if self.defeated:
            # Boss is defeated, just wait for removal or victory sequence
            return

        now = time.time()

        # Initialize _last_update if it doesn't exist
        if not hasattr(self, '_last_update'):
            self._last_update = now

        # Handle hurt state FIRST
        if self.state == "hurt":
            hurt_duration = now - self.state_timer

            if hurt_duration >= 0.8:
                print("Boss exiting hurt state, resuming T-motion")

                # Exit hurt state
                self.state = "moving"

                # Resume T-motion with correct animation
                self._start_current_direction_animation()

            # Update animation regardless
            self.anim.update()
            self._last_update = now
            return

        # Handle dying state
        if self.state == "dying":
            if now - self.state_timer >= 2.0:
                pass  # Could trigger victory sequence here
            self.anim.update()
            self._last_update = now
            return

        # Handle T-motion pattern
        self._update_t_motion(now, level_loader)
        self.anim.update()
        self._last_update = now

    def _start_current_direction_animation(self):
        """Start the correct animation for current direction"""
        if self.current_direction in ["right", "down"]:
            self.facing = "right"
            self.anim.play("walk_right", True)
        else:  # left, up
            self.facing = "left"
            self.anim.play("walk_left", True)

    def _update_t_motion(self, now, level_loader):
        """Update T-motion pattern"""
        # Check if it's time to move
        if now - self.last_move < self.move_cooldown:
            return

        # Calculate movement based on current direction
        dx = dy = 0
        if self.current_direction == "right":
            dx = 1
        elif self.current_direction == "left":
            dx = -1
        elif self.current_direction == "down":
            dy = 1
        elif self.current_direction == "up":
            dy = -1

        # Calculate new position
        new_x = self.x + (dx * TILE_SIZE)
        new_y = self.y + (dy * TILE_SIZE)

        # Check if movement is valid (boundaries and collisions)
        can_move = True
        if level_loader:
            level_width, level_height = level_loader.get_level_size()
            if (new_x < 0 or new_x > level_width - self.size or
                new_y < 0 or new_y > level_height - self.size):
                can_move = False
            elif level_loader.is_position_blocked(new_x, new_y):
                can_move = False

        if can_move:
            # Move boss
            self.x, self.y = new_x, new_y
            self.blocks_moved += 1
            self.last_move = now

            print(f"Boss moved {self.current_direction}: {self.blocks_moved}/{self.target_blocks} blocks")

            # Check if we've completed this direction
            if self.blocks_moved >= self.target_blocks:
                self._next_direction()
        else:
            # Can't move in this direction, skip to next
            print(f"Boss can't move {self.current_direction}, skipping to next direction")
            self._next_direction()

    def _next_direction(self):
        """Move to next direction in T-sequence"""
        # Reset block counter
        self.blocks_moved = 0

        # Move to next direction in sequence
        self.current_sequence_index = (self.current_sequence_index + 1) % len(self.t_sequence)
        self.current_direction = self.t_sequence[self.current_sequence_index]

        print(f"Boss switching to direction: {self.current_direction}")

        # Start appropriate animation for new direction
        self._start_current_direction_animation()

    def should_be_removed(self):
        """Boss should only be removed after a longer victory sequence"""
        if not self.defeated:
            return False
        # Keep boss around for 3 seconds after defeat for victory sequence
        return time.time() - self.victory_timer >= 3.0

    def draw(self, screen, camera_x, camera_y):
        """Draw boss with special effects"""
        screen_x, screen_y = self.x - camera_x, self.y - camera_y

        # Flash during hurt state
        if self.state == "hurt":
            if int(time.time() * 15) % 2:  # Faster flashing for boss
                return

        # Flash during dying state
        if self.state == "dying":
            if int(time.time() * 8) % 2:
                return

        # Draw boss sprite
        frame = self.anim.get_frame()
        if frame:
            # Boss is 32x32 pixels
            screen.blit(frame, (screen_x, screen_y))


##############################################################
# OPTIMIZED UI CLASS


class UI:
    def __init__(self):
        self.spritesheet = pygame.image.load("images/ui_hud.png")
        self.full_heart = self.spritesheet.subsurface(
            0, 0, TILE_SIZE, TILE_SIZE
        )
        self.empty_heart = self.spritesheet.subsurface(
            2 * TILE_SIZE, 0, TILE_SIZE, TILE_SIZE
        )

        # Load key sprite - NEW!
        self.key_icon = self.spritesheet.subsurface(
            2 * TILE_SIZE, 1 * TILE_SIZE, TILE_SIZE, TILE_SIZE
        )

        # Load font for score display
        try:
            self.score_font = pygame.font.Font("fonts/early-gameboy.ttf", 12)
        except Exception as e:
            print(f"Warning: Could not load early-gameboy font for score: {e}")
            self.score_font = pygame.font.Font(None, 12)

    def draw(self, screen, player):
        """Draw health hearts, score, and key indicator"""
        global SCORE, HAS_KEY

        # Draw health hearts (existing code)
        for i in range(player.max_health):
            x = 16 + (i * TILE_SIZE)
            heart = self.full_heart if i < player.health else self.empty_heart
            screen.blit(heart, (x, 16))

        # Draw score in top center (existing code)
        score_text = f"{SCORE:03d}"
        if self.score_font:
            score_surface = self.score_font.render(
                score_text, True, RETRO_CREAM
            )
            score_rect = score_surface.get_rect(center=(WIDTH // 2, 16))
            screen.blit(score_surface, score_rect)

        # Draw key icon in upper right corner - NEW!
        if HAS_KEY:
            key_x = WIDTH - 16 - TILE_SIZE  # 16px from right edge
            key_y = 16  # 16px from top
            screen.blit(self.key_icon, (key_x, key_y))


##############################################################
# DOOR SYSTEM


class Door:
    def __init__(self, x, y, width, height, locked=True):
        self.rect = pygame.Rect(x, y, width, height)
        self.locked = locked

    def can_enter(self):
        global HAS_KEY
        if not self.locked:
            return True  # Unlocked door, always passable
        else:
            return HAS_KEY  # Locked door, only passable if player has key

    def check_collision(self, player_rect):
        return self.rect.colliderect(player_rect)


class Pickup:
    """Lightweight pickup class optimized for Pi Zero"""

    # Class-level animation definitions to reduce memory
    ANIMATIONS = {
        "coin": {
            "frames": [(0, 0), (0, 1), (0, 2), (0, 3)],
            "duration": 0.6,
            "loop": True,
        },
        "key": {
            "frames": [(1, 0), (1, 1), (1, 2), (1, 3)],  # Row 1 (index 0)
            "duration": 0.6,
            "loop": True,
        },
        "heart": {
            "frames": [(4, 0), (4, 1), (4, 2), (4, 3)],  # Row 4 (index 3)
            "duration": 0.6,
            "loop": True,
        },
    }

    def __init__(self, x, y, pickup_type="heart"):
        # Grid-snap position
        self.x = (x // TILE_SIZE) * TILE_SIZE
        self.y = (y // TILE_SIZE) * TILE_SIZE

        # Pickup properties
        self.pickup_type = pickup_type
        self.collected = False

        # Animation manager
        self.anim = AnimationManager(
            "images/pickup_animated.png", TILE_SIZE, self.ANIMATIONS
        )

        # Start appropriate animation
        if pickup_type in self.ANIMATIONS:
            self.anim.play(pickup_type)
            print(f"Pickup created: {pickup_type} at ({self.x}, {self.y})")  # Debug
        else:
            print(
                f"Warning: Unknown pickup type '{pickup_type}', defaulting to heart"
            )
            self.pickup_type = "heart"
            self.anim.play("heart")

    def set_paused(self, paused):
        """Set pause state for animations"""
        self.anim.set_paused(paused)

    def update(self):
        """Update pickup animation"""
        if not self.collected:
            self.anim.update()

    def collect(self, player):
        """Handle pickup collection by player"""
        if self.collected:
            return False

        self.collected = True
        print(f"Pickup collected: {self.pickup_type}")  # Debug

        # Handle different pickup types
        if self.pickup_type == "coin":
            self._collect_coin(player)
        elif self.pickup_type == "heart":
            self._collect_heart(player)
        elif self.pickup_type == "key":
            self._collect_key(player)
        # Add more pickup types here as needed

        return True

    def _collect_coin(self, player):
        """Handle coin pickup - add 10 to global score"""
        global SCORE
        SCORE += 10
        print(f"Coin collected! Score: {SCORE}")
        # Play coin collection sound
        try:
            sounds.gold_2.play()
        except:
            print("Warning: Could not play coin pickup sound")

    def _collect_heart(self, player):
        """Handle heart pickup - restore health if not at max"""
        if player.health < player.max_health:
            player.health += 1
            print(
                f"Health restored! Health: {player.health}/{player.max_health}"
            )
            # Play healing sound
            try:
                sounds.gold_2.play()  # Using existing sound, you can add a specific heal sound
            except:
                print("Warning: Could not play heart pickup sound")
        else:
            print("Health already full!")
            # Play different sound for full health
            try:
                sounds.hit_7.play()  # Different sound when health is full
            except:
                print("Warning: Could not play full health sound")

    def _collect_key(self, player):
        global HAS_KEY  # This line is missing!
        sounds.gold_2.play()
        HAS_KEY = True
        print(f"Key collected! HAS_KEY is now: {HAS_KEY}")

    def get_rect(self):
        """Get collision rectangle"""
        return pygame.Rect(self.x, self.y, TILE_SIZE, TILE_SIZE)

    def should_be_removed(self):
        """Check if pickup should be removed from game"""
        return self.collected

    def draw(self, screen, camera_x, camera_y):
        """Draw pickup if not collected"""
        if self.collected:
            return

        screen_x, screen_y = self.x - camera_x, self.y - camera_y

        # Only draw if on screen (with some margin for smooth scrolling)
        if (
            -TILE_SIZE <= screen_x <= WIDTH
            and -TILE_SIZE <= screen_y <= HEIGHT
        ):
            frame = self.anim.get_frame()
            if frame:
                screen.blit(frame, (screen_x, screen_y))
            else:
                # Debug: draw a colored square if no frame available
                debug_surf = pygame.Surface((TILE_SIZE, TILE_SIZE))
                debug_surf.fill((255, 0, 255))  # Magenta for missing pickup frame
                screen.blit(debug_surf, (screen_x, screen_y))


##############################################################
# OPTIMIZED LEVEL LOADER


class LevelLoader:
    """Optimized level loader with reduced memory allocations"""

    def __init__(self, level_sequence):
        self.level_sequence = level_sequence
        self.current_level_index = 0
        self.tmx_data = None
        self.bg_surface = None
        self.camera_x = self.camera_y = 0
        self.objects = []
        self.player = None
        self.collision_grid = []
        self.animated_tiles = []
        self.doors = []
        self.pickups = []
        self.ui = UI()

        # Transition system
        self.transitioning = False
        self.transition_timer = 0
        self.transition_duration = 0.5
        self.transition_surface = pygame.Surface((WIDTH, HEIGHT)).convert_alpha()

        # OPTIMIZATION: Pre-allocate commonly used rectangles
        self._temp_rect = pygame.Rect(0, 0, TILE_SIZE, TILE_SIZE)
        self._screen_rect = pygame.Rect(0, 0, WIDTH, HEIGHT)

        # OPTIMIZATION: Cache level size to avoid recalculation
        self._level_width = 0
        self._level_height = 0

        # OPTIMIZATION: Cache frame time during pause
        self._paused_frame_time = 0

        self.load_current_level()

    def set_paused(self, paused):
        """Set pause state for all entities including pickups"""
        # Pause player animations
        if self.player:
            self.player.set_paused(paused)

        # Pause enemy animations
        for obj in self.objects:
            if isinstance(obj, Enemy):
                obj.set_paused(paused)

        # Pause pickup animations
        for pickup in self.pickups:
            pickup.set_paused(paused)

    def load_current_level(self):
        """Load current level with error handling and cache clearing"""
        if self.current_level_index >= len(self.level_sequence):
            return False
    
        level_name = self.level_sequence[self.current_level_index]
        tmx_path = os.path.join("data", "tmx", f"{level_name}.tmx")

        try:
            # FIXED: Clear tile caches when loading a new level
            if hasattr(self, '_tile_conversion_cache'):
                self._tile_conversion_cache.clear()
            if hasattr(self, '_animated_frame_cache'):
                self._animated_frame_cache.clear()

            self.tmx_data = pytmx.load_pygame(tmx_path)
            self._create_collision_grid()
            self._render_background()
            self._load_objects()
            self._load_animated_tiles()
            return True
        except Exception as e:
            print(f"Error loading level: {e}")
            return False

    def _create_collision_grid(self):
        """Create collision grid with optimization"""
        if not self.tmx_data:
            return

        w, h = self.tmx_data.width, self.tmx_data.height
        # OPTIMIZATION: Pre-allocate grid more efficiently
        self.collision_grid = [[False for _ in range(w)] for _ in range(h)]

        # Find colliders layer
        for layer in self.tmx_data.layers:
            if layer.name == "colliders" and hasattr(layer, "data"):
                for x, y, gid in layer:
                    if gid and 0 <= y < h and 0 <= x < w:
                        self.collision_grid[y][x] = True
                break

    def _render_background(self):
        """Simplified version - just use convert_alpha() for everything"""
        if not self.tmx_data:
            return

        w = self.tmx_data.width * self.tmx_data.tilewidth
        h = self.tmx_data.height * self.tmx_data.tileheight

        self._level_width, self._level_height = w, h
        self.bg_surface = pygame.Surface((w, h)).convert_alpha()

        if not hasattr(self, '_tile_conversion_cache'):
            self._tile_conversion_cache = {}

        for layer_name in ["background", "colliders"]:
            for layer in self.tmx_data.layers:
                if layer.name == layer_name and hasattr(layer, "data"):
                    for x, y, gid in layer:
                        if gid:
                            tile = self.tmx_data.get_tile_image_by_gid(gid)
                            if tile:
                                # SIMPLE FIX: Just use convert_alpha() for everything
                                if gid not in self._tile_conversion_cache:
                                    self._tile_conversion_cache[gid] = tile.convert_alpha()

                                converted_tile = self._tile_conversion_cache[gid]
                                self.bg_surface.blit(converted_tile, (
                                    x * self.tmx_data.tilewidth,
                                    y * self.tmx_data.tileheight
                                ))

    def _load_objects(self):
        """Load objects from level with health preservation"""
        # Store previous player health before clearing objects
        previous_health = None
        if self.player:
            previous_health = self.player.health
            print(f"Preserving player health: {previous_health}")

        # Clear existing objects
        self.objects.clear()
        old_player = self.player
        self.player = None
        self.doors.clear()
        self.pickups.clear()

        if not self.tmx_data:
            return

        # Find objects layer
        for layer in self.tmx_data.layers:
            if layer.name == "objects":
                for obj in layer:
                    name = obj.name.lower() if obj.name else ""

                    if name == "player":
                        player = Player(obj.x, obj.y)

                        # Restore previous health if we had a player before
                        if previous_health is not None:
                            player.health = previous_health
                            print(f"Restored player health to: {player.health}")

                        self.objects.append(player)
                        self.player = player

                    elif name == "door":
                        # Get locked property with default
                        locked = getattr(obj, "locked", True)
                        if hasattr(obj, "properties"):
                            locked = obj.properties.get("locked", locked)

                        door = Door(obj.x, obj.y, obj.width, obj.height, locked)
                        self.doors.append(door)

                    elif name == "pickup":
                        # Handle pickup objects
                        pickup_type = getattr(obj, "pickup_type", "heart")
                        if hasattr(obj, "properties"):
                            pickup_type = obj.properties.get("pickup_type", pickup_type)

                        pickup = Pickup(obj.x, obj.y, pickup_type)
                        self.pickups.append(pickup)
                        print(f"Loaded pickup: {pickup_type} at ({obj.x}, {obj.y})")

                    elif name == "enemy":
                        # Get properties with defaults
                        enemy_type = getattr(obj, "enemy_type", "rat")
                        movement = getattr(obj, "enemy_movement", "horizontal")
                        blocks = getattr(obj, "blocks", 2)

                        if hasattr(obj, "properties"):
                            enemy_type = obj.properties.get("enemy_type", enemy_type)
                            movement = obj.properties.get("enemy_movement", movement)
                            blocks = obj.properties.get("blocks", blocks)

                        enemy = Enemy(obj.x, obj.y, enemy_type, movement, int(blocks))
                        self.objects.append(enemy)

                    elif name == "boss":
                        boss = Boss(obj.x, obj.y)
                        self.objects.append(boss)
                        print(f"Boss loaded at ({obj.x}, {obj.y})")

                    elif name == "info":
                        # Handle music
                        music_file = getattr(obj, "music", None)
                        if hasattr(obj, "properties"):
                            music_file = obj.properties.get("music", music_file)
                        if music_file:
                            self._load_music(music_file)
                break

    def _load_music(self, filename):
        """Load background music with error handling"""
        try:
            music.stop()
            if os.path.exists(f"music/{filename}.ogg"):
                music.play(filename)
        except Exception as e:
            print(f"Warning: Could not load music {filename}: {e}")

    def _load_animated_tiles(self):
        """Load animated tiles - optimized and FIXED"""
        self.animated_tiles.clear()

        if not self.tmx_data:
            return

        # OPTIMIZATION: Create a cache for converted animated frames
        if not hasattr(self, '_animated_frame_cache'):
            self._animated_frame_cache = {}

        # Find animated layer
        for layer in self.tmx_data.layers:
            if layer.name == "animated" and hasattr(layer, "data"):
                for x, y, gid in layer:
                    if gid:
                        frames = self._get_tile_frames(gid)
                        if frames and len(frames) > 1:  # Only store truly animated tiles
                            # FIXED: Convert frames using a cache instead of modifying originals
                            converted_frames = []
                            for i, frame in enumerate(frames):
                                if frame:
                                    # Use GID + frame index as cache key
                                    cache_key = f"{gid}_{i}"
                                    if cache_key not in self._animated_frame_cache:
                                        self._animated_frame_cache[cache_key] = frame.convert_alpha()
                                    converted_frames.append(self._animated_frame_cache[cache_key])

                            if converted_frames:
                                self.animated_tiles.append({
                                    "x": x * self.tmx_data.tilewidth,
                                    "y": y * self.tmx_data.tileheight,
                                    "frames": converted_frames,
                                })
                break

    def _get_tile_frames(self, gid):
        """Extract animation frames for a tile with error handling"""
        try:
            props = self.tmx_data.get_tile_properties_by_gid(gid)
            if props and "frames" in props:
                frames = []
                for frame in props["frames"]:
                    surface = self.tmx_data.get_tile_image_by_gid(frame.gid)
                    if surface:
                        frames.append(surface)
                return frames
            else:
                # Static tile
                surface = self.tmx_data.get_tile_image_by_gid(gid)
                return [surface] if surface else []
        except Exception as e:
            print(f"Warning: Error loading tile frames for gid {gid}: {e}")
            surface = self.tmx_data.get_tile_image_by_gid(gid)
            return [surface] if surface else []

    def start_transition(self):
        """Start level transition"""
        if self.transitioning:
            return False

        self.transitioning = True
        self.transition_timer = time.time()
        return True

    def next_level(self):
        """Load next level in sequence"""
        self.current_level_index += 1
        if self.current_level_index >= len(self.level_sequence):
            print("All levels completed!")
            self.current_level_index = len(self.level_sequence) - 1
            return False

        return self.load_current_level()

    def get_level_size(self):
        """Return cached level size"""
        return (self._level_width, self._level_height)

    def is_position_blocked(self, x, y):
        """Optimized collision check with bounds validation"""
        tile_x, tile_y = int(x // TILE_SIZE), int(y // TILE_SIZE)

        # Quick bounds check
        if (tile_x < 0 or tile_y < 0 or
            tile_y >= len(self.collision_grid) or
            tile_x >= len(self.collision_grid[0])):
            return True

        return self.collision_grid[tile_y][tile_x]

    def update(self):
        """Update game logic with victory freeze check"""
        # Check if we're in victory freeze mode
        if (hasattr(game_state_manager, 'victory_freeze') and
            game_state_manager.victory_freeze):
            return

        # Handle transition
        if self.transitioning:
            elapsed = time.time() - self.transition_timer
            if elapsed >= self.transition_duration:
                self.transitioning = False
                self.next_level()
            return

        # Update entities
        for entity in self.objects:
            if hasattr(entity, "update"):
                if isinstance(entity, Enemy):
                    entity.update(self)
                else:
                    entity.update()

        # Update pickups
        for pickup in self.pickups:
            pickup.update()

        # Collision checks
        self._check_collisions()

        # Remove dead enemies
        self.objects = [
            obj for obj in self.objects
            if not (isinstance(obj, Enemy) and obj.should_be_removed())
        ]

        # Remove collected pickups
        self.pickups = [
            pickup for pickup in self.pickups
            if not pickup.should_be_removed()
        ]

    def _check_collisions(self):
        """Check all collisions with optimizations"""
        if not self.player:
            return

        player_rect = self.player.get_rect()

        # Pickup collisions (check first)
        for pickup in self.pickups:
            if not pickup.collected and player_rect.colliderect(pickup.get_rect()):
                pickup.collect(self.player)
                break

        # Player-enemy collisions
        if self.player.invincible_timer <= 0:
            for obj in self.objects:
                if (isinstance(obj, Enemy) and
                    obj.state not in ["hurt", "dying"] and
                    player_rect.colliderect(obj.get_rect())):
                    self.player.take_damage(1)
                    break

        # Sword-enemy collisions
        if self.player.state == "attacking":
            sword_rect = self._get_sword_rect()
            if sword_rect:
                for obj in self.objects:
                    if (isinstance(obj, Enemy) and
                        obj.state not in ["hurt", "dying"] and
                        sword_rect.colliderect(obj.get_rect())):
                        if obj.take_damage():
                            # Only call start_death for regular enemies, not Boss
                            if not isinstance(obj, Boss):
                                obj.start_death()
                        break

    def _get_sword_rect(self):
        """Get sword attack rectangle using cached rect"""
        if not self.player or self.player.state != "attacking":
            return None

        # OPTIMIZATION: Reuse temp rectangle
        if self.player.facing == "right":
            self._temp_rect.x = self.player.x + TILE_SIZE
            self._temp_rect.y = self.player.y
        else:
            self._temp_rect.x = self.player.x - TILE_SIZE
            self._temp_rect.y = self.player.y

        self._temp_rect.width = TILE_SIZE
        self._temp_rect.height = TILE_SIZE
        return self._temp_rect

    def draw(self, screen):
        """Optimized drawing with early culling"""
        # Update screen rect for culling
        self._screen_rect.x = self.camera_x
        self._screen_rect.y = self.camera_y

        # Background
        if self.bg_surface:
            screen.blit(self.bg_surface, (0, 0), self._screen_rect)

        # Animated tiles with frame caching
        if self.animated_tiles:
            # Use cached frame time during pause
            if (hasattr(game_state_manager, "game_paused") and
                game_state_manager.game_paused):
                frame_time = self._paused_frame_time
            else:
                frame_time = pygame.time.get_ticks() // 600
                self._paused_frame_time = frame_time

            for tile in self.animated_tiles:
                if len(tile["frames"]) > 1:
                    # OPTIMIZATION: Use cached screen position
                    screen_x = tile["x"] - self.camera_x
                    screen_y = tile["y"] - self.camera_y

                    # Cull off-screen tiles
                    if -TILE_SIZE <= screen_x <= WIDTH and -TILE_SIZE <= screen_y <= HEIGHT:
                        frame_idx = frame_time % len(tile["frames"])
                        screen.blit(tile["frames"][frame_idx], (screen_x, screen_y))

        # Draw pickups (with culling)
        for pickup in self.pickups:
            pickup.draw(screen, self.camera_x, self.camera_y)

        # Draw entities (with culling)
        for obj in self.objects:
            # OPTIMIZATION: Only draw objects that could be on screen
            if hasattr(obj, 'x') and hasattr(obj, 'y'):
                screen_x = obj.x - self.camera_x
                screen_y = obj.y - self.camera_y
                if -64 <= screen_x <= WIDTH + 64 and -64 <= screen_y <= HEIGHT + 64:
                    obj.draw(screen, self.camera_x, self.camera_y)
            else:
                obj.draw(screen, self.camera_x, self.camera_y)

        # UI
        if self.player:
            self.ui.draw(screen, self.player)

        # Debug
        if DEBUG_MODE_ON:
            self._draw_debug(screen)

        # Transition
        if self.transitioning:
            self._draw_transition(screen)

    def _draw_transition(self, screen):
        """Draw retro fade transition"""
        elapsed = time.time() - self.transition_timer
        progress = elapsed / self.transition_duration

        # Fade to brown instead of black
        alpha = int(255 * progress)
        self.transition_surface.fill(RETRO_BROWN)
        self.transition_surface.set_alpha(alpha)
        screen.blit(self.transition_surface, (0, 0))

    def _draw_debug(self, screen):
        """Draw debug info with optimized rendering"""
        # Draw collision tiles in red
        for y, row in enumerate(self.collision_grid):
            for x, blocked in enumerate(row):
                if blocked:
                    screen_x = (x * TILE_SIZE) - self.camera_x
                    screen_y = (y * TILE_SIZE) - self.camera_y
                    if -TILE_SIZE <= screen_x <= WIDTH and -TILE_SIZE <= screen_y <= HEIGHT:
                        # OPTIMIZATION: Create debug surface once and reuse
                        if not hasattr(self, '_debug_red_surf'):
                            self._debug_red_surf = pygame.Surface((TILE_SIZE, TILE_SIZE)).convert_alpha()
                            self._debug_red_surf.set_alpha(128)
                            self._debug_red_surf.fill((255, 0, 0))
                        screen.blit(self._debug_red_surf, (screen_x, screen_y))

        # Draw doors
        for door in self.doors:
            screen_x = door.rect.x - self.camera_x
            screen_y = door.rect.y - self.camera_y
            if (-door.rect.width <= screen_x <= WIDTH and
                -door.rect.height <= screen_y <= HEIGHT):

                # OPTIMIZATION: Create door debug surfaces once
                if not hasattr(self, '_debug_door_surfs'):
                    self._debug_door_surfs = {}

                color_key = "green" if door.can_enter() else "yellow"
                if color_key not in self._debug_door_surfs:
                    surf = pygame.Surface((door.rect.width, door.rect.height)).convert_alpha()
                    surf.set_alpha(128)
                    color = (0, 255, 0) if color_key == "green" else (255, 255, 0)
                    surf.fill(color)
                    self._debug_door_surfs[color_key] = surf

                screen.blit(self._debug_door_surfs[color_key], (screen_x, screen_y))

        # Draw pickup debug info in blue
        for pickup in self.pickups:
            if not pickup.collected:
                screen_x = pickup.x - self.camera_x
                screen_y = pickup.y - self.camera_y
                if -TILE_SIZE <= screen_x <= WIDTH and -TILE_SIZE <= screen_y <= HEIGHT:
                    # OPTIMIZATION: Create pickup debug surface once
                    if not hasattr(self, '_debug_pickup_surf'):
                        self._debug_pickup_surf = pygame.Surface((TILE_SIZE, TILE_SIZE)).convert_alpha()
                        self._debug_pickup_surf.set_alpha(128)
                        self._debug_pickup_surf.fill((0, 0, 255))
                    screen.blit(self._debug_pickup_surf, (screen_x, screen_y))

    def move_player(self, dx, dy):
        """Move player with collision check"""
        if self.player:
            new_x = self.player.x + (dx * TILE_SIZE)
            new_y = self.player.y + (dy * TILE_SIZE)

            if not self.is_position_blocked(new_x, new_y):
                level_width, level_height = self.get_level_size()
                current_time = pygame.time.get_ticks() / 1000.0
                return self.player.move(dx, dy, level_width, level_height, current_time)
        return False

    def try_enter_door(self):
        """Try to enter a door when Enter is pressed"""
        if not self.player or self.transitioning:
            return

        global HAS_KEY
        player_rect = self.player.get_rect()

        for door in self.doors:
            if door.check_collision(player_rect):
                if door.can_enter():
                    print("Player entered door - starting transition")

                    # If this was a locked door that required a key, consume the key
                    if door.locked and HAS_KEY:
                        HAS_KEY = False
                        print("Key consumed! HAS_KEY is now False")

                    try:
                        sounds.wings.play()
                    except:
                        pass
                    self.start_transition()
                    return
                else:
                    # Player is at a locked door but doesn't have key
                    print("Door is locked! You need a key.")
                    try:
                        sounds.hit_7.play()
                    except:
                        pass
                    return


##############################################################
# GAME LOOP

game_state_manager = GameStateManager()


def draw():
    """Optimized drawing function"""
    screen.clear()
    game_state_manager.draw(screen.surface)


def update():
    """Optimized update function"""
    # Update game state
    game_state_manager.update()

    # Handle input for current state
    game_state_manager.handle_input()

    # Set pause state for level entities when game is paused
    if (game_state_manager.current_state == STATE_GAME and
      game_state_manager.level_loader):
        game_state_manager.level_loader.set_paused(game_state_manager.game_paused)


# OPTIMIZATION: Add cleanup function for memory management
def cleanup():
    """Cleanup function to call on exit"""
    AnimationManager.clear_caches()
    pygame.quit()


# Register cleanup function
import atexit

atexit.register(cleanup)

pgzrun.go()