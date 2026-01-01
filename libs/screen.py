import logging
from typing import Any

from libs.audio import audio
from libs.texture import tex
from libs.utils import input_state

logger = logging.getLogger(__name__)

class Screen:
    def __init__(self, name: str):
        self.screen_init = False
        self.screen_name = name

    def _do_screen_start(self):
        if not self.screen_init:
            self.screen_init = True
            self.on_screen_start()
            logger.info(f"{self.__class__.__name__} initialized")

    def on_screen_start(self) -> Any:
        tex.load_screen_textures(self.screen_name)
        logger.info(f"Loaded textures for screen: {self.screen_name}")
        audio.load_screen_sounds(self.screen_name)
        logger.info(f"Loaded sounds for screen: {self.screen_name}")

    def on_screen_end(self, next_screen: str):
        self.screen_init = False
        logger.info(f"{self.__class__.__name__} ended, transitioning to {next_screen} screen")
        audio.unload_all_sounds()
        audio.unload_all_music()
        logger.info(f"Unloaded sounds for screen: {next_screen}")
        tex.unload_textures()
        logger.info(f"Unloaded textures for screen: {next_screen}")
        return next_screen

    def update(self) -> Any:
        input_state.update()
        ret_val = self._do_screen_start()
        if ret_val:
            return ret_val

    def draw(self):
        pass

    def _do_draw(self):
        if self.screen_init:
            self.draw()
