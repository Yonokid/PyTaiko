import logging
import pyray as ray

from libs.audio import audio
from libs.screen import Screen
from libs.utils import (
    global_data,
    is_l_don_pressed,
    is_l_kat_pressed,
    is_r_don_pressed,
    is_r_kat_pressed,
)
from libs.config import save_config

logger = logging.getLogger(__name__)


class SettingsScreen(Screen):
    def on_screen_start(self):
        super().on_screen_start()
        self.config = global_data.config
        self.headers = list(self.config.keys())
        self.headers.append('Exit')
        self.header_index = 0
        self.setting_index = 0
        self.in_setting_edit = False
        self.editing_key = False
        self.editing_gamepad = False

    def on_screen_end(self, next_screen: str):
        save_config(self.config)
        global_data.config = self.config
        audio.close_audio_device()
        audio.device_type = global_data.config["audio"]["device_type"]
        sample_rate = global_data.config["audio"]["sample_rate"]
        if sample_rate < 0:
            sample_rate = 44100
        audio.target_sample_rate = sample_rate
        audio.buffer_size = global_data.config["audio"]["buffer_size"]
        audio.volume_presets = global_data.config["volume"]
        audio.init_audio_device()
        logger.info("Settings saved and audio device re-initialized")
        return next_screen

    def get_current_settings(self):
        """Get the current section's settings as a list"""
        current_header = self.headers[self.header_index]
        if current_header == 'Exit' or current_header not in self.config:
            return []
        return list(self.config[current_header].items())

    def handle_boolean_toggle(self, section, key):
        """Toggle boolean values"""
        self.config[section][key] = not self.config[section][key]
        logger.info(f"Toggled boolean setting: {section}.{key} -> {self.config[section][key]}")

    def handle_numeric_change(self, section, key, increment):
        """Handle numeric value changes"""
        current_value = self.config[section][key]

        # Define step sizes for different settings
        step_sizes = {
            'judge_offset': 1,
            'visual_offset': 1,
            'sample_rate': 1000,
        }

        step = step_sizes.get(key, 1)
        new_value = current_value + (step * increment)

        if key == 'sample_rate':
            valid_rates = [-1, 22050, 44100, 48000, 88200, 96000]
            current_idx = valid_rates.index(current_value) if current_value in valid_rates else 2
            new_idx = max(0, min(len(valid_rates) - 1, current_idx + increment))
            new_value = valid_rates[new_idx]

        if key == 'buffer_size':
            valid_sizes = [-1, 32, 64, 128, 256, 512, 1024]
            current_idx = valid_sizes.index(current_value) if current_value in valid_sizes else 2
            new_idx = max(0, min(len(valid_sizes) - 1, current_idx + increment))
            new_value = valid_sizes[new_idx]

        self.config[section][key] = new_value
        logger.info(f"Changed numeric setting: {section}.{key} -> {new_value}")

    def handle_string_cycle(self, section, key):
        """Cycle through predefined string values"""
        current_value = self.config[section][key]

        options = {
            'language': ['ja', 'en'],
        }

        if key in options:
            values = options[key]
            try:
                current_idx = values.index(current_value)
                new_idx = (current_idx + 1) % len(values)
                self.config[section][key] = values[new_idx]
            except ValueError:
                self.config[section][key] = values[0]
        logger.info(f"Cycled string setting: {section}.{key} -> {self.config[section][key]}")

    def handle_key_binding(self, section, key):
        """Handle key binding changes"""
        self.editing_key = True
        logger.info(f"Started key binding edit for: {section}.{key}")

    def update_key_binding(self):
        """Update key binding based on input"""
        key_pressed = ray.get_key_pressed()
        if key_pressed != 0:
            # Convert keycode to character
            if 65 <= key_pressed <= 90:  # A-Z
                new_key = chr(key_pressed)
                current_header = self.headers[self.header_index]
                settings = self.get_current_settings()
                if settings:
                    setting_key, _ = settings[self.setting_index]
                    self.config[current_header][setting_key] = [new_key]
                    self.editing_key = False
                    logger.info(f"Key binding updated: {current_header}.{setting_key} -> {new_key}")
            elif key_pressed == global_data.config["keys"]["back_key"]:
                self.editing_key = False
                logger.info("Key binding edit cancelled")

    def handle_gamepad_binding(self, section, key):
        self.editing_gamepad = True
        logger.info(f"Started gamepad binding edit for: {section}.{key}")

    def update_gamepad_binding(self):
        """Update gamepad binding based on input"""
        button_pressed = ray.get_gamepad_button_pressed()
        if button_pressed != 0:
            current_header = self.headers[self.header_index]
            settings = self.get_current_settings()
            if settings:
                setting_key, _ = settings[self.setting_index]
                self.config[current_header][setting_key] = [button_pressed]
                self.editing_gamepad = False
                logger.info(f"Gamepad binding updated: {current_header}.{setting_key} -> {button_pressed}")
        if ray.is_key_pressed(global_data.config["keys"]["back_key"]):
            self.editing_gamepad = False
            logger.info("Gamepad binding edit cancelled")

    def update(self):
        super().update()

        # Handle key binding editing
        if self.editing_key:
            self.update_key_binding()
            return

        if self.editing_gamepad:
            self.update_gamepad_binding()
            return

        current_header = self.headers[self.header_index]

        # Exit handling
        if current_header == 'Exit' and (is_l_don_pressed() or is_r_don_pressed()):
            logger.info("Exiting settings screen")
            return self.on_screen_end("ENTRY")

        # Navigation between sections
        if not self.in_setting_edit:
            if is_r_kat_pressed():
                self.header_index = (self.header_index + 1) % len(self.headers)
                self.setting_index = 0
                logger.info(f"Navigated to next section: {self.headers[self.header_index]}")
            elif is_l_kat_pressed():
                self.header_index = (self.header_index - 1) % len(self.headers)
                self.setting_index = 0
                logger.info(f"Navigated to previous section: {self.headers[self.header_index]}")
            elif (is_l_don_pressed() or is_r_don_pressed()) and current_header != 'Exit':
                self.in_setting_edit = True
                logger.info(f"Entered section edit: {current_header}")
        else:
            # Navigation within settings
            settings = self.get_current_settings()
            if not settings:
                self.in_setting_edit = False
                return

            if is_r_kat_pressed():
                self.setting_index = (self.setting_index + 1) % len(settings)
                logger.info(f"Navigated to next setting: {settings[self.setting_index][0]}")
            elif is_l_kat_pressed():
                self.setting_index = (self.setting_index - 1) % len(settings)
                logger.info(f"Navigated to previous setting: {settings[self.setting_index][0]}")
            elif is_r_don_pressed():
                # Modify setting value
                setting_key, setting_value = settings[self.setting_index]

                if isinstance(setting_value, bool):
                    self.handle_boolean_toggle(current_header, setting_key)
                elif isinstance(setting_value, (int, float)):
                    self.handle_numeric_change(current_header, setting_key, 1)
                elif isinstance(setting_value, str):
                    if 'keys' in current_header:
                        self.handle_key_binding(current_header, setting_key)
                    elif 'gamepad' in current_header:
                        self.handle_gamepad_binding(current_header, setting_key)
                    else:
                        self.handle_string_cycle(current_header, setting_key)
                elif isinstance(setting_value, list) and len(setting_value) > 0:
                    if isinstance(setting_value[0], str) and len(setting_value[0]) == 1:
                        # Key binding
                        self.handle_key_binding(current_header, setting_key)
                    elif isinstance(setting_value[0], int):
                        self.handle_gamepad_binding(current_header, setting_key)
            elif is_l_don_pressed():
                # Modify setting value (reverse direction for numeric)
                setting_key, setting_value = settings[self.setting_index]

                if isinstance(setting_value, bool):
                    self.handle_boolean_toggle(current_header, setting_key)
                elif isinstance(setting_value, (int, float)):
                    self.handle_numeric_change(current_header, setting_key, -1)
                elif isinstance(setting_value, str):
                    if ('keys' not in current_header) and ('gamepad' not in current_header):
                        self.handle_string_cycle(current_header, setting_key)

            elif ray.is_key_pressed(global_data.config["keys"]["back_key"]):
                self.in_setting_edit = False
                logger.info("Exited section edit")

    def draw(self):
        ray.draw_rectangle(0, 0, tex.screen_width, tex.screen_height, ray.BLACK)
        # Draw title
        ray.draw_text("SETTINGS", 20, 20, 30, ray.WHITE)

        # Draw section headers
        current_header = self.headers[self.header_index]
        for i, key in enumerate(self.headers):
            color = ray.GREEN
            if key == current_header:
                color = ray.YELLOW if not self.in_setting_edit else ray.ORANGE
            ray.draw_text(f'{key}', 20, i*25 + 70, 20, color)

        # Draw current section settings
        if current_header != 'Exit' and current_header in self.config:
            settings = self.get_current_settings()

            # Draw settings list
            for i, (key, value) in enumerate(settings):
                color = ray.GREEN
                if self.in_setting_edit and i == self.setting_index:
                    color = ray.YELLOW

                # Format value display
                if isinstance(value, list):
                    display_value = ', '.join(map(str, value))
                else:
                    display_value = str(value)
                if key == 'device_type' and not isinstance(value, list):
                    display_value = f'{display_value} ({audio.get_host_api_name(value)})'
                ray.draw_text(f'{key}: {display_value}', 250, i*25 + 70, 20, color)

            # Draw instructions
            y_offset = len(settings) * 25 + 150
            if not self.in_setting_edit:
                ray.draw_text("Don/Kat: Navigate sections", 20, y_offset, 16, ray.GRAY)
                ray.draw_text("L/R Don: Enter section", 20, y_offset + 20, 16, ray.GRAY)
            else:
                ray.draw_text("Don/Kat: Navigate settings", 20, y_offset, 16, ray.GRAY)
                ray.draw_text("L/R Don: Modify value", 20, y_offset + 20, 16, ray.GRAY)
                ray.draw_text("ESC: Back to sections", 20, y_offset + 40, 16, ray.GRAY)

                if self.editing_key:
                    ray.draw_text("Press a key to bind (ESC to cancel)", 20, y_offset + 60, 16, ray.RED)
        else:
            # Draw exit instruction
            ray.draw_text("Press Don to exit settings", 250, 100, 20, ray.GREEN)
