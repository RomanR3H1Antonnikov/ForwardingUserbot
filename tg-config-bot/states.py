from aiogram.fsm.state import State, StatesGroup


class SetupFlow(StatesGroup):
    source_link = State()
    dest_link = State()
    confirm = State()
    running = State()
    paused = State()
