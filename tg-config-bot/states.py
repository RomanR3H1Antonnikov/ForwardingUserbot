from aiogram.fsm.state import State, StatesGroup


class SetupFlow(StatesGroup):
    source_link = State()
    source_type = State()
    dest_link = State()
    dest_type = State()
    media_filter = State()
    direction = State()
    confirm = State()
    running = State()
    paused = State()
